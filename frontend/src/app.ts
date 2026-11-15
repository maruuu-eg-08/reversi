import { Engine } from "./engine.js";
import type { Analysis, Color, GameState, Move, MoveScore } from "./protocol.js";

// ---------- DOM ----------
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const boardEl = $<HTMLDivElement>("board");
const loadingEl = $<HTMLDivElement>("loading");
const loadingText = $<HTMLParagraphElement>("loading-text");
const statusEl = $<HTMLParagraphElement>("status");
const newGameBtn = $<HTMLButtonElement>("new-game");
const levelSel = $<HTMLSelectElement>("level");
const depthInput = $<HTMLInputElement>("depth");
const depthValue = $<HTMLOutputElement>("depth-value");
const showAnalysisInput = $<HTMLInputElement>("show-analysis");
const showEvalInput = $<HTMLInputElement>("show-eval");
const analysisList = $<HTMLOListElement>("analysis-list");

const COLS = "abcdefgh";
const colorName = (c: Color) => (c === 1 ? "黒" : "白");
const notation = (row: number, col: number) => `${COLS[col]}${row + 1}`;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const AI_TIME_LIMIT = 1.0; // Lv.5 が1手に使う時間（秒）

// ---------- 状態 ----------
let state: GameState | null = null;
let humanColor: Color = 1;
let gameId = 0; // 新しい対局を始めたら古い非同期処理の結果を捨てるための番号
let busy = false;
let lastMove: Move | null = null;
let analysis: Analysis | null = null;

const engine = new Engine((message) => (loadingText.textContent = message));

// ---------- 表示設定（ブラウザに保存。保存できない環境でも動くようにする） ----------
const PREFS_KEY = "reversi-prefs";
function loadPrefs() {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as Record<string, unknown>;
    if (typeof p.showEval === "boolean") showEvalInput.checked = p.showEval;
    if (typeof p.showAnalysis === "boolean") showAnalysisInput.checked = p.showAnalysis;
  } catch {
    // 既定値のまま
  }
}
function savePrefs() {
  try {
    localStorage.setItem(
      PREFS_KEY,
      JSON.stringify({ showEval: showEvalInput.checked, showAnalysis: showAnalysisInput.checked }),
    );
  } catch {
    // 保存できなくても表示は切り替わる
  }
}
loadPrefs();

// 盤面の数字か読み筋リストのどちらかを表示するなら、分析が必要
const wantAnalysis = () => showEvalInput.checked || showAnalysisInput.checked;

// ---------- 盤面の生成 ----------
const cells: HTMLButtonElement[] = [];
for (let row = 0; row < 8; row++) {
  for (let col = 0; col < 8; col++) {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "cell";
    cell.dataset.row = String(row);
    cell.dataset.col = String(col);
    cell.addEventListener("click", () => void onCellClick(row, col));
    boardEl.appendChild(cell);
    cells.push(cell);
  }
}

function bitAt(bits: string, index: number): boolean {
  return ((BigInt(bits) >> BigInt(index)) & 1n) === 1n;
}

// 評価値を色（良い=緑, 悪い=赤）に変換する。同じ評価値は同じ色になるよう、異なる値の順位で決める
function heatColor(score: number, distinct: number[]): string {
  const idx = distinct.indexOf(score);
  const t = distinct.length <= 1 ? 1 : 1 - idx / (distinct.length - 1);
  const hue = Math.round(t * 140);
  return `hsla(${hue}, 70%, 40%, 0.88)`;
}

function scoreLabel(m: MoveScore): string {
  if (m.outcome === "win") return `勝+${m.discDiff}`;
  if (m.outcome === "loss") return `負${m.discDiff}`;
  const v = Math.round(m.score);
  return v > 0 ? `+${v}` : String(v);
}

// ---------- 描画 ----------
function render(animate = false) {
  if (!state) return;
  const s = state;
  const legal = new Set(s.legal.map(([r, c]) => r * 8 + c));
  const flipped = new Set(s.flipped.map(([r, c]) => r * 8 + c));
  const humanTurn = s.color === humanColor && !busy;
  const scores = new Map<number, MoveScore>();
  let distinct: number[] = [];
  if (analysis && showEvalInput.checked && humanTurn) {
    analysis.moves.forEach((m) => scores.set(m.row * 8 + m.col, m));
    distinct = [...new Set(analysis.moves.map((m) => m.score))]; // 降順に並んでいる
  }

  cells.forEach((cell, i) => {
    const row = Math.floor(i / 8);
    const col = i % 8;
    const isBlack = bitAt(s.black, i);
    const isWhite = bitAt(s.white, i);
    const canPlay = humanTurn && legal.has(i);
    const isLast = lastMove !== null && lastMove[0] === row && lastMove[1] === col;

    cell.replaceChildren();
    cell.classList.toggle("legal", canPlay);
    cell.classList.toggle("last-move", isLast);
    cell.disabled = !canPlay;

    let label = notation(row, col);
    if (isBlack || isWhite) {
      const stone = document.createElement("span");
      stone.className = `stone ${isBlack ? "black" : "white"}`;
      if (animate && flipped.has(i)) stone.classList.add("flip");
      if (animate && isLast) stone.classList.add("placed");
      cell.appendChild(stone);
      label += isBlack ? " 黒" : " 白";
    } else if (canPlay) {
      const m = scores.get(i);
      if (m) {
        const ev = document.createElement("span");
        ev.className = "eval" + (m.score === distinct[0] ? " best" : "");
        ev.style.background = heatColor(m.score, distinct);
        ev.textContent = scoreLabel(m);
        cell.appendChild(ev);
        label += ` 打てる 評価 ${scoreLabel(m)}`;
      } else {
        const dot = document.createElement("span");
        dot.className = "hint-dot";
        cell.appendChild(dot);
        label += " 打てる";
      }
    }
    cell.setAttribute("aria-label", label);
  });

  $("count-black").textContent = String(s.blackCount);
  $("count-white").textContent = String(s.whiteCount);
  $("who-black").textContent = humanColor === 1 ? "(あなた)" : "(AI)";
  $("who-white").textContent = humanColor === -1 ? "(あなた)" : "(AI)";
  const over = s.legal.length === 0 && !s.opponentHasMove;
  $("player-black").classList.toggle("active", !over && s.color === 1);
  $("player-white").classList.toggle("active", !over && s.color === -1);

  renderAnalysisList();
}

function renderAnalysisList() {
  analysisList.replaceChildren();
  const li = (text: string, cls = "") => {
    const el = document.createElement("li");
    el.className = cls;
    el.textContent = text;
    analysisList.appendChild(el);
    return el;
  };
  if (!showAnalysisInput.checked) return;
  if (!state || state.color !== humanColor || busy) {
    li("あなたの番になると表示します", "empty");
    return;
  }
  if (!analysis) {
    li("分析中…", "empty");
    return;
  }
  const top = analysis.moves[0]?.score;
  analysis.moves.slice(0, 5).forEach((m, i) => {
    const el = li("", m.score === top ? "best" : "");
    const name = document.createElement("span");
    name.textContent = `${i + 1}. ${notation(m.row, m.col)}`;
    const score = document.createElement("span");
    score.textContent = scoreLabel(m);
    el.append(name, score);
  });
  li(`深さ ${analysis.depth} · ${analysis.nodes.toLocaleString()} 局面 · ${analysis.ms} ms`, "empty");
}

function setStatus(text: string) {
  statusEl.textContent = text;
}

// ---------- 対局の進行 ----------
async function startGame() {
  const id = ++gameId;
  humanColor = Number(
    (document.querySelector('input[name="human-color"]:checked') as HTMLInputElement).value,
  ) as Color;
  busy = false;
  lastMove = null;
  analysis = null;
  $("stat-ms").textContent = "–";
  $("stat-nodes").textContent = "–";
  $("stat-depth").textContent = "–";
  const s = await engine.newGame();
  if (id !== gameId) return;
  state = s;
  render();
  await advance(id);
}

async function advance(id: number) {
  while (state && id === gameId) {
    const s = state;
    if (s.legal.length === 0) {
      if (!s.opponentHasMove) {
        finishGame(s);
        return;
      }
      setStatus(`${colorName(s.color)}は打てる場所がないのでパスします`);
      await sleep(900);
      const next = await engine.getState(s, (-s.color) as Color);
      if (id !== gameId) return;
      state = next;
      render();
      continue;
    }

    if (s.color !== humanColor) {
      busy = true;
      setStatus("AI が考え中…");
      render();
      const level = levelSel.value;
      const depth = Number(depthInput.value);
      const [res] = await Promise.all([engine.aiMove(s, level, depth, AI_TIME_LIMIT), sleep(400)]);
      if (id !== gameId) return;
      $("stat-ms").textContent = `${res.ms.toLocaleString()} ms`;
      $("stat-nodes").textContent = res.nodes === null ? "–（探索なし）" : res.nodes.toLocaleString();
      $("stat-depth").textContent = res.solved
        ? `終局まで読み切り（${res.depth} 手先）`
        : res.depth
          ? `${res.depth} 手先まで`
          : "–";
      if (!res.move) throw new Error("AI が手を返しませんでした");
      const next = await engine.play(s, res.move[0], res.move[1]);
      if (id !== gameId) return;
      state = next;
      lastMove = res.move;
      analysis = null;
      busy = false;
      render(true);
      continue;
    }

    // 人間の番
    setStatus(`あなた（${colorName(humanColor)}）の番です`);
    analysis = null;
    render();
    if (wantAnalysis()) void requestAnalysis(id);
    return;
  }
}

async function requestAnalysis(id: number) {
  const s = state;
  if (!s || s.color !== humanColor) return;
  const result = await engine.analyze(s, Number(depthInput.value));
  if (id === gameId && state === s && !busy) {
    analysis = result;
    render();
  }
}

async function onCellClick(row: number, col: number) {
  const s = state;
  if (!s || busy || s.color !== humanColor) return;
  if (!s.legal.some(([r, c]) => r === row && c === col)) return;
  busy = true;
  const id = gameId;
  const next = await engine.play(s, row, col);
  if (id !== gameId) return;
  state = next;
  lastMove = [row, col];
  analysis = null;
  busy = false;
  render(true);
  await advance(id);
}

function finishGame(s: GameState) {
  const diff = s.blackCount - s.whiteCount;
  const humanDiff = diff * humanColor;
  const result = humanDiff > 0 ? "あなたの勝ち！" : humanDiff < 0 ? "AI の勝ち" : "引き分け";
  setStatus(`終局 — 黒 ${s.blackCount} : ${s.whiteCount} 白 · ${result}`);
  render();
}

// ---------- イベント ----------
newGameBtn.addEventListener("click", () => void startGame());
document.querySelectorAll('input[name="human-color"]').forEach((el) =>
  el.addEventListener("change", () => void startGame()),
);
depthInput.addEventListener("input", () => {
  depthValue.textContent = depthInput.value;
});
depthInput.addEventListener("change", () => {
  if (state && state.color === humanColor && !busy && wantAnalysis()) {
    analysis = null;
    render();
    void requestAnalysis(gameId);
  }
});
function onDisplayToggle() {
  savePrefs();
  render();
  if (wantAnalysis() && !analysis) void requestAnalysis(gameId);
}
showEvalInput.addEventListener("change", onDisplayToggle);
showAnalysisInput.addEventListener("change", onDisplayToggle);
// E キーで盤面の評価値を切り替える（入力欄の操作中は除く）
document.addEventListener("keydown", (e) => {
  if (e.key !== "e" && e.key !== "E") return;
  if (e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
  const t = e.target as HTMLElement | null;
  if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA") && t !== showEvalInput) return;
  showEvalInput.checked = !showEvalInput.checked;
  onDisplayToggle();
});

// ---------- 起動 ----------
engine.ready
  .then(async (version) => {
    $("runtime").textContent = `Python ${version}（Pyodide）`;
    loadingEl.hidden = true;
    newGameBtn.disabled = false;
    await startGame();
  })
  .catch((e: unknown) => {
    loadingText.textContent = `読み込みに失敗しました: ${e instanceof Error ? e.message : String(e)}`;
    setStatus("エンジンを読み込めませんでした。ページを再読み込みしてください。");
  });
