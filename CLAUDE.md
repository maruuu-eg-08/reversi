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
| #19 | Learning loop round 2 (self-play with pattern eval, retrain on old+new data) + docs/DESIGN.md | **round 2 vs round 1 333-58-9 (84.4%, CI 80.8-87.9%)**; new data only 79.2% |
| #20 | Claude Code subagents (code-reviewer, test-runner, ai-benchmarker) | merged 2026-11-18 with the user's OK |
| #24 | B-1 incremental pattern evaluation (Rust only; Python unchanged by the user's choice, values identical) | evaluation was 61% of search time; depth 10 1.52x faster, Lv.5 +0.4 ply in 0.3 s, results identical on 30 positions |
| #26 | Learning loop round 3 (round-2 engine plays 200k games, retrain) | **round 3 (new data only) vs round 2: 1038-846-116 in 2,000 games, 54.8% (CI 52.6-57.0%)**; 2+3 data 52.8%, 1+2+3 51.5% (400 games, n.s.); converging (+293 -> +33 Elo) |

## Current status

Pattern evaluation (#10-#15), the WebAssembly web version (#16), the English translation with the new
README (#17), the second round of self-play with docs/DESIGN.md (#19), subagents (#20), B-1 incremental
pattern evaluation (#24) and the third round of self-play (#26) are done.

- Speed benchmark: `data/bench/` (gitignored) holds `speed_bench.py` (run from a venv with the extension;
  `--compare speed_baseline.json` checks move/score/nodes are identical), the pre-B-1 baseline JSON and
  `midgame.txt`. Rust-only quick bench: `cargo run --release --example bench_search --
  examples/midgame_positions.txt 10 ../backend/pattern_weights.bin` (21,168,136 nodes at depth 10).
- Incremental evaluation lives in Rust only (`pattern::Features`, `Searcher::incremental`); the test
  `incremental_pattern_evaluation_gives_identical_results` compares it with full recomputation.
- **Round 3 of self-play is done (2026-11-19)**: `data/selfplay-gen3-200k.bin` (seed 2, round-2 weights, 11.96 M
  positions; ran 12:50-16:29 incl. a ~1 h pause while the lid was closed). Candidates `data/pw-gen3.bin`
  (adopted), `pw-gen23.bin`, `pw-gen123.bin` (λ = 30); arena log `data/arena-gen3.log`. None was significant
  in 400 games, so the best was re-tested with `-n 1000 --seed 1` (new openings): significant. Lesson: a gain
  of a few percent needs ~2,000 games; old round-1 data no longer helps; the loop is converging, so the next
  strength gain likely needs a bigger model (D, neural network) rather than round 4.
- The user keeps an Obsidian dev log + roadmap (`~/Documents/Obsidian Vault/20_Projects/Notes/Othello AI - *.md`);
  update the day's log and the roadmap after each piece of work.

- Training data (gitignored): `data/selfplay-200k.bin` (round 1, linear eval, seed 0) and
  `data/selfplay-gen2-200k.bin` (round 2, `--patterns auto` with round-1 weights, seed 1; 11.95 M positions,
  ~2 h 15 min at ~24 games/s). Round-1 weights are kept as `data/pw-l30.bin`; candidates `data/pw-gen2.bin`
  (round-2 data only) and `data/pw-gen12.bin` (adopted). Arena log: `data/arena-gen2.log`.
- Weights: `backend/pattern_weights.bin` = round 3 data only, λ = 30 (#26; commit adopted versions only).
  Round-2 weights (round 1 + 2 data) are kept as `data/pw-gen12.bin`.
- The opening book was NOT rebuilt with the round-2/3 weights (earlier rebuilds were not significant).
- The web Lv.5 uses Rust (wasm) + pattern evaluation + opening book. Lv.1-4 are Rust ports identical to Python.
- README chart `docs/images/head-to-head.png` is drawn by a small matplotlib script (not in the repo; same style:
  horizontal bars + 95% CI, background #fcfcfb, bar #2a78d6). `r2-by-stage.png` still shows round 1. The chart
  script used on 2026-11-19 was in the session scratchpad (8 rows incl. round 3; figsize 9x5.3, dpi 200).
- The repository About section was updated (description, homepage link to the game, topics:
  rust, webassembly, game-ai, othello, reversi, machine-learning).

## Subagents (`.claude/agents/`, PR #20, merged 2026-11-18)

Chosen by the user from their own role list (rules-tester became test-runner; readme-writer skipped;
ai-researcher added afterwards):
- `code-reviewer` (Read/Grep/Glob only): review changes against the project rules; give it the changed files.
- `test-runner`: runs every check (ruff, pytest with/without Rust, cargo fmt/clippy native+wasm, cargo test,
  frontend build + smoke test) and reports; does not fix.
- `ai-benchmarker`: arena.py matches (colors swapped, 95% CI) and speed; refuses to start while another heavy
  job is running.
- `ai-researcher` (Read/Grep/Glob/WebSearch/WebFetch, added for the 2026-11-19 plan): researches techniques and
  proposes a plan that fits the codebase; never edits. Use it at the start of B.
`.gitignore` tracks `.claude/agents/` only. Agent files are in English.
Subagents start without this conversation's context and cost more than doing small things directly, so use
them for repeated, well-defined jobs (full checks before a PR, reviews, benchmarks).

## Plan for 2026-11-19 (decided by the user on 2026-11-18)

Order: **B (faster search) -> round 3 of self-play with the faster engine -> interview practice while it runs**.
Start the day by confirming the plan with the user, then go.

0. **Research** (`ai-researcher`): incremental pattern evaluation and endgame-solver techniques; agree the design
   with the user.
1. **Baseline first** (`ai-benchmarker`): nodes/s, seconds and completed depth at fixed depths 8 and 10 on fixed
   random positions, and the depth Lv.5 reaches in 0.3 s / 1 s. Save the numbers for the README.
2. **B-1 incremental pattern evaluation** (DONE, #24; Rust only by the user's choice): update only the pattern instances that contain the
   placed or flipped squares instead of recomputing all 84. Values must stay identical, so
   `tests/test_rust_engine.py` / `tests/test_rust_web_port.py` keep passing with the same moves, scores and node
   counts. Also used by the wasm build.
3. **B-2 dedicated endgame solver** (postponed by the user until after round 3): in the last few empty squares, a specialized search without evaluation calls
   (parity / fastest-first ordering, no transposition table at the very end). The search procedure changes, so
   implement it in Python too and keep the equality tests passing.
4. After each step: `test-runner` (all checks), then `ai-benchmarker` (speed vs baseline; arena 200 openings =
   400 games vs the current engine at 0.3 s); `code-reviewer` before the PR.
5. **Round 3 of self-play** with the faster engine and the round-2 weights:
   `gen_data.py --games 200000 --patterns auto --seed 2 --out ../data/selfplay-gen3-200k.bin` (round 2 took
   2 h 15 min; expected shorter). Keep the Mac awake (`caffeinate -i -w <pid>`). No benchmarks or arena while it runs.
6. **Interview practice during the generation**: go through docs/DESIGN.md in Japanese, then answer the interview
   questions in English.
7. Retrain candidates (round 3 only; rounds 1+2+3; maybe 2+3), arena each vs the round-2 weights (400 games),
   adopt the best if stronger; update README (results table, chart, speed table), DESIGN.md, CLAUDE.md; deploy and
   check the live page.

Delegation (same rule as 2026-11-18): **merge and publish without asking if the change is stronger at all**
(arena 95% CI above 50%), or for B if it is faster with identical results. Otherwise report and ask.
Later options: D (neural-network evaluation), rebuilding the opening book, the open #19 nice-to-have items
(`load_patterns` cache keyed by path only, clean error for a missing `--patterns` file, paired-variance CI in arena.py).
- Note: two chats worked on the same checkout on 2026-11-18 (a second chat committed review fixes on the
  branch). Before editing, check `git log` / `git status` for commits from another chat.
