// Copy the HTML, CSS, the Rust engine (WebAssembly) and its data (pattern weights, opening book)
// into dist/ and add a version (a content hash) to every file URL.
//
// GitHub Pages caches each file for 10 minutes, so right after a deploy a browser could combine
// e.g. a new HTML file with old JS and break.
// With versioned URLs, one HTML file only ever loads files from the same build.
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
const backend = join(root, "..", "backend");
const wasmDir = join(root, "..", "backend_rust", "target", "wasm32-unknown-unknown", "release");

// Files the worker (src/worker.ts) loads from dist/engine/
const ENGINE_FILES = [
  [join(wasmDir, "reversi_engine.wasm"), "reversi_engine.wasm"],
  [join(backend, "pattern_weights.bin"), "pattern_weights.bin"],
  [join(backend, "opening_book.txt"), "opening_book.txt"],
];

mkdirSync(join(dist, "engine"), { recursive: true });
for (const f of ["index.html", "style.css"]) copyFileSync(join(root, f), join(dist, f));
for (const [src, name] of ENGINE_FILES) copyFileSync(src, join(dist, "engine", name));
console.log(`copied ${ENGINE_FILES.length} engine files to dist/engine`);

// ---------- versioning ----------
const jsFiles = readdirSync(dist).filter((f) => f.endsWith(".js")).sort();
const hash = createHash("sha256");
for (const f of [...jsFiles, "index.html", "style.css"]) hash.update(readFileSync(join(dist, f)));
for (const [, name] of ENGINE_FILES) hash.update(readFileSync(join(dist, "engine", name)));
const v = `?v=${hash.digest("hex").slice(0, 10)}`;

function stamp(file, pattern, replacer, expected) {
  const path = join(dist, file);
  const src = readFileSync(path, "utf8");
  let count = 0;
  const out = src.replace(pattern, (...m) => {
    count++;
    return replacer(...m);
  });
  if (count < expected) throw new Error(`${file}: only ${count} place(s) to stamp a version (expected at least ${expected})`);
  writeFileSync(path, out);
}

stamp("index.html", /(href="style\.css|src="app\.js)"/g, (_, p) => `${p}${v}"`, 2);
// relative imports between JS files (e.g. from "./engine.js")
for (const f of jsFiles) {
  stamp(f, /((?:from|import)\s*["']\.\/[\w-]+\.js)(["'])/g, (_, p, q) => `${p}${v}${q}`, 0);
}
// make sure no unversioned relative import is left
for (const f of jsFiles) {
  const left = readFileSync(join(dist, f), "utf8").match(/(?:from|import)\s*["']\.\/[\w-]+\.js["']/g);
  if (left) throw new Error(`${f}: unversioned imports remain: ${left.join(", ")}`);
}
console.log(`stamped assets with ${v}`);
