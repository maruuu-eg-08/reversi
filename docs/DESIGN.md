# Design notes

This document explains how the engine is built, why it is built that way, what worked, what did not,
and what I would do next. The [README](../README.md) is the short tour; this is the long one.
The last section lists questions I expect in an interview, with short answers.

Contents

1. [Goals and constraints](#1-goals-and-constraints)
2. [Architecture](#2-architecture)
3. [Board representation](#3-board-representation)
4. [Search](#4-search)
5. [Evaluation: from hand-tuned to learned](#5-evaluation-from-hand-tuned-to-learned)
6. [The learning pipeline](#6-the-learning-pipeline)
7. [Measuring strength](#7-measuring-strength)
8. [Engineering for correctness](#8-engineering-for-correctness)
9. [What worked and what did not](#9-what-worked-and-what-did-not)
10. [Limitations and next steps](#10-limitations-and-next-steps)
11. [Interview questions](#11-interview-questions)

---

## 1. Goals and constraints

- **A strong engine whose strength is measured, not claimed.** Every change that is meant to make the AI
  stronger is checked in head-to-head matches with a confidence interval, and results that are not
  significant are reported as such.
- **Runs for free.** It runs in the browser (GitHub Pages, no server), and all training runs on a laptop
  (8 cores) or GitHub Actions. No GPUs, no paid cloud.
- **Easy to explain.** Each part is a well-known technique (bitboards, alpha-beta search, linear
  regression over pattern features) built carefully, rather than a black box.

## 2. Architecture

```
                 ┌─────────────────────────────┐
  Web UI ──wasm──▶│  Rust engine (backend_rust) │◀──PyO3── Python tools
  (TypeScript,    │  search · evaluation ·      │          arena · self-play · training · book
   web worker)    │  self-play · training       │
                 └──────────────┬──────────────┘
                                │ tests: same move, score and node count
                 ┌──────────────▼──────────────┐
                 │  Python reference engine     │
                 │  (backend/strong_ai.py)      │
                 └─────────────────────────────┘
```

The project started in pure Python. When search speed became the limit, the hot path was ported to Rust
**without changing the algorithm**: the Python version stayed as the reference and tests require both to
return the same best move, the same score (bit-identical floating-point values) and the same number of
searched nodes. That made the port safe (any divergence is a bug that a test finds) and made the
speed-up easy to measure: same algorithm, same nodes, ~80× faster.

The same Rust crate is built three ways:

| Build | Used by | How |
|---|---|---|
| Python extension | arena, self-play, training, book building | PyO3 + maturin (`--features python`) |
| WebAssembly | the browser game | `wasm32-unknown-unknown`, plain `extern "C"` exports |
| Native tests | `cargo test` | unit and property tests |

Heavy jobs that are not on the search path (self-play data generation, weight training) were written only
in Rust; the Python scripts are thin command-line wrappers around them.

## 3. Board representation

A position is two 64-bit integers: the discs of the player to move and the discs of the opponent. Bit
`row * 8 + col` is one square. This "side to move" form means the search never needs a color variable:
after a move the two boards swap.

Legal moves are found with the standard shift-and-mask method: for each of the 8 directions, shift the
player's discs repeatedly through runs of opponent discs and keep the empty squares where a run ends.
Masks stop the shifts from wrapping around the board edges. Flipping uses the same idea from the move
square outward.

**Verification.** Move generation is checked with *perft* (counting all positions reachable in *n*
plies; 390,216 positions at 8 plies matches the known value) and against a slow, obviously correct
implementation on random positions.

## 4. Search

Lv.5 is a classic alpha-beta engine:

| Technique | What it does | Why |
|---|---|---|
| Negamax | one function for both players: my score = −(opponent's score) | half the code, no color bugs |
| Alpha-beta pruning | skips moves that cannot change the result | with perfect ordering, searches roughly the square root of the full tree |
| Principal variation search (PVS) | searches the first move with a full window, the others with a null window, and re-searches only if a move turns out better | most moves are worse than the first one, and proving that is cheap |
| Iterative deepening | searches depth 1, 2, 3, … until time runs out | gives an answer at any moment and fills the transposition table with good first moves for the next depth |
| Transposition table | a hash map from position to (depth, bound, value, best move) | reuses results for positions reached by different move orders, and supplies the best move to try first |
| Move ordering | table move first, then *fastest-first* (moves that leave the opponent the fewest replies) at depth ≥ 3, otherwise by square weight | good ordering is what makes alpha-beta and PVS effective |
| Exact endgame solve | when the remaining empty squares fit within the depth reached, the search reaches the end of the game | perfect play in the endgame; scores become exact disc differences |

**Time management.** The clock is checked every 1,024 nodes. A new depth is not started once 70% of the
time is used, because it could not even finish its first move. If time runs out in the middle of a depth,
the best move found so far in that depth is still used: the previous best move is always searched first,
so anything that beat it is safe.

**Scores.** The evaluation returns a float. Finished games return a large constant (`WIN_SCORE`) plus the
disc difference, so a win is always preferred to any heuristic score, and a bigger win to a smaller one.

## 5. Evaluation: from hand-tuned to learned

The evaluation function turned out to be the most important part of the engine. It went through four
versions:

| Version | Idea | Result |
|---|---|---|
| 1. Hand-written square weights | corners good, squares next to corners bad | baseline |
| 2. Genetic algorithm (`ga_trainer.py`) | evolve 9 coefficients (3 features × 3 game phases) by playing games | worked but slow and noisy: each fitness value is a few games |
| 3. Linear regression (`tune_eval.py`) | fit 12 coefficients (positional, mobility, discs, frontier × 3 phases) to the final results of self-play games | **87% vs the untrained coefficients** (87–13 in 100 games, 95% CI 80.4–93.6%); cheaper and more stable than the GA |
| 4. Pattern evaluation (`patterns.py`, `pattern.rs`) | a learned score for every configuration of 11 board shapes, per game stage | **97% vs version 3** (194–6 in 200 games, 95% CI 94.6–99.4%) |

The lesson from versions 2 → 3 was that when a problem can be written as least squares, solving it
directly beats searching for the answer by trial and error.

### Pattern evaluation

A linear evaluation over a few global features cannot express things like "this edge configuration is
safe but that one lets the opponent take the corner". Pattern evaluation, the approach used by strong
Othello programs such as Logistello, gives every configuration of a small group of squares its own learned
value and adds them up.

- **Shapes** (11): rows 2, 3 and 4, diagonals of length 4–8, an edge plus its two X-squares (10 squares),
  a corner 3×3 block and a corner 2×5 block. Each square is empty, mine or the opponent's, so a 10-square
  shape has 3¹⁰ = 59,049 configurations.
- **Symmetry by construction.** Each shape appears on the board in up to 8 rotated/reflected positions.
  Instead of trusting the training data to make them equal, every distinct (set of squares, reading order)
  image under the 8 symmetries is an *instance* that reads the **same** weight table (84 instances). A
  mirror-symmetric shape such as an edge is read from both ends. The evaluation is therefore exactly
  symmetric for *any* weights, which a property test checks.
- **15 stages.** The value of a configuration changes during the game (discs on an edge mean something
  else at move 10 and at move 50), so there is a separate table for every 4 moves: 15 stages × 167,265
  weights.
- **Integer weights.** Weights are stored in units of 1/64 disc as integers. Integer addition gives the
  same result in any order, so Python, native Rust and WebAssembly agree exactly. (With floats, a
  different summation order changes the last bit, and the engines stop agreeing.)

**Cost.** The pattern evaluation is about 5× slower per node than the linear one, so in the same time it
searches about 1.7 plies shallower. It still wins 97% of games (194–6, 95% CI 94.6–99.4%): **a better evaluation was worth more than
deeper search.**

## 6. The learning pipeline

```
 self-play (selfplay.rs)  ──▶  positions + final results  ──▶  least squares (train.rs)  ──▶  weights
        ▲                                                                                      │
        └──────────────────────────── better player ◀──────────────────────────────────────────┘
```

### Self-play data

Each game starts with 8–20 random moves (so the data covers many openings), then both sides search to
depth 6, and from 14 empty squares on the game is **solved exactly** and played perfectly.

**Labels.** Each position is labeled with the final disc difference for the side to move. Labels are
exact from the first solved position on. Earlier positions get the exact value of that first solved
position, i.e. the result if both sides play perfectly from there. This removes the noise of endgame
mistakes from every label in the game.

**Reproducible and resumable.** Each game's random numbers come only from the seed and its game number, so the
output is byte-for-byte identical for any number of threads, and an interrupted run continues where it
stopped (the settings are stored in the file header, and resuming with different settings is refused).

### Training

For each stage, the weights `w` minimize

```
‖X w − y‖² + λ ‖w‖²
```

where each row of `X` is one position (a 1 for each pattern configuration that occurs in it, plus a bias
and the mobility difference), and `y` is its label. This is ridge regression. The normal equations
`(XᵀX + λI) w = Xᵀy` have 167,265 unknowns per stage, but `X` is very sparse (86 non-zeros per row), so
they are solved with **conjugate gradients** (CG) without ever forming `XᵀX`: each iteration only needs
`X v` and `Xᵀ u`, which are sparse loops. A **Jacobi preconditioner** (dividing by the diagonal of
`XᵀX + λI`, i.e. how often each configuration occurs) makes rare and common configurations converge at a
similar speed.

**Why λ (regularization) matters.** Many configurations occur only a few times. Without regularization
their weights fit the noise of those few games. λ pulls rarely seen weights toward zero (unknown =
neutral) while barely affecting common ones. λ = 30 was chosen by the error on held-out games (1 game in 10).

**Deterministic in parallel.** Rows and columns are split across threads, and every dot product is
summed in fixed-size chunks in a fixed order, so the trained weights are identical for any thread count.
Training on 11.9 M positions takes about 2 minutes.

**Validation results.** On held-out games the pattern evaluation explains 63% of the variance of the
final result in the midgame (R² 0.634), against 23% for the linear evaluation (R² 0.227).

### Iterating the loop

The first data set was played by the linear evaluation. The natural next step, the same idea as
reinforcement learning by self-play, is to let the improved player generate new data and retrain on it:
better play gives positions closer to what a strong player actually meets, and better depth-6 choices.
`gen_data.py --patterns auto` makes both sides search with the pattern evaluation, and
`train_patterns.py` accepts several data files so old and new data can be combined.

Round 2: 200,000 new games played by the round-1 pattern evaluation (seed 1, so the random openings differ
from round 1; ~2 h 15 min), then two candidates, each played against the round-1 weights for 400 games
(0.3 s per move):

| Candidate | W–L–D | Score vs round 1 (95% CI) | Elo |
|---|---|---|---|
| Round-2 data only | 310–76–14 | 79.2% (75.3–83.2%) | +233 |
| Round-1 + round-2 data (adopted) | 333–58–9 | **84.4% (80.8–87.9%)** | +293 |

Two observations. First, held-out R² went up a lot (midgame 0.73–0.80 on round-2 data, against 0.634 for
round 1), but that is partly because games between stronger players are easier to predict; R² measured on
different data sets cannot be compared, which is why only the match decides. Second, combining both rounds
beat the new data alone: the new games are better played, but the old ones cover positions that a weaker
opponent creates, and twice the data helps the many rarely seen pattern configurations.

## 7. Measuring strength

`arena.py` is the referee for every claim in this project.

- **Paired openings.** Each opening (6 random moves from the start) is played twice with colors swapped.
  This cancels the first-move advantage and the luck of a lopsided random opening.
- **Score and confidence interval.** Score = (wins + ½ draws) / games, with a 95% confidence interval
  from the normal approximation `p ± 1.96 √(p(1−p)/n)`. A change is called stronger only if the whole
  interval is above 50%.
- **Elo.** The score is also converted to an Elo difference, `−400 log₁₀(1/p − 1)`, which is easier to
  compare between experiments.
- **Same conditions.** Both sides get the same time per move. Games run in parallel, one game per process,
  so time-limited play is slightly noisier under full load; both sides share that noise equally.

**A known simplification.** The interval treats every game as independent, but the two games of a pair
share an opening. If an opening favors one color, the pair's results tend to cancel and the true
uncertainty is smaller; if an opening suits one engine with either color, the results are positively
correlated and it is larger. A paired estimate (variance of the per-pair score) would be more exact.

## 8. Engineering for correctness

- **Two engines that must agree.** Python is slow but easy to read and debug; Rust is fast. Any change to
  search or evaluation goes into both, and equality tests on random positions compare moves, scores and
  node counts. Equal node counts are a strong check: they mean that move ordering, the transposition table
  and pruning happen in exactly the same order.
- **Floating point.** Python 3.12 changed `sum()` to compensated summation, which changed the last bit of
  precomputed tables and broke the equality tests. Tables are now summed in an explicit loop, and pattern
  weights are integers.
- **WebAssembly without a framework.** The browser build uses plain `extern "C"` functions. 64-bit boards
  cross into JavaScript as `BigInt`s; longer results go through a shared `f64` buffer; weights and the
  opening book are copied in through an exported `alloc`. `std::time::Instant` does not exist on
  `wasm32-unknown-unknown`, so the engine imports the clock from JavaScript's `performance.now()`.
  The result is 145 KB, against ~10 MB for the earlier Python-in-the-browser (Pyodide) version.
- **Deploys.** GitHub Pages caches files for 10 minutes, so a new HTML file could load an old JavaScript
  file. The build appends a content hash (`?v=…`) to every asset URL.
- **CI.** Every pull request runs ruff, pytest (with and without the Rust extension), `cargo fmt`,
  `cargo clippy` for native and wasm, `cargo test`, and a Node test that loads the built WebAssembly
  engine and plays moves.

## 9. What worked and what did not

Every row is an `arena.py` match with colors swapped; the score counts a draw as half a win.

| Change | Games | W–L–D | Score (95% CI) | Takeaway |
|---|---|---|---|---|
| Lv.5 search vs Lv.4 (fixed depth 4) | 100 | 98–2–0 | 98.0% (95.3–100%) | the search techniques work |
| Regression-trained linear evaluation vs untrained | 100 | 87–13–0 | 87.0% (80.4–93.6%) | least squares beats a genetic algorithm for fitting coefficients |
| Rust port vs Python, same time per move | 200 | 193–7–0 | 96.5% (94.0–99.0%) | ~80× more nodes = a few plies deeper |
| Pattern vs linear evaluation | 200 | 194–6–0 | **97.0% (94.6–99.4%)** | evaluation quality mattered most |
| Opening book vs no book | 400 | 202–185–13 | 52.1% (47.2–57.0%), **not significant** | games start from random positions, so the book is used for 1–2 moves; its value is instant replies |
| Book rebuilt with the pattern evaluation vs old book | 400 | 205–181–14 | 53.0% (48.1–57.9%), **not significant** | same reason |
| Wasm in the browser vs Pyodide (approximate, native reproduction) | 50 | 49–0–1 | 99.0% (96.2–100%) | speed in the browser turned into strength |
| Second round of self-play (round 1 + 2 data) vs round 1 | 400 | 333–58–9 | **84.4% (80.8–87.9%)** | the learning loop pays off; keep the old data too |

The opening-book result is the most useful "failure": it showed that the engine was not losing in the
opening, which pointed to the evaluation function as the bottleneck and led to the pattern work.

## 10. Limitations and next steps

- **Full recomputation of patterns at every node.** All 84 instances are re-read for every evaluated
  position. Updating only the patterns that contain flipped squares (incremental evaluation) would make
  evaluation several times faster and the search deeper.
- **No dedicated endgame solver.** The exact solve reuses the midgame search. Strong programs switch to
  a specialized solver near the end (parity-based ordering, no transposition table in the last few plies,
  no evaluation calls), which is much faster per node.
- **Transposition table.** It is an unbounded hash map cleared before each move. A fixed-size table with
  a replacement policy would use memory predictably and could be kept between moves.
- **Float scores.** Scores are floats, inherited from the original Python design (and kept so the two
  engines stay identical); integer scores would be faster and make null windows exact.
- **Learning.** The evaluation is linear in its features. The next step is a small neural network trained
  on the same data, and eventually reinforcement learning with search-guided targets (in the style of
  AlphaZero) on cloud GPUs.

## 11. Interview questions

**Q: Give a two-minute summary of the project.**
A reversi engine in Rust with a learned evaluation, playable in the browser through WebAssembly. I
started in Python, added alpha-beta search with iterative deepening and a transposition table, then found
by measurement that the evaluation function was the bottleneck. I replaced a hand-tuned linear evaluation
with pattern tables trained by ridge regression on self-play games, which won 97% of games against the
old version (194–6, 95% CI 94.6–99.4%); a second round of self-play by the new evaluation won another 84%
against the first (400 games, 95% CI 80.8–87.9%). The Rust port is verified to be identical to the Python reference and is about
80× faster.

**Q: What was the hardest part?**
Keeping Python and Rust exactly identical. It forced me to understand every detail, including
floating-point summation order: Python 3.12 changed `sum()` and broke bit-equality. I solved it by summing
in an explicit order and by using integer pattern weights.

**Q: Why keep a Python version at all?**
It is the readable reference. Because the Rust version must produce the same node counts, any bug in the
port shows up as a failing test immediately, and performance comparisons are fair: same algorithm, same
tree, only the language differs.

**Q: How do you know the AI got stronger and not just lucky?**
Paired matches with colors swapped, a 95% confidence interval, and only adopting a change when the whole
interval is above 50%. I also report results that were not significant, like the opening book.

**Q: Why did the pattern evaluation win even though it searches less deeply?**
A wrong evaluation at the leaves is wrong at every depth; searching deeper only moves the error further
away. The linear evaluation could not tell a safe edge from a dangerous one; the patterns can. Better
leaf values were worth more than 1.7 extra plies.

**Q: Why ridge regression and conjugate gradients rather than gradient descent or a neural network?**
The model is linear in its weights, so the best weights are the solution of a linear system; there is no
learning rate to tune and the result is reproducible. CG solves sparse symmetric positive-definite
systems efficiently without forming the matrix. A neural network is the next step, and the pattern model
is a strong baseline to compare it against.

**Q: What does λ do, and how did you choose it?**
It penalizes large weights, which mainly affects configurations seen only a few times, so they do not
memorize noise. I compared several values on held-out games (split by game, not by position, so positions
from the same game never appear on both sides) and picked the best one.

**Q: Why split validation data by game?**
Positions from the same game are strongly correlated and share the same label. Splitting by position
would leak information and make the validation error look better than it is.

**Q: How does the search use time?**
Iterative deepening: depth 1, 2, 3 … each reusing the transposition table from the last. It stops
starting new depths after 70% of the time, and if it runs out mid-depth it keeps the best move found so
far, which is safe because the previous best move is always searched first.

**Q: How did you make parallel code deterministic?**
Self-play: each game's randomness depends only on its game number, and results are stored by game
number, so thread scheduling does not matter. Training: work is split into fixed chunks and partial sums
are added in a fixed order.

**Q: Your second round of self-play improved R² a lot. Is that why it is stronger?**
Not necessarily: the round-2 validation games were played by a stronger player and are easier to predict,
so R² on different data sets is not comparable. The 84% match result is the evidence; R² is only a sanity
check within one data set.

**Q: What would you do with more time?**
Incremental pattern updates and a dedicated endgame solver for speed; then a neural-network evaluation
trained on the same data; then reinforcement learning on cloud GPUs.

**Q: What did you learn?**
To measure before optimizing (the opening book taught me that), to keep a slow reference implementation
for testing a fast one, and that reproducibility (deterministic, resumable jobs) saves a lot of time in
machine-learning experiments.
