// Pyodide（ブラウザで動く CPython）を読み込み、backend/ の Python エンジンをそのまま実行する Web Worker。
// 重い探索をメインスレッドから切り離すことで、AI の思考中も画面が固まらない。
import type { WorkerMessage, WorkerRequest } from "./protocol.js";

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

interface PyProxy {
  (...args: unknown[]): unknown;
}
interface Pyodide {
  FS: { writeFile(path: string, data: string): void };
  pyimport(name: string): Record<string, PyProxy>;
  runPython(code: string): unknown;
}

const post = (msg: WorkerMessage) => (self as unknown as Worker).postMessage(msg);

async function init(): Promise<Record<string, PyProxy>> {
  post({ type: "progress", message: "Python ランタイムを読み込み中…" });
  const { loadPyodide } = (await import(`${PYODIDE_URL}pyodide.mjs`)) as {
    loadPyodide: (opts: { indexURL: string }) => Promise<Pyodide>;
  };
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

  post({ type: "progress", message: "AI エンジンを読み込み中…" });
  const manifest = await fetch(new URL("./py/manifest.json", self.location.href));
  const modules = (await manifest.json()) as string[];
  const sources = await Promise.all(
    modules.map(async (name) => {
      const res = await fetch(new URL(`./py/${name}`, self.location.href));
      if (!res.ok) throw new Error(`${name} を取得できません (${res.status})`);
      return [name, await res.text()] as const;
    }),
  );
  for (const [name, code] of sources) pyodide.FS.writeFile(`/home/pyodide/${name}`, code);

  const api = pyodide.pyimport("web_api");
  const version = String(pyodide.runPython("import sys; sys.version.split()[0]"));
  post({ type: "ready", pythonVersion: version });
  return api;
}

const ready = init().catch((e: unknown) => {
  post({ type: "init-error", message: e instanceof Error ? e.message : String(e) });
  throw e;
});

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const { id, fn, args } = event.data;
  try {
    const api = await ready;
    const result = String(api[fn](...args));
    post({ type: "result", id, result });
  } catch (e) {
    post({ type: "error", id, message: e instanceof Error ? e.message : String(e) });
  }
};
