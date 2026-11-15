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
const undoBtn = $<HTMLButtonElement>("undo");
const recordEl = $<HTMLOListElement>("record");
const recordCount = $<HTMLSpanElement>("record-count");
const copyBtn = $<HTMLButtonElement>("copy-record");
const copyStatus = $<HTMLParagraphElement>("copy-status");
const openingNameEl = $<HTMLElement>("opening-name");
const COPY_HINT = copyStatus.textContent?.trim() ?? "";
const analysisList = $<HTMLOListElement>("analysis-list");

const COLS = "abcdefgh";
const colorName = (c: Color) => (c === 1 ? "Black" : "White");
const notation = (row: number, col: number) => `${COLS[col]}${row + 1}`;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const AI_TIME_LIMIT = 1.0; // seconds per move for Lv.5

// ---------- state ----------
let state: GameState | null = null;
let humanColor: Color = 1;
let gameId = 0; // bumped on every new game so stale async results are discarded
let busy = false;
let lastMove: Move | null = null;
let analysis: Analysis | null = null;

// game record (moves including passes)
interface Ply {
  color: Color;
  move: Move | null; // null means a pass
}
let plies: Ply[] = [];
let renderedPlies = -1;

// for undo: every position where it became your turn, in order
interface Snapshot {
  state: GameState;
  lastMove: Move | null;
  plies: number;
}
let snapshots: Snapshot[] = [];

const engine = new Engine((message) => (loadingText.textContent = message));

// ---------- display settings (saved in the browser; works without storage too) ----------
const PREFS_KEY = "reversi-prefs";
function loadPrefs() {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as Record<string, unknown>;
    if (typeof p.showEval === "boolean") showEvalInput.checked = p.showEval;
    if (typeof p.showAnalysis === "boolean") showAnalysisInput.checked = p.showAnalysis;
  } catch {
    // keep the defaults
  }
}
function savePrefs() {
  try {
    localStorage.setItem(
      PREFS_KEY,
      JSON.stringify({ showEval: showEvalInput.checked, showAnalysis: showAnalysisInput.checked }),
    );
  } catch {
    // the display still toggles even if saving fails
  }
}
loadPrefs();

// analysis is needed if either the board scores or the analysis list is shown
const wantAnalysis = () => showEvalInput.checked || showAnalysisInput.checked;

// ---------- board ----------
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

// Map a score to a color (green = good, red = bad), by rank among distinct scores so equal scores share a color
function heatColor(score: number, distinct: number[]): string {
  const idx = distinct.indexOf(score);
  const t = distinct.length <= 1 ? 1 : 1 - idx / (distinct.length - 1);
  const hue = Math.round(t * 140);
  return `hsla(${hue}, 70%, 40%, 0.88)`;
}

function scoreLabel(m: MoveScore): string {
  if (m.outcome === "win") return `W+${m.discDiff}`;
  if (m.outcome === "loss") return `L${m.discDiff}`;
  const v = Math.round(m.score);
  return v > 0 ? `+${v}` : String(v);
}

// ---------- rendering ----------
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
    distinct = [...new Set(analysis.moves.map((m) => m.score))]; // already sorted in descending order
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
      label += isBlack ? " black" : " white";
    } else if (canPlay) {
      const m = scores.get(i);
      if (m) {
        const ev = document.createElement("span");
        ev.className = "eval" + (m.score === distinct[0] ? " best" : "");
        ev.style.background = heatColor(m.score, distinct);
        ev.textContent = scoreLabel(m);
        cell.appendChild(ev);
        label += ` legal, score ${scoreLabel(m)}`;
      } else {
        const dot = document.createElement("span");
        dot.className = "hint-dot";
        cell.appendChild(dot);
        label += " legal";
      }
    }
    cell.setAttribute("aria-label", label);
  });

  $("count-black").textContent = String(s.blackCount);
  $("count-white").textContent = String(s.whiteCount);
  $("who-black").textContent = humanColor === 1 ? "(you)" : "(AI)";
  $("who-white").textContent = humanColor === -1 ? "(you)" : "(AI)";
  const over = s.legal.length === 0 && !s.opponentHasMove;
  $("player-black").classList.toggle("active", !over && s.color === 1);
  $("player-white").classList.toggle("active", !over && s.color === -1);

  renderAnalysisList();
  renderRecord();
  undoBtn.disabled = !canUndo();
  undoBtn.title = undoBtn.disabled ? "Nothing to undo yet" : "Go back to your previous turn (⌘Z / Ctrl+Z)";
}

function renderRecord() {
  if (renderedPlies === plies.length) return;
  const grew = plies.length > renderedPlies;
  renderedPlies = plies.length;
  void updateOpeningName();
  recordEl.replaceChildren();
  const moves = plies.filter((p) => p.move).length;
  recordCount.textContent = moves ? `${moves} ${moves === 1 ? "move" : "moves"}` : "";
  copyBtn.disabled = moves === 0;
  if (plies.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No moves yet";
    recordEl.appendChild(li);
    return;
  }
  let n = 0;
  plies.forEach((p, i) => {
    const li = document.createElement("li");
    const num = document.createElement("span");
    num.className = "n";
    const disc = document.createElement("span");
    disc.className = `mini ${p.color === 1 ? "black" : "white"}`;
    const text = document.createElement("span");
    if (p.move) {
      n++;
      num.textContent = String(n);
      text.textContent = notation(p.move[0], p.move[1]);
      li.setAttribute("aria-label", `move ${n} ${colorName(p.color)} ${text.textContent}`);
    } else {
      li.classList.add("pass");
      text.textContent = "pass";
      li.setAttribute("aria-label", `${colorName(p.color)} passes`);
    }
    if (i === plies.length - 1) li.classList.add("latest");
    li.append(num, disc, text);
    recordEl.appendChild(li);
  });
  if (grew) recordEl.scrollTop = recordEl.scrollHeight;
}

// Look up the opening name. Named openings are at most about 20 moves long, so stop asking after that
const OPENING_MAX_MOVES = 24;
let openingName: string | null = null;
async function updateOpeningName() {
  const transcript = recordText();
  if (transcript.length / 2 > OPENING_MAX_MOVES) return; // keep showing the last name after leaving the book
  const name = transcript ? (await engine.opening(transcript)).name : null;
  if (recordText() !== transcript) return; // the game moved on or back while we were asking
  openingName = name;
  openingNameEl.textContent = openingName ?? "–";
}

function recordText(): string {
  return plies
    .filter((p): p is Ply & { move: Move } => p.move !== null)
    .map((p) => notation(p.move[0], p.move[1]))
    .join("");
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
    li("Shown on your turn", "empty");
    return;
  }
  if (!analysis) {
    li("Analyzing…", "empty");
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
  li(`depth ${analysis.depth} · ${analysis.nodes.toLocaleString()} positions · ${analysis.ms} ms`, "empty");
}

function setStatus(text: string) {
  statusEl.textContent = text;
}

// ---------- game flow ----------
async function startGame() {
  const id = ++gameId;
  humanColor = Number(
    (document.querySelector('input[name="human-color"]:checked') as HTMLInputElement).value,
  ) as Color;
  busy = false;
  lastMove = null;
  analysis = null;
  plies = [];
  snapshots = [];
  copyStatus.textContent = COPY_HINT;
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
      setStatus(`${colorName(s.color)} has no legal move and passes`);
      await sleep(900);
      const next = await engine.getState(s, (-s.color) as Color);
      if (id !== gameId) return;
      plies.push({ color: s.color, move: null });
      state = next;
      render();
      continue;
    }

    if (s.color !== humanColor) {
      busy = true;
      setStatus("AI is thinking…");
      render();
      const level = levelSel.value;
      const depth = Number(depthInput.value);
      const [res] = await Promise.all([engine.aiMove(s, level, depth, AI_TIME_LIMIT), sleep(400)]);
      if (id !== gameId) return;
      $("stat-ms").textContent = `${res.ms.toLocaleString()} ms`;
      $("stat-nodes").textContent = res.book
        ? "– (book)"
        : res.nodes === null
          ? "– (no search)"
          : res.nodes.toLocaleString();
      $("stat-depth").textContent = res.book
        ? `Book move (precomputed ${res.depth} plies deep)`
        : res.solved
          ? `Solved to the end (${res.depth} plies)`
          : res.depth
            ? `${res.depth} plies deep`
            : "–";
      if (!res.move) throw new Error("the AI returned no move");
      const next = await engine.play(s, res.move[0], res.move[1]);
      if (id !== gameId) return;
      plies.push({ color: s.color, move: res.move });
      state = next;
      lastMove = res.move;
      analysis = null;
      busy = false;
      render(true);
      continue;
    }

    // your turn (save the position so undo can return to it)
    if (snapshots[snapshots.length - 1]?.state !== s) {
      snapshots.push({ state: s, lastMove, plies: plies.length });
    }
    setStatus(`Your turn (${colorName(humanColor)})`);
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
  plies.push({ color: s.color, move: [row, col] });
  state = next;
  lastMove = [row, col];
  analysis = null;
  busy = false;
  render(true);
  await advance(id);
}

// ---------- undo ----------
// Go back to your previous turn (undoing both your move and the AI's reply).
// Pressed while the AI is thinking, it discards that search and returns to before your move.
function canUndo(): boolean {
  if (!state || snapshots.length === 0) return false;
  return snapshots[snapshots.length - 1].state !== state || snapshots.length >= 2;
}

async function undo() {
  if (!canUndo()) return;
  if (snapshots[snapshots.length - 1].state === state) snapshots.pop();
  const target = snapshots[snapshots.length - 1];
  const id = ++gameId; // discard any AI search or analysis still in progress
  state = target.state;
  lastMove = target.lastMove;
  plies = plies.slice(0, target.plies);
  analysis = null;
  busy = false;
  render();
  await advance(id);
}

function finishGame(s: GameState) {
  const diff = s.blackCount - s.whiteCount;
  const humanDiff = diff * humanColor;
  const result = humanDiff > 0 ? "You win!" : humanDiff < 0 ? "The AI wins" : "Draw";
  setStatus(`Game over — Black ${s.blackCount} : ${s.whiteCount} White · ${result}`);
  render();
}

// Without the Clipboard API (no permission or an old browser), fall back to execCommand
async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    ta.remove();
    copyBtn.focus();
    return ok;
  }
}

// ---------- events ----------
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
undoBtn.addEventListener("click", () => void undo());
copyBtn.addEventListener("click", async () => {
  const text = recordText();
  if (await copyToClipboard(text)) {
    copyStatus.textContent = `Copied (${text.length / 2} moves)`;
  } else {
    copyStatus.textContent = `Could not copy. Moves: ${text}`;
  }
});
// ⌘Z / Ctrl+Z to undo
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && !e.shiftKey && (e.key === "z" || e.key === "Z")) {
    e.preventDefault();
    void undo();
  }
});
// E toggles the board scores (except while typing in an input)
document.addEventListener("keydown", (e) => {
  if (e.key !== "e" && e.key !== "E") return;
  if (e.metaKey || e.ctrlKey || e.altKey || e.isComposing) return;
  const t = e.target as HTMLElement | null;
  if (t && (t.tagName === "INPUT" || t.tagName === "SELECT" || t.tagName === "TEXTAREA") && t !== showEvalInput) return;
  showEvalInput.checked = !showEvalInput.checked;
  onDisplayToggle();
});

// ---------- startup ----------
engine.ready
  .then(async (version) => {
    $("runtime").textContent = version;
    loadingEl.hidden = true;
    newGameBtn.disabled = false;
    await startGame();
  })
  .catch((e: unknown) => {
    loadingText.textContent = `Failed to load: ${e instanceof Error ? e.message : String(e)}`;
    setStatus("Could not load the engine. Please reload the page.");
  });
