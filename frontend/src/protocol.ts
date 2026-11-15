// メインスレッドと Worker の間でやり取りするデータの型

export type Color = 1 | -1;
export type Move = [number, number];

export interface GameState {
  black: string; // 64ビットの盤面（10進文字列）
  white: string;
  color: Color; // 次の手番
  blackCount: number;
  whiteCount: number;
  legal: Move[];
  opponentHasMove: boolean;
  flipped: Move[]; // 直前の手で裏返った石
}

export interface AiMoveResult {
  move: Move | null;
  ms: number;
  nodes: number | null;
  depth: number | null; // 読んだ深さ（Lv.5 は時間内に到達した深さ）
  solved: boolean; // 終局まで読み切ったか
  book: boolean; // 定石（事前に深く読んだ手の表）から選んだ手か
}

export interface OpeningName {
  name: string | null; // 例: "虎（Tiger）"。どの定石にも当てはまらなければ null
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
  | { type: "ready"; pythonVersion: string }
  | { type: "progress"; message: string }
  | { type: "init-error"; message: string }
  | { type: "result"; id: number; result: string }
  | { type: "error"; id: number; message: string };
