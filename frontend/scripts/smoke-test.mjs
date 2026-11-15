// Run the built web engine (dist/engine/*.wasm and dist/wasm-engine.js) in Node.
// It uses the same code as the browser, so CI can check that the build actually works.
// Usage: npm run build && npm test
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

ok(engine.usesPatterns, "pattern weights are loaded");

// start position
const start = engine.newGame();
ok(start.color === 1 && start.blackCount === 2 && start.whiteCount === 2, "disc counts at the start");
assert.deepEqual(start.legal, [[2, 3], [3, 2], [4, 5], [5, 4]]);
checks++;

// legal and illegal moves
const s1 = engine.play(start.black, start.white, 1, 2, 3);
ok(s1.color === -1 && s1.blackCount === 4 && s1.whiteCount === 1, "d3 makes it 4 to 1");
assert.deepEqual(s1.flipped, [[3, 3]]);
checks++;
ok("error" in engine.play(start.black, start.white, 1, 0, 0), "a1 is not legal");

// every level's AI returns a legal move
const isLegal = (s, m) => s.legal.some(([r, c]) => r === m[0] && c === m[1]);
for (const level of ["1", "2", "3", "4", "5"]) {
  const r = engine.aiMove(start.black, start.white, 1, level, 3, 0.2);
  ok(r.move && isLegal(start, r.move), `Lv.${level} plays a legal move`);
}
const lv5 = engine.aiMove(start.black, start.white, 1, "5", 4, 1.0);
ok(lv5.book === true, "Lv.5 uses the book at the start");

// analysis (best first)
const a = engine.analyze(s1.black, s1.white, -1, 3);
ok(a.moves.length === s1.legal.length && a.nodes > 0, "the analysis covers every legal move");
ok(a.moves.every((m, i) => i === 0 || a.moves[i - 1].score >= m.score), "the analysis is sorted best first");

// opening names
ok(engine.opening("f5d6c3d3c4").name === "Tiger", "recognizes the Tiger");
ok(engine.opening("").name === null && engine.opening("a1").name === null, "non-openings give null");

// play to the end: Lv.5 (short time limit) against Lv.1 (random)
let s = engine.newGame();
let moves = 0;
while (s.legal.length || s.opponentHasMove) {
  if (!s.legal.length) {
    s = engine.getState(s.black, s.white, -s.color);
    continue;
  }
  const r = engine.aiMove(s.black, s.white, s.color, s.color === 1 ? "5" : "1", 4, 0.05);
  ok(isLegal(s, r.move), "every move in the game is legal");
  s = engine.play(s.black, s.white, s.color, r.move[0], r.move[1]);
  moves++;
}
ok(s.blackCount + s.whiteCount <= 64 && moves > 0, "the game can be played to the end");

// the endgame is solved exactly: reach <= 12 empties with deterministic Lv.4 play, then ask Lv.5
let e = engine.newGame();
while (e.legal.length && 64 - e.blackCount - e.whiteCount > 12) {
  const r = engine.aiMove(e.black, e.white, e.color, "4", 2, 1.0);
  e = engine.play(e.black, e.white, e.color, r.move[0], r.move[1]);
  if (!e.legal.length && e.opponentHasMove) e = engine.getState(e.black, e.white, -e.color);
}
ok(e.legal.length > 1, "the endgame test position has several legal moves (a single move is returned without searching)");
const endgame = engine.aiMove(e.black, e.white, e.color, "5", 4, 5.0);
ok(endgame.solved && isLegal(e, endgame.move), "a position with 12 or fewer empties is solved exactly");

console.log(`smoke test: all ${checks} checks passed (${moves} moves, black ${s.blackCount} - ${s.whiteCount} white)`);
