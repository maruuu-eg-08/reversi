// ビルドした Web版のエンジン（dist/engine/*.wasm と dist/wasm-engine.js）を Node で動かして確かめる。
// ブラウザと同じコードを使うので、「ビルドしたものが本当に動くか」を CI で確認できる。
// 使い方: npm run build && npm test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const { WasmEngine } = await import(join(dist, "wasm-engine.js"));

const engine = await WasmEngine.create(
  {
    wasm: readFileSync(join(dist, "engine", "reversi_engine.wasm")),
    patterns: readFileSync(join(dist, "engine", "pattern_weights.bin")).buffer,
    book: readFileSync(join(dist, "engine", "opening_book.txt"), "utf8"),
  },
  () => performance.now(),
);
let checks = 0;
const ok = (cond, msg) => {
  assert.ok(cond, msg);
  checks++;
};

ok(engine.usesPatterns, "パターン評価の重みを読み込めている");

// 開始局面
const start = engine.newGame();
ok(start.color === 1 && start.blackCount === 2 && start.whiteCount === 2, "開始局面の石の数");
assert.deepEqual(start.legal, [[2, 3], [3, 2], [4, 5], [5, 4]]);
checks++;

// 打つ・打てない手
const s1 = engine.play(start.black, start.white, 1, 2, 3);
ok(s1.color === -1 && s1.blackCount === 4 && s1.whiteCount === 1, "d3 に打つと4対1");
assert.deepEqual(s1.flipped, [[3, 3]]);
checks++;
ok("error" in engine.play(start.black, start.white, 1, 0, 0), "a1 には打てない");

// 各レベルの AI が合法手を返す
const isLegal = (s, m) => s.legal.some(([r, c]) => r === m[0] && c === m[1]);
for (const level of ["1", "2", "3", "4", "5"]) {
  const r = engine.aiMove(start.black, start.white, 1, level, 3, 0.2);
  ok(r.move && isLegal(start, r.move), `Lv.${level} の手が合法`);
}
const lv5 = engine.aiMove(start.black, start.white, 1, "5", 4, 1.0);
ok(lv5.book === true, "Lv.5 は開始局面で定石を使う");

// 読み筋（評価値の高い順）
const a = engine.analyze(s1.black, s1.white, -1, 3);
ok(a.moves.length === s1.legal.length && a.nodes > 0, "読み筋に全合法手がある");
ok(a.moves.every((m, i) => i === 0 || a.moves[i - 1].score >= m.score), "読み筋は良い順");

// 定石名
ok(engine.opening("f5d6c3d3c4").name === "虎（Tiger）", "虎を判定できる");
ok(engine.opening("").name === null && engine.opening("a1").name === null, "定石でないものは null");

// Lv.5（短い持ち時間）と Lv.1（ランダム）で最後まで打つ
let s = engine.newGame();
let moves = 0;
while (s.legal.length || s.opponentHasMove) {
  if (!s.legal.length) {
    s = engine.getState(s.black, s.white, -s.color);
    continue;
  }
  const r = engine.aiMove(s.black, s.white, s.color, s.color === 1 ? "5" : "1", 4, 0.05);
  ok(isLegal(s, r.move), "対局中の手がすべて合法");
  s = engine.play(s.black, s.white, s.color, r.move[0], r.move[1]);
  moves++;
}
ok(s.blackCount + s.whiteCount <= 64 && moves > 0, "終局まで打てる");

// 終盤は完全読みする: 毎回同じ手を打つ Lv.4 同士で空きマス12以下まで進め、Lv.5 に読ませる
let e = engine.newGame();
while (e.legal.length && 64 - e.blackCount - e.whiteCount > 12) {
  const r = engine.aiMove(e.black, e.white, e.color, "4", 2, 1.0);
  e = engine.play(e.black, e.white, e.color, r.move[0], r.move[1]);
  if (!e.legal.length && e.opponentHasMove) e = engine.getState(e.black, e.white, -e.color);
}
ok(e.legal.length > 1, "読み切りを確かめる局面に打てる手が複数ある（1つだと読まずに返すため）");
const endgame = engine.aiMove(e.black, e.white, e.color, "5", 4, 5.0);
ok(endgame.solved && isLegal(e, endgame.move), "空きマス12以下の局面を終局まで読み切る");

console.log(`smoke test: ${checks} 件の確認がすべて通りました（${moves} 手、黒 ${s.blackCount} - ${s.whiteCount} 白）`);
