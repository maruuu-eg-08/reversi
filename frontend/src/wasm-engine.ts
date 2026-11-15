// Thin wrapper around the Rust engine (backend_rust compiled to WebAssembly).
// Used both by the browser's web worker and by the Node check (scripts/smoke-test.mjs).
// It returns values shaped like the former Python web API (backend/web_api.py), so app.ts works unchanged.
import type { AiMoveResult, Analysis, ApiFunction, Color, GameState, Move, MoveScore, OpeningName } from "./protocol.js";

/** Functions exported by Rust (backend_rust/src/wasm.rs) */
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
  /** Pattern weights (pattern_weights.bin); without them the linear evaluation is used */
  patterns?: ArrayBuffer;
  /** Opening book (opening_book.txt); without it there is no book */
  book?: string;
}

const WIN_SCORE = 10_000;
const START_BLACK = 0x0000000810000000n;
const START_WHITE = 0x0000001008000000n;
// wasm returns i64 values as signed, so convert them to unsigned 64-bit integers
const u64 = (x: bigint) => BigInt.asUintN(64, x);

function popcount(b: bigint): number {
  let n = 0;
  while (b) {
    b &= b - 1n;
    n++;
  }
  return n;
}

/** Indices of the set bits, in increasing order */
function squares(b: bigint): number[] {
  const out: number[] = [];
  for (let i = 0; i < 64; i++) if ((b >> BigInt(i)) & 1n) out.push(i);
  return out;
}

const toMove = (i: number): Move => [Math.floor(i / 8), i % 8];

export class WasmEngine {
  private constructor(private readonly x: Exports) {}

  /** `now` returns the time in milliseconds (performance.now); Rust uses it for the time limit */
  static async create(assets: EngineAssets, now: () => number): Promise<WasmEngine> {
    const { instance } = await WebAssembly.instantiate(assets.wasm, { env: { now_ms: now } });
    const engine = new WasmEngine(instance.exports as unknown as Exports);
    if (assets.patterns && engine.load(assets.patterns, (p, n) => engine.x.load_patterns(p, n)) !== 0) {
      throw new Error("could not load the pattern weights");
    }
    if (assets.book && engine.load(new TextEncoder().encode(assets.book), (p, n) => engine.x.load_book(p, n)) !== 0) {
      throw new Error("could not load the opening book");
    }
    return engine;
  }

  get usesPatterns(): boolean {
    return this.x.has_patterns() === 1;
  }

  /** Copy bytes into wasm memory and call `fn(address, length)` */
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

  /** Board after color plays (row, col); the opponent is to move next */
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

  /** Scores of every legal move of the side to move (same evaluation as Lv.4) */
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

  /** Opening name matching a record ("f5d6c3...", no passes) */
  opening(transcript: string): OpeningName {
    const bytes = new TextEncoder().encode(transcript);
    const len = bytes.length ? this.load(bytes, (p, n) => this.x.opening(p, n)) : -1;
    if (len < 0) return { name: null };
    return { name: new TextDecoder().decode(new Uint8Array(this.x.memory.buffer, this.x.text_ptr(), len)) };
  }

  /** Dispatch calls from the worker (arguments in the same order as the former Python API) */
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
