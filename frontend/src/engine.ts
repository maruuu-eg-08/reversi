// Worker に処理を依頼し、結果を Promise で受け取るためのクライアント
import type {
  AiMoveResult,
  Analysis,
  ApiFunction,
  Color,
  GameState,
  WorkerMessage,
} from "./protocol.js";

export class Engine {
  // ビルド時に付けたバージョン（?v=...）を Worker にも引き継ぎ、古いキャッシュと混ざらないようにする
  private worker = new Worker(new URL(`./worker.js${new URL(import.meta.url).search}`, import.meta.url), {
    type: "module",
  });
  private nextId = 0;
  private pending = new Map<number, { resolve: (v: string) => void; reject: (e: Error) => void }>();
  readonly ready: Promise<string>;

  constructor(onProgress: (message: string) => void) {
    this.ready = new Promise((resolve, reject) => {
      this.worker.onmessage = (event: MessageEvent<WorkerMessage>) => {
        const msg = event.data;
        switch (msg.type) {
          case "progress":
            onProgress(msg.message);
            break;
          case "ready":
            resolve(msg.pythonVersion);
            break;
          case "init-error":
            reject(new Error(msg.message));
            break;
          case "result":
            this.pending.get(msg.id)?.resolve(msg.result);
            this.pending.delete(msg.id);
            break;
          case "error":
            this.pending.get(msg.id)?.reject(new Error(msg.message));
            this.pending.delete(msg.id);
            break;
        }
      };
    });
  }

  private async call<T>(fn: ApiFunction, ...args: (string | number)[]): Promise<T> {
    const id = this.nextId++;
    const raw = await new Promise<string>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, fn, args });
    });
    const parsed = JSON.parse(raw) as T & { error?: string };
    if (parsed.error) throw new Error(parsed.error);
    return parsed;
  }

  newGame() {
    return this.call<GameState>("new_game");
  }
  getState(s: GameState, color: Color) {
    return this.call<GameState>("get_state", s.black, s.white, color);
  }
  play(s: GameState, row: number, col: number) {
    return this.call<GameState>("play", s.black, s.white, s.color, row, col);
  }
  aiMove(s: GameState, level: string, depth: number, timeLimit: number) {
    return this.call<AiMoveResult>("ai_move", s.black, s.white, s.color, level, depth, timeLimit);
  }
  analyze(s: GameState, depth: number) {
    return this.call<Analysis>("analyze", s.black, s.white, s.color, depth);
  }
}
