// Web worker that loads and runs the Rust engine (WebAssembly).
// Running the search off the main thread keeps the page responsive while the AI thinks.
import type { WorkerMessage, WorkerRequest } from "./protocol.js";
import { WasmEngine } from "./wasm-engine.js";

const post = (msg: WorkerMessage) => (self as unknown as Worker).postMessage(msg);

async function fetchAsset(name: string): Promise<Response> {
  // add the build version (?v=...) so cached old files are never mixed in
  const res = await fetch(new URL(`./engine/${name}${self.location.search}`, self.location.href));
  if (!res.ok) throw new Error(`could not fetch ${name} (${res.status})`);
  return res;
}

async function init(): Promise<WasmEngine> {
  post({ type: "progress", message: "Loading the AI engine…" });
  const [wasm, patterns, book] = await Promise.all([
    fetchAsset("reversi_engine.wasm").then((r) => r.arrayBuffer()),
    fetchAsset("pattern_weights.bin").then((r) => r.arrayBuffer()),
    fetchAsset("opening_book.txt").then((r) => r.text()),
  ]);
  const engine = await WasmEngine.create({ wasm, patterns, book }, () => performance.now());
  post({ type: "ready", runtime: `Rust (WebAssembly)${engine.usesPatterns ? " · pattern evaluation" : ""}` });
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
