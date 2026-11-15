// ビルド成果物 dist/ に HTML・CSS と、ブラウザで動かす Python エンジンをコピーし、
// 全ファイルの URL にバージョン（内容のハッシュ）を付ける。
//
// GitHub Pages は各ファイルを10分キャッシュするため、そのままだと公開直後に
// 「新しい HTML + 古い JS」のような組み合わせで読み込まれて壊れることがある。
// URL にバージョンを付けると、1つの HTML からは必ず同じビルドのファイルだけが読まれる。
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const backend = join(root, "..", "backend");

const PY_MODULES = [
  "bitboard.py",
  "weights.py",
  "random_ai.py",
  "weighted_ai.py",
  "minimax.py",
  "alphabeta_ai.py",
  "strong_ai.py",
  "opening_book.py",
  "openings.py",
  "ai_manager.py",
  "web_api.py",
];
// Python から読み込むデータファイル（定石の表）
const PY_DATA = ["opening_book.txt"];
const PY_FILES = [...PY_MODULES, ...PY_DATA];

mkdirSync(join(dist, "py"), { recursive: true });
for (const f of ["index.html", "style.css"]) copyFileSync(join(root, f), join(dist, f));
for (const f of PY_FILES) copyFileSync(join(backend, f), join(dist, "py", f));
// Worker はこの一覧を見て Python のファイルを読み込む
writeFileSync(join(dist, "py", "manifest.json"), JSON.stringify(PY_FILES));
console.log(`copied ${PY_MODULES.length} Python modules and ${PY_DATA.length} data files to dist/py`);

// ---------- バージョン付け ----------
const jsFiles = readdirSync(dist).filter((f) => f.endsWith(".js")).sort();
const hash = createHash("sha256");
for (const f of [...jsFiles, "index.html", "style.css"]) hash.update(readFileSync(join(dist, f)));
for (const f of PY_FILES) hash.update(readFileSync(join(dist, "py", f)));
const v = `?v=${hash.digest("hex").slice(0, 10)}`;

function stamp(file, pattern, replacer, expected) {
  const path = join(dist, file);
  const src = readFileSync(path, "utf8");
  let count = 0;
  const out = src.replace(pattern, (...m) => {
    count++;
    return replacer(...m);
  });
  if (count < expected) throw new Error(`${file}: バージョンを付ける箇所が ${count} 件しかありません（期待 ${expected} 件以上）`);
  writeFileSync(path, out);
}

stamp("index.html", /(href="style\.css|src="app\.js)"/g, (_, p) => `${p}${v}"`, 2);
// JS 同士の相対 import（例: from "./engine.js"）
for (const f of jsFiles) {
  stamp(f, /((?:from|import)\s*["']\.\/[\w-]+\.js)(["'])/g, (_, p, q) => `${p}${v}${q}`, 0);
}
// 版の付いていない相対 import が残っていないか確認する
for (const f of jsFiles) {
  const left = readFileSync(join(dist, f), "utf8").match(/(?:from|import)\s*["']\.\/[\w-]+\.js["']/g);
  if (left) throw new Error(`${f}: バージョンなしの import が残っています: ${left.join(", ")}`);
}
console.log(`stamped assets with ${v}`);
