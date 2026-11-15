// Types of the data exchanged between the main thread and the worker

export type Color = 1 | -1;
export type Move = [number, number];

export interface GameState {
  black: string; // 64-bit board (decimal string)
  white: string;
  color: Color; // side to move
  blackCount: number;
  whiteCount: number;
  legal: Move[];
  opponentHasMove: boolean;
  flipped: Move[]; // discs flipped by the last move
}

export interface AiMoveResult {
  move: Move | null;
  ms: number;
  nodes: number | null;
  depth: number | null; // search depth (for Lv.5, the depth reached within the time limit)
  solved: boolean; // whether the game was solved to the end
  book: boolean; // whether the move came from the opening book (moves searched deeply in advance)
}

export interface OpeningName {
  name: string | null; // e.g. "Tiger"; null if no named opening matches
}

export interface MoveScore {
  row: number;
  col: number;
  score: number;
  outcome: "win" | "loss" | null;
  discDiff: number | null;
}

export interface Analysis {
  moves: MoveScore[];
  ms: number;
  nodes: number;
  depth: number;
}

export type ApiFunction = "new_game" | "get_state" | "play" | "ai_move" | "analyze" | "opening";

export interface WorkerRequest {
  id: number;
  fn: ApiFunction;
  args: (string | number)[];
}

export type WorkerMessage =
  | { type: "ready"; runtime: string }
  | { type: "progress"; message: string }
  | { type: "init-error"; message: string }
  | { type: "result"; id: number; result: string }
  | { type: "error"; id: number; message: string };
