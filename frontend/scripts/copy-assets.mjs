// ビルド成果物 dist/ に HTML・CSS と、ブラウザで動かす Python エンジンをコピーする
import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
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
  "ai_manager.py",
  "web_api.py",
];

mkdirSync(join(dist, "py"), { recursive: true });
for (const f of ["index.html", "style.css"]) copyFileSync(join(root, f), join(dist, f));
for (const f of PY_MODULES) copyFileSync(join(backend, f), join(dist, "py", f));
// Worker はこの一覧を見て Python モジュールを読み込む
writeFileSync(join(dist, "py", "manifest.json"), JSON.stringify(PY_MODULES));
console.log(`copied ${PY_MODULES.length} Python modules to dist/py`);
