// Rust 版エンジン（backend_rust を WebAssembly にしたもの）の薄いラッパー。
// ブラウザの Web Worker と、Node での動作確認（scripts/smoke-test.mjs）の両方から使う。
// 返す値の形は以前の Python 版 Web API（backend/web_api.py）と同じなので、画面側（app.ts）はそのまま使える。
import type { AiMoveResult, Analysis, ApiFunction, Color, GameState, Move, MoveScore, OpeningName } from "./protocol.js";

/** Rust 側が公開している関数（backend_rust/src/wasm.rs） */
interface Exports {
  memory: WebAssembly.Memory;
  alloc(len: number): number;
  dealloc(ptr: number, len: number): void;
  load_patterns(ptr: number, len: number): number;
  load_book(ptr: number, len: number): number;
  legal_moves(p: bigint, o: bigint): bigint;
  flips(p: bigint, o: bigint, x: bigint): bigint;
  ai_move(black: bigint, white: bigint, color: number, level: number, depth: number, timeLimit: number, seed: bigint): bigint;
  analyze(black: bigint, white: bigint, color: number, depth: number): number;
  opening(ptr: number, len: number): number;
  result_ptr(): number;
  text_ptr(): number;
  has_patterns(): number;
}

export interface EngineAssets {
  wasm: BufferSource;
  /** パターン評価の重み（pattern_weights.bin）。なければ線形評価で読む */
  patterns?: ArrayBuffer;
  /** 定石（opening_book.txt）。なければ定石なし */
  book?: string;
}

const WIN_SCORE = 10_000;
const START_BLACK = 0x0000000810000000n;
const START_WHITE = 0x0000001008000000n;
// wasm の i64 は符号つきで返ってくるので、64 ビットの符号なし整数に直す
const u64 = (x: bigint) => BigInt.asUintN(64, x);

function popcount(b: bigint): number {
  let n = 0;
  while (b) {
    b &= b - 1n;
    n++;
  }
  return n;
}

/** 立っているビットのマス番号（小さい順） */
function squares(b: bigint): number[] {
  const out: number[] = [];
  for (let i = 0; i < 64; i++) if ((b >> BigInt(i)) & 1n) out.push(i);
  return out;
}

const toMove = (i: number): Move => [Math.floor(i / 8), i % 8];

export class WasmEngine {
  private constructor(private readonly x: Exports) {}

  /** `now` は時刻（ミリ秒）を返す関数（performance.now）。Rust 側が持ち時間の計算に使う */
  static async create(assets: EngineAssets, now: () => number): Promise<WasmEngine> {
    const { instance } = await WebAssembly.instantiate(assets.wasm, { env: { now_ms: now } });
    const engine = new WasmEngine(instance.exports as unknown as Exports);
    if (assets.patterns && engine.load(assets.patterns, (p, n) => engine.x.load_patterns(p, n)) !== 0) {
      throw new Error("パターン評価の重みファイルを読み込めませんでした");
    }
    if (assets.book && engine.load(new TextEncoder().encode(assets.book), (p, n) => engine.x.load_book(p, n)) !== 0) {
      throw new Error("定石ファイルを読み込めませんでした");
    }
    return engine;
  }

  get usesPatterns(): boolean {
    return this.x.has_patterns() === 1;
  }

  /** バイト列を wasm のメモリにコピーして `fn(位置, 長さ)` を呼ぶ */
  private load(data: ArrayBuffer | Uint8Array, fn: (ptr: number, len: number) => number): number {
    const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
    const ptr = this.x.alloc(bytes.length);
    try {
      new Uint8Array(this.x.memory.buffer, ptr, bytes.length).set(bytes);
      return fn(ptr, bytes.length);
    } finally {
      this.x.dealloc(ptr, bytes.length);
    }
  }

  private results(n: number): Float64Array {
    return new Float64Array(this.x.memory.buffer, this.x.result_ptr(), n);
  }

  private sides(black: bigint, white: bigint, color: Color): [bigint, bigint] {
    return color === 1 ? [black, white] : [white, black];
  }

  private state(black: bigint, white: bigint, color: Color, flipped = 0n): GameState {
    const [p, o] = this.sides(black, white, color);
    return {
      black: black.toString(),
      white: white.toString(),
      color,
      blackCount: popcount(black),
      whiteCount: popcount(white),
      legal: squares(u64(this.x.legal_moves(p, o))).map(toMove),
      opponentHasMove: u64(this.x.legal_moves(o, p)) !== 0n,
      flipped: squares(flipped).map(toMove),
    };
  }

  newGame(): GameState {
    return this.state(START_BLACK, START_WHITE, 1);
  }

  getState(black: string, white: string, color: Color): GameState {
    return this.state(BigInt(black), BigInt(white), color);
  }

  /** color が (row, col) に打った後の盤面。手番は相手に移る */
  play(black: string, white: string, color: Color, row: number, col: number): GameState | { error: string } {
    const [b, w] = [BigInt(black), BigInt(white)];
    const [p, o] = this.sides(b, w, color);
    const x = 1n << BigInt(row * 8 + col);
    if (!(u64(this.x.legal_moves(p, o)) & x)) return { error: "illegal move" };
    const f = u64(this.x.flips(p, o, x));
    const [np, no] = [p | x | f, o ^ f];
    const [nb, nw] = color === 1 ? [np, no] : [no, np];
    return this.state(nb, nw, -color as Color, f);
  }

  aiMove(black: string, white: string, color: Color, level: string, depth: number, timeLimit: number): AiMoveResult {
    const seed = BigInt(Math.floor(Math.random() * 2 ** 32)) * 4294967296n + BigInt(Math.floor(Math.random() * 2 ** 32));
    const start = performance.now();
    const move = u64(this.x.ai_move(BigInt(black), BigInt(white), color, Number(level), depth, timeLimit, seed));
    const ms = Math.round(performance.now() - start);
    const [nodes, readDepth, solved, book] = this.results(4);
    return {
      move: move ? toMove(squares(move)[0]) : null,
      ms,
      nodes: nodes < 0 ? null : nodes,
      depth: readDepth < 0 ? null : readDepth,
      solved: solved === 1,
      book: book === 1,
    };
  }

  /** 手番側の全合法手の評価値（Lv.4 と同じ評価） */
  analyze(black: string, white: string, color: Color, depth: number): Analysis {
    const start = performance.now();
    const n = this.x.analyze(BigInt(black), BigInt(white), color, depth);
    const ms = Math.round(performance.now() - start);
    const r = this.results(1 + 2 * n);
    const moves: MoveScore[] = [];
    for (let i = 0; i < n; i++) {
      const [row, col] = toMove(r[1 + 2 * i]);
      const score = r[2 + 2 * i];
      const outcome = score >= WIN_SCORE ? "win" : score <= -WIN_SCORE ? "loss" : null;
      moves.push({
        row,
        col,
        score: Math.round(score * 100) / 100,
        outcome,
        discDiff: outcome === "win" ? Math.trunc(score - WIN_SCORE) : outcome === "loss" ? Math.trunc(score + WIN_SCORE) : null,
      });
    }
    return { moves, ms, nodes: r[0], depth };
  }

  /** 棋譜（"f5d6c3..."、パスは含めない）に一致する定石名 */
  opening(transcript: string): OpeningName {
    const bytes = new TextEncoder().encode(transcript);
    const len = bytes.length ? this.load(bytes, (p, n) => this.x.opening(p, n)) : -1;
    if (len < 0) return { name: null };
    return { name: new TextDecoder().decode(new Uint8Array(this.x.memory.buffer, this.x.text_ptr(), len)) };
  }

  /** Worker からの呼び出しを振り分ける（引数は以前の Python 版 API と同じ並び） */
  call(fn: ApiFunction, args: (string | number)[]): unknown {
    const a = args as never[];
    switch (fn) {
      case "new_game":
        return this.newGame();
      case "get_state":
        return this.getState(a[0], a[1], a[2]);
      case "play":
        return this.play(a[0], a[1], a[2], a[3], a[4]);
      case "ai_move":
        return this.aiMove(a[0], a[1], a[2], String(a[3]), a[4], a[5] ?? 1.0);
      case "analyze":
        return this.analyze(a[0], a[1], a[2], a[3]);
      case "opening":
        return this.opening(a[0]);
    }
  }
}
