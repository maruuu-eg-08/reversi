// Rust 版エンジン（WebAssembly）を読み込んで実行する Web Worker。
// 重い探索をメインスレッドから切り離すことで、AI の思考中も画面が固まらない。
import type { WorkerMessage, WorkerRequest } from "./protocol.js";
import { WasmEngine } from "./wasm-engine.js";

const post = (msg: WorkerMessage) => (self as unknown as Worker).postMessage(msg);

async function fetchAsset(name: string): Promise<Response> {
  // ビルド時に付けたバージョン（?v=...）を付けて、古いキャッシュと混ざらないようにする
  const res = await fetch(new URL(`./engine/${name}${self.location.search}`, self.location.href));
  if (!res.ok) throw new Error(`${name} を取得できません (${res.status})`);
  return res;
}

async function init(): Promise<WasmEngine> {
  post({ type: "progress", message: "AI エンジンを読み込み中…" });
  const [wasm, patterns, book] = await Promise.all([
    fetchAsset("reversi_engine.wasm").then((r) => r.arrayBuffer()),
    fetchAsset("pattern_weights.bin").then((r) => r.arrayBuffer()),
    fetchAsset("opening_book.txt").then((r) => r.text()),
  ]);
  const engine = await WasmEngine.create({ wasm, patterns, book }, () => performance.now());
  post({ type: "ready", runtime: `Rust（WebAssembly）${engine.usesPatterns ? "・パターン評価" : ""}` });
  return engine;
}

const ready = init().catch((e: unknown) => {
  post({ type: "init-error", message: e instanceof Error ? e.message : String(e) });
  throw e;
});

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const { id, fn, args } = event.data;
  try {
    const engine = await ready;
    post({ type: "result", id, result: JSON.stringify(engine.call(fn, args)) });
  } catch (e) {
    post({ type: "error", id, message: e instanceof Error ? e.message : String(e) });
  }
};
