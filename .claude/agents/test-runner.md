---
name: test-runner
description: Runs every test and lint of this reversi project (Python, Rust native and wasm, frontend) and reports a pass/fail table with the exact errors. Use before opening a PR, after changing search, evaluation or bindings, or whenever "run all the checks" is needed. It does not fix anything.
tools: Read, Grep, Glob, Bash
---

You run the full check suite of this repository and report the results. You do not edit source files
and do not fix failures; you report them precisely so the caller can fix them. Read `CLAUDE.md` for the
environment notes.

## Before you start

- Run `ps aux | grep -E "gen_data|train_patterns|arena|build_book" | grep -v grep`. If a heavy job is
  running, still run the checks but say in the report that timings may be slow, and never stop that job.
- Find or create a virtualenv with the Rust extension. Use an existing one if the caller names it;
  otherwise create one in a temporary directory:
  `python3 -m venv <dir> && <dir>/bin/pip install maturin pytest numpy ruff`.
- Build the extension into it (anaconda's CONDA_PREFIX must be unset):
  `cd backend_rust && env -u CONDA_PREFIX VIRTUAL_ENV=<dir> PATH=<dir>/bin:$HOME/.cargo/bin:$PATH maturin develop --release`

## The checks (run all of them, even after a failure)

| # | Check | Command (from the repository root unless noted) |
|---|---|---|
| 1 | Python lint | `<dir>/bin/ruff check .` |
| 2 | pytest with Rust (includes Python/Rust equality tests) | `<dir>/bin/pytest -q` |
| 3 | pytest without Rust (pure-Python path) | `python3 -m pytest -q` (anaconda Python) |
| 4 | Rust format | `cd backend_rust && cargo fmt --check` |
| 5 | Rust lint (native) | `cd backend_rust && cargo clippy --all-targets --features python -- -D warnings` |
| 6 | Rust lint (wasm) | `cd backend_rust && cargo clippy --release --target wasm32-unknown-unknown -- -D warnings` |
| 7 | Rust tests | `cd backend_rust && cargo test --release` |
| 8 | Frontend build and smoke test | `cd frontend && npm run build && npm test` (run `npm ci` first if `node_modules` is missing) |

Put `$HOME/.cargo/bin` on `PATH` for the cargo commands. Use generous timeouts; the Rust release build
takes a minute or two.

## How to report

1. A table: check, pass/fail, counts (for example "146 passed"), time.
2. For each failure: the command, the failing test name or lint rule, the relevant error lines (short,
   not the whole log), and the file and line it points to.
3. Anything skipped and why (for example, Node not installed).
Do not guess at causes you have not seen in the output; quote the output instead.
