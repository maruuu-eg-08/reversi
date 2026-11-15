# CLAUDE.md

Notes that let Claude pick up this project in a new chat: its history, the working rules agreed with the
user, and the current status. **Claude updates this file after every piece of work** (the user said no
permission is needed). Always keep "Work history" and "Current status" up to date.

## Project

A reversi (Othello) AI portfolio. The user wants an advanced portfolio whose improvements are shown with
numbers, aimed at graduate schools and IT companies abroad, so **everything on GitHub is written in
English** (code, comments, README, PR titles and descriptions).

- Repository (public): https://github.com/maruuu-eg-08/reversi
- Web version (GitHub Pages): https://maruuu-eg-08.github.io/reversi/ (auto-deployed by
  `.github/workflows/pages.yml` on every push to main)
- **Talk to the user in Japanese.** The user is not an expert, so explain technical terms simply.
- **When asking the user questions, collect them in a numbered "質問一覧" (question list) at the end of the
  message, each with a recommended answer.**

## Layout

```
backend/          Python engine and tools (the reference implementation)
  bitboard.py       bitboards
  strong_ai.py      Lv.5 (iterative-deepening PVS, TT, endgame solve, book); uses Rust when installed
  weights.py        evaluation parameters (STRONG_EVAL_COEFFS etc.)
  patterns.py       pattern evaluation (Python); pattern_weights.bin(.json) = adopted weights and metrics
  opening_book.py   symmetric opening book / build_book.py generator / opening_book.txt (7,081 positions)
  openings.py       named openings (Gatliff's 77), English names only
  gen_data.py       self-play training data (needs Rust) / train_patterns.py weight training (needs Rust)
  arena.py          AI-vs-AI matches (colors swapped, 95% CI, Elo)
  web_api.py        Python version of the JSON API (wasm-engine.ts mirrors its shapes)
backend_rust/     Rust engine (PyO3 `import reversi_engine`, and wasm32 for the browser)
  src/board.rs search.rs eval.rs pattern.rs selfplay.rs train.rs
  src/levels.rs book.rs openings.rs wasm.rs clock.rs lib.rs
frontend/         TypeScript UI; runs the Rust engine as WebAssembly in a web worker (wasm-engine.ts).
                  `npm run build` builds Rust -> wasm -> dist/; `npm test` runs the built engine in Node
docs/images/      README screenshots and charts
tests/            pytest (pythonpath = backend)
data/             training data (gitignored, large)
.github/workflows ci.yml (lint, test, rust, frontend), pages.yml, build-book.yml (manual book build)
```

## Environment and commands

- Python is anaconda's python3 (3.13). ruff is not installed system-wide; use a virtualenv.
- Rust 1.94 (`~/.cargo/bin`) with the `wasm32-unknown-unknown` target installed.
- Install the Rust extension into a virtualenv with `maturin develop --release`. In the anaconda
  environment CONDA_PREFIX must be unset:
  `env -u CONDA_PREFIX VIRTUAL_ENV=<venv> PATH=<venv>/bin:$PATH maturin develop --release`
- The virtualenv used so far lives in the session scratchpad and may disappear; recreate it with
  `python3 -m venv <dir> && <dir>/bin/pip install maturin pytest numpy ruff`.
- Tests: `pytest` both in the Rust virtualenv (includes Rust/Python equality tests) and with anaconda's
  `python3 -m pytest` (no Rust, the pure-Python path).
- Lints: `ruff check .`; in backend_rust `cargo fmt --check`,
  `cargo clippy --all-targets --features python -- -D warnings`,
  `cargo clippy --release --target wasm32-unknown-unknown -- -D warnings`, `cargo test --release`.
- Frontend: `cd frontend && npm run build && npm test`. Local preview: the `reversi-web` entry in
  `.claude/launch.json` (port 8765, serves dist).
- README images: charts with matplotlib, screenshots with headless Chrome over the DevTools protocol
  (a small Node script, no npm packages), at 2x/3x device scale.

## Working rules agreed with the user

- Feature branch -> PR -> CI green -> merge. **Ask the user before merging and publishing**, unless they
  delegated it for that piece of work (e.g. "merge if significantly stronger" for the pattern work,
  "merge and publish after browser verification" for the WebAssembly work).
- Commits use the GitHub noreply email (set in the repo's local git config). Never expose the personal email.
- Strength claims must come from `arena.py` matches (colors swapped, 95% CI). Adopt only what is proven
  stronger; report non-significant results honestly in the README.
- Keep the README results up to date and check the live page after each deploy.
- Before a long computation, tell the user the expected duration and show progress.
- Heavy computation runs with the Rust engine locally (8 cores) or on GitHub Actions. AWS is a later option
  for reinforcement learning / deep learning; prefer free options first.
- Keep Python and Rust identical: any change to search or evaluation goes into both, and
  `tests/test_rust_engine.py` / `tests/test_rust_web_port.py` must pass (same moves, scores and node counts).
- Use American English spelling (color, regularization, ...).

## Technical notes (lessons learned)

- Python 3.12+ `sum()` uses compensated summation for floats, which changed the last bit between versions;
  weight tables are now summed in an explicit loop.
- Pattern weights are integers (1/64 disc), so Python and Rust agree regardless of summation order.
- Pattern instances include every distinct (squares, reading order) image (84), so the evaluation is exactly
  symmetric for any weights.
- GitHub Pages caches files for 10 minutes; the build stamps `?v=<hash>` on every asset URL.
- WebAssembly: plain `extern "C"` exports, no wasm-bindgen. i64 values are BigInts in JS and come back
  signed (`BigInt.asUintN(64, x)`). `std::time::Instant` is unavailable on wasm32, so `clock.rs` imports
  `env.now_ms` (performance.now) from JS.
- PyO3 0.22's macros trigger a false clippy::useless_conversion; it is allowed in lib.rs's python module.
- Lv.2/3 choose randomly among equally good moves, so tests compare the set of best moves. Even the
  symmetric start position may not tie, because float sums differ by order (same in Python).
- In auto mode force-push is rejected; push a rebased branch under a new name and open the PR from it.
- The commit history and earlier merge-commit titles are partly Japanese; history is not rewritten.

## Work history

| PR | Change | Key result |
|---|---|---|
| #1 | Bug fixes, GUI improvements, tests and CI | move generation verified by perft |
| #2 | Web version (Pyodide + TypeScript, analysis view) | published on GitHub Pages |
| #3 | Lv.5 (iterative deepening, PVS, endgame solve) + learned linear evaluation | Lv.5 vs Lv.4 98%, trained vs untrained 87% |
| #4 | Toggle the board scores during a game (E key) | |
| #5 | Undo (⌘Z) and game record with copy | |
| #6 | Versioned asset URLs (old/new files mixed after deploys) | |
| #7 | GitHub Actions workflow for building the opening book | PyPy ~3.1x faster than CPython |
| #8 | Opening book (depth 10, 7,122 positions) and opening names | book vs no book 52.1% (not significant) |
| #9 | Rust engine (PyO3) | ~80x faster, identical to Python, Rust vs Python same time 96.5%, book rebuild 2.5 h -> 2 min 12 s (identical file) |
| #10 | Pattern evaluation step 1: definitions (11 shapes, 84 instances, 15 stages, integer weights) | Rust/Python equal, exactly symmetric |
| #11 | Step 2: self-play data generation | ~54 games/s, resumable, deterministic |
| #12 | CLAUDE.md added | |
| #13 | Step 3: weight training (Rust, preconditioned CG) | 200k games trained in 136 s, midgame R² 0.634 (linear 0.227) |
| #14 | Step 4: pattern evaluation in the search, adopted for Lv.5 | **pattern vs linear 194-6 (97.0%)** |
| #15 | Step 5: opening book rebuilt with pattern evaluation | new vs old book 53.0% (not significant), merged by user's choice; main line = Tiger -> Aubrey |
| #16 | Web version on Rust/WebAssembly, Pyodide removed | wasm 145 KB, 9-11 plies/s in the browser, Node smoke test in CI, new vs old web 49-0-1 |
| #17 | Everything translated to English; README redesigned with screenshots and charts | English UI, opening names in English, past PR titles/descriptions translated |

## Current status

Pattern evaluation (#10-#15), the WebAssembly web version (#16) and the English translation with the new
README (#17) are done.

- Training data: `data/selfplay-200k.bin` (200k games, gitignored). Weights: `backend/pattern_weights.bin`
  (λ = 30; commit adopted versions only).
- The web Lv.5 uses Rust (wasm) + pattern evaluation + opening book. Lv.1-4 are Rust ports identical to Python.

- The repository About section was updated (description, homepage link to the game, topics:
  rust, webassembly, game-ai, othello, reversi, machine-learning).

## Plan for the next session (proposed on 2026-11-16, not yet decided)

Options presented to the user (goal: a portfolio for graduate schools and IT companies abroad, balancing
strength, technical depth and being able to explain the work):

| Option | What | Time | Why |
|---|---|---|---|
| **A. Iterate the learning loop** | Regenerate self-play data with the pattern-evaluation Lv.5 (`gen_data.py`; the current data was played with the linear evaluation), retrain (`train_patterns.py`), and check with `arena.py` that it is stronger | ~1-2 h of computation (runs in the background) | another measurable strength gain |
| **B. Faster search** | Incremental pattern updates (recompute only the patterns touched by a move) and a dedicated fast endgame solver | about half a day | deeper search in the same time; good interview material |
| **C. Technical write-up** | `docs/DESIGN.md` in English: design, what worked and what did not, plus likely interview questions and how to answer them | 2-3 h | the user can explain the project in their own words; usable in applications |
| **D. Neural-network evaluation** | Train a small neural network on the existing data and compare it with the pattern evaluation (Colab GPUs possible) | a day or more | machine-learning experience; a step toward reinforcement learning (AWS later) |

Recommendation given to the user: **A + C**. Start A's data generation in the morning (~70 min in the
background), write C together while it runs (explaining the content to the user in Japanese), then retrain
and verify with arena. Keep B and D for later.

Open questions for the user (ask at the start of the next session if still undecided):
1. Which option(s) to do (recommended: A + C).
2. The write-up language (recommended: English on GitHub; explain it in Japanese in the chat).

Notes for option A: the existing data `data/selfplay-200k.bin` (~260 MB, gitignored) was generated with the
linear evaluation. `gen_data.py` / `selfplay.rs` currently always use the linear evaluation for self-play, so
they need an option to search with the pattern weights. Use a new output file (settings are stored in the
header and resuming refuses mismatched settings). Commit new weights only if arena shows a significant gain.
