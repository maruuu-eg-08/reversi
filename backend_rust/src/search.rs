//! Search. Follows exactly the same procedure as `StrongAI` in `backend/strong_ai.py`.
//!
//! With no time limit (fixed depth) it returns the same best move, score and node count as Python
//! (tests/test_rust_engine.py). Only the speed differs, so it searches deeper in the same time.

use std::sync::Arc;

use rustc_hash::FxHashMap;

use crate::board::{bits, legal_moves, play};
use crate::clock::now;
use crate::eval::{final_score, Evaluator};
use crate::pattern::{Features, PatternWeights};

/// Null-window width for PVS (same value as Python)
const NULL_WINDOW: f64 = 1e-6;
/// Check the clock every this many nodes
const TIME_CHECK_INTERVAL: u64 = 1024;
/// Do not start the next depth once this fraction of the time is used
const NEXT_DEPTH_TIME_RATIO: f64 = 0.7;

/// Kind of value stored in the transposition table
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Bound {
    Exact,
    Lower,
    Upper,
}

#[derive(Clone, Copy, Debug)]
struct Entry {
    depth: i32,
    bound: Bound,
    value: f64,
    best_move: u64,
}

/// The search was aborted because time ran out
#[derive(Debug)]
struct Timeout;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SearchResult {
    /// best move (single bit); 0 if there is no legal move
    pub best_move: u64,
    /// score for the player to move
    pub score: f64,
    /// completed depth
    pub depth: u32,
    /// nodes searched
    pub nodes: u64,
    /// whether the game was solved to the end
    pub solved: bool,
}

pub struct Searcher {
    /// linear evaluation (its positional weights are also used for move ordering with patterns)
    eval: Evaluator,
    /// pattern-evaluation weights; used at the leaves when present
    pattern: Option<Arc<PatternWeights>>,
    tt: FxHashMap<(u64, u64), Entry>,
    nodes: u64,
    /// deadline (seconds of `clock::now()`)
    deadline: Option<f64>,
    /// best move found so far in the current iteration (used on timeout)
    iter_best: Option<(u64, f64)>,
    /// update the pattern indices along the search instead of recomputing them at every leaf
    /// (same values; switched off only by tests that compare the two)
    incremental: bool,
}

impl Searcher {
    pub fn new(eval: Evaluator) -> Self {
        Self {
            eval,
            pattern: None,
            tt: FxHashMap::default(),
            nodes: 0,
            deadline: None,
            iter_best: None,
            incremental: true,
        }
    }

    /// Use pattern evaluation at the leaves.
    pub fn with_patterns(mut self, weights: Arc<PatternWeights>) -> Self {
        self.pattern = Some(weights);
        self
    }

    /// Static evaluation (depth 0) for the player to move `p`; `my_moves` is `legal_moves(p, o)`.
    #[inline]
    pub fn evaluate(&self, p: u64, o: u64, my_moves: u64) -> f64 {
        match &self.pattern {
            Some(w) => w.evaluate(p, o, my_moves, legal_moves(o, p)),
            None => self.eval.evaluate(p, o, my_moves),
        }
    }

    /// Pattern evaluation from the incrementally updated indices `f` (same value as `evaluate`).
    #[inline]
    fn evaluate_incremental(&self, p: u64, o: u64, my_moves: u64, f: &Features) -> f64 {
        let w = self
            .pattern
            .as_ref()
            .expect("incremental evaluation is only used with patterns");
        let opp_moves = legal_moves(o, p);
        let raw = w.evaluate_features(f, (!(p | o)).count_ones(), my_moves, opp_moves);
        debug_assert_eq!(raw, w.evaluate_raw(p, o, my_moves, opp_moves));
        f64::from(raw) / f64::from(crate::pattern::SCALE)
    }

    /// Indices of the root position when the leaves use incremental pattern evaluation.
    fn root_features(&self, p: u64, o: u64) -> Option<Features> {
        (self.pattern.is_some() && self.incremental).then(|| Features::new(p, o))
    }

    /// Whether the children of a node with `depth` and (`p`, `o`) need pattern indices: once
    /// `depth >= empties` the search reaches the end of the game before depth 0 (moves lower both by
    /// one, passes neither), so no evaluation happens below and the updates are skipped.
    #[inline]
    fn track_children(f: Option<&Features>, p: u64, o: u64, depth: i32) -> bool {
        f.is_some() && depth < (!(p | o)).count_ones() as i32
    }

    /// Indices of the child after move `x` from (`p`, `o`) to (_, `no`), if they are tracked.
    #[inline]
    fn child_features(
        f: Option<&Features>,
        track: bool,
        p: u64,
        x: u64,
        no: u64,
    ) -> Option<Features> {
        match f {
            Some(f) if track => Some(f.after_move(x.trailing_zeros(), no ^ p ^ x)),
            _ => None,
        }
    }

    /// `negamax` with incremental pattern evaluation when `f` is given, without otherwise.
    #[inline(always)]
    fn visit(
        &mut self,
        p: u64,
        o: u64,
        f: Option<&Features>,
        depth: i32,
        alpha: f64,
        beta: f64,
    ) -> Result<f64, Timeout> {
        match f {
            Some(f) => self.negamax::<true>(p, o, f, depth, alpha, beta),
            None => self.negamax::<false>(p, o, &Features::EMPTY, depth, alpha, beta),
        }
    }

    /// Iterative deepening for `time_limit` seconds (infinite = no limit) or up to `max_depth`.
    pub fn search(&mut self, p: u64, o: u64, time_limit: f64, max_depth: u32) -> SearchResult {
        self.tt.clear();
        self.nodes = 0;
        let start = now();
        self.deadline = deadline_after(start, time_limit);

        let moves = legal_moves(p, o);
        let result = |best_move, score, depth, nodes, solved| SearchResult {
            best_move,
            score,
            depth,
            nodes,
            solved,
        };
        if moves == 0 {
            return result(0, 0.0, 0, 0, false);
        }
        if moves & (moves - 1) == 0 {
            return result(moves, 0.0, 0, 0, false); // only one legal move
        }
        self.deepen(p, o, moves, start, time_limit, max_depth)
    }

    /// Solve to the end of the game and return (best move, exact score for the player to move).
    /// Unlike `search`, it also searches when there is a single legal move. Not for positions with no legal move.
    pub fn solve(&mut self, p: u64, o: u64) -> (u64, f64) {
        let moves = legal_moves(p, o);
        assert_ne!(moves, 0, "solve needs a position with a legal move");
        self.tt.clear();
        self.nodes = 0;
        self.deadline = None;
        let r = self.deepen(p, o, moves, now(), f64::INFINITY, 60);
        debug_assert!(r.solved);
        (r.best_move, r.score)
    }

    /// The iterative-deepening loop.
    fn deepen(
        &mut self,
        p: u64,
        o: u64,
        moves: u64,
        start: f64,
        time_limit: f64,
        max_depth: u32,
    ) -> SearchResult {
        let result = |best_move, score, depth, nodes, solved| SearchResult {
            best_move,
            score,
            depth,
            nodes,
            solved,
        };
        let n_empty = (!(p | o)).count_ones();
        let (mut best_move, mut best_score, mut done_depth) = (0, 0.0, 0);
        let mut solved = false;
        for depth in 1..=max_depth.min(n_empty) {
            self.iter_best = None;
            match self.root(p, o, depth as i32, best_move) {
                Ok((m, s)) => (best_move, best_score, done_depth) = (m, s, depth),
                Err(Timeout) => {
                    // the previous best move is searched first, so any better move found so far is safe to use
                    if let Some((m, s)) = self.iter_best {
                        if depth > 1 {
                            (best_move, best_score) = (m, s);
                        }
                    }
                    break;
                }
            }
            if depth >= n_empty {
                solved = true;
                break;
            }
            if now() - start > time_limit * NEXT_DEPTH_TIME_RATIO {
                break; // with the time left, the next depth could not even finish its first move
            }
        }
        if best_move == 0 {
            best_move = self.ordered(p, o, moves, 0, 0)[0]; // fallback when not even depth 1 finished
        }
        result(best_move, best_score, done_depth, self.nodes, solved)
    }

    /// Search every legal move to `depth` with a full window and return (move, score), best first.
    pub fn score_moves(&mut self, p: u64, o: u64, depth: u32) -> Vec<(u64, f64)> {
        self.tt.clear();
        self.nodes = 0;
        self.deadline = None;
        let mut results = Vec::new();
        let f = self.root_features(p, o);
        let track = Self::track_children(f.as_ref(), p, o, depth as i32);
        for x in self.ordered(p, o, legal_moves(p, o), 0, depth as i32) {
            let (np, no) = play(p, o, x);
            let cf = Self::child_features(f.as_ref(), track, p, x, no);
            let score = -self
                .visit(
                    np,
                    no,
                    cf.as_ref(),
                    depth as i32 - 1,
                    f64::NEG_INFINITY,
                    f64::INFINITY,
                )
                .expect("no time limit, so the search cannot time out");
            results.push((x, score));
        }
        // highest score first, ties by square index (same order as Python)
        results.sort_by(|a, b| cmp_f64(b.1, a.1).then(a.0.cmp(&b.0)));
        results
    }

    pub fn nodes(&self) -> u64 {
        self.nodes
    }

    fn check_time(&self) -> Result<(), Timeout> {
        match self.deadline {
            Some(d) if now() > d => Err(Timeout),
            _ => Ok(()),
        }
    }

    /// Order the moves to search (same order as Python's `_ordered`).
    fn ordered(&self, p: u64, o: u64, moves: u64, tt_move: u64, depth: i32) -> Vec<u64> {
        let mut list: Vec<u64> = bits(moves).collect();
        if list.len() > 1 {
            if depth >= 3 {
                // fastest-first: fewest opponent replies first (then higher weight, then square index)
                let mut keyed: Vec<(f64, u64)> = list
                    .iter()
                    .map(|&x| {
                        let (np, no) = play(p, o, x);
                        let mobility = legal_moves(np, no).count_ones() * 1000;
                        (f64::from(mobility) - self.eval.weight(x), x)
                    })
                    .collect();
                keyed.sort_by(|a, b| cmp_f64(a.0, b.0).then(a.1.cmp(&b.1)));
                list = keyed.into_iter().map(|(_, x)| x).collect();
            } else {
                // highest weight first (stable sort keeps square order for equal weights)
                list.sort_by(|a, b| cmp_f64(self.eval.weight(*b), self.eval.weight(*a)));
            }
        }
        if tt_move != 0 {
            if let Some(i) = list.iter().position(|&x| x == tt_move) {
                list.remove(i);
                list.insert(0, tt_move);
            }
        }
        list
    }

    /// `PAT`: `f` holds the pattern indices of (`p`, `o`) and the leaves use them.
    fn negamax<const PAT: bool>(
        &mut self,
        p: u64,
        o: u64,
        f: &Features,
        depth: i32,
        mut alpha: f64,
        beta: f64,
    ) -> Result<f64, Timeout> {
        self.nodes += 1;
        if self.nodes.is_multiple_of(TIME_CHECK_INTERVAL) {
            self.check_time()?;
        }

        let moves = legal_moves(p, o);
        if moves == 0 {
            if legal_moves(o, p) == 0 {
                return Ok(final_score(p, o));
            }
            // pass
            return Ok(if PAT {
                -self.negamax::<true>(o, p, &f.passed(), depth, -beta, -alpha)?
            } else {
                -self.negamax::<false>(o, p, f, depth, -beta, -alpha)?
            });
        }
        if depth <= 0 {
            return Ok(if PAT {
                self.evaluate_incremental(p, o, moves, f)
            } else {
                self.evaluate(p, o, moves)
            });
        }

        let key = (p, o);
        let mut tt_move = 0;
        if let Some(e) = self.tt.get(&key) {
            tt_move = e.best_move;
            if e.depth >= depth {
                match e.bound {
                    Bound::Exact => return Ok(e.value),
                    Bound::Lower if e.value >= beta => return Ok(e.value),
                    Bound::Upper if e.value <= alpha => return Ok(e.value),
                    _ => {}
                }
            }
        }

        let original_alpha = alpha;
        let mut best = f64::NEG_INFINITY;
        let mut best_move = 0;
        let f = PAT.then_some(f);
        let track = Self::track_children(f, p, o, depth);
        for (i, x) in self
            .ordered(p, o, moves, tt_move, depth)
            .into_iter()
            .enumerate()
        {
            let (np, no) = play(p, o, x);
            let cf = Self::child_features(f, track, p, x, no);
            let score = if i == 0 {
                -self.visit(np, no, cf.as_ref(), depth - 1, -beta, -alpha)?
            } else {
                // PVS: test with a null window whether the move beats alpha; re-search if it does
                let s =
                    -self.visit(np, no, cf.as_ref(), depth - 1, -alpha - NULL_WINDOW, -alpha)?;
                if alpha < s && s < beta {
                    -self.visit(np, no, cf.as_ref(), depth - 1, -beta, -s)?
                } else {
                    s
                }
            };
            if score > best {
                best = score;
                best_move = x;
                if score > alpha {
                    alpha = score;
                    if alpha >= beta {
                        break;
                    }
                }
            }
        }

        let bound = if best <= original_alpha {
            Bound::Upper
        } else if best >= beta {
            Bound::Lower
        } else {
            Bound::Exact
        };
        self.tt.insert(
            key,
            Entry {
                depth,
                bound,
                value: best,
                best_move,
            },
        );
        Ok(best)
    }

    /// Search every root move and return (best move, score).
    fn root(&mut self, p: u64, o: u64, depth: i32, prev_best: u64) -> Result<(u64, f64), Timeout> {
        let beta = f64::INFINITY;
        let mut alpha = f64::NEG_INFINITY;
        let mut best_move = 0;
        let f = self.root_features(p, o);
        let track = Self::track_children(f.as_ref(), p, o, depth);
        for (i, x) in self
            .ordered(p, o, legal_moves(p, o), prev_best, depth)
            .into_iter()
            .enumerate()
        {
            let (np, no) = play(p, o, x);
            let cf = Self::child_features(f.as_ref(), track, p, x, no);
            let score = if i == 0 {
                -self.visit(np, no, cf.as_ref(), depth - 1, -beta, -alpha)?
            } else {
                let s =
                    -self.visit(np, no, cf.as_ref(), depth - 1, -alpha - NULL_WINDOW, -alpha)?;
                if s > alpha {
                    -self.visit(np, no, cf.as_ref(), depth - 1, -beta, -s)?
                } else {
                    s
                }
            };
            if score > alpha {
                alpha = score;
                best_move = x;
                self.iter_best = Some((best_move, alpha));
            }
        }
        Ok((best_move, alpha))
    }
}

/// Comparison with the meaning of Python's `<` (0.0 equals -0.0). Values are never NaN.
fn cmp_f64(a: f64, b: f64) -> std::cmp::Ordering {
    a.partial_cmp(&b).unwrap_or(std::cmp::Ordering::Equal)
}

/// Deadline `time_limit` seconds after `start`; no limit for infinity or NaN.
fn deadline_after(start: f64, time_limit: f64) -> Option<f64> {
    time_limit.is_finite().then(|| start + time_limit.max(0.0))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::board::bits;

    const START: (u64, u64) = (0x0000_0008_1000_0000, 0x0000_0010_0800_0000);

    fn searcher() -> Searcher {
        let weights: Vec<f64> = (0..64).map(|i| ((i * 7) % 11) as f64 - 5.0).collect();
        let coeffs = [1.0, 0.7, 0.3, 0.2, 1.0, 0.6, 0.4, 0.3, 0.0, 0.5, 1.0, 0.1];
        Searcher::new(Evaluator::new(&coeffs, &weights).unwrap())
    }

    /// Position after n random moves from the start (a simple LCG keeps it reproducible)
    fn random_position(seed: u64, n: u32) -> (u64, u64) {
        let (mut p, mut o) = START;
        let mut r = seed;
        for _ in 0..n {
            let moves = legal_moves(p, o);
            if moves == 0 {
                if legal_moves(o, p) == 0 {
                    break;
                }
                (p, o) = (o, p);
                continue;
            }
            r = r
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let list: Vec<u64> = bits(moves).collect();
            let x = list[(r >> 33) as usize % list.len()];
            (p, o) = play(p, o, x);
        }
        (p, o)
    }

    /// Exact value by plain negamax without pruning
    fn brute_force(p: u64, o: u64) -> f64 {
        let moves = legal_moves(p, o);
        if moves == 0 {
            if legal_moves(o, p) == 0 {
                return final_score(p, o);
            }
            return -brute_force(o, p);
        }
        bits(moves)
            .map(|x| {
                let (np, no) = play(p, o, x);
                -brute_force(np, no)
            })
            .fold(f64::NEG_INFINITY, f64::max)
    }

    #[test]
    fn returns_legal_move() {
        let mut s = searcher();
        for seed in 0..20 {
            let (p, o) = random_position(seed, 20);
            let moves = legal_moves(p, o);
            let r = s.search(p, o, f64::INFINITY, 4);
            if moves == 0 {
                assert_eq!(r.best_move, 0);
            } else {
                assert_ne!(r.best_move & moves, 0);
            }
        }
    }

    #[test]
    fn endgame_solve_matches_brute_force() {
        let mut s = searcher();
        for seed in 0..10 {
            let (p, o) = random_position(seed, 52);
            if legal_moves(p, o).count_ones() < 2 {
                continue;
            }
            let r = s.search(p, o, f64::INFINITY, 60);
            assert!(r.solved);
            assert_eq!(r.score, brute_force(p, o), "seed {seed}");
        }
    }

    #[test]
    fn score_moves_is_sorted_and_agrees_with_search() {
        let mut s = searcher();
        let (p, o) = random_position(3, 16);
        let scored = s.score_moves(p, o, 4);
        assert!(scored.windows(2).all(|w| w[0].1 >= w[1].1));
        let r = s.search(p, o, f64::INFINITY, 4);
        assert_eq!(scored[0].1, r.score);
    }

    #[test]
    fn incremental_pattern_evaluation_gives_identical_results() {
        // random pattern weights; the search with incrementally updated indices must return the same
        // move, score and node count as the search that recomputes them at every leaf. Positions cover
        // the opening to the endgame (where depth >= empties switches the updates off) and passes.
        // In debug builds every incremental leaf is also checked against a full recomputation.
        let mut w = PatternWeights::zeros();
        let mut r = crate::selfplay::Rng::new(11);
        for st in &mut w.stages {
            st.bias = r.below(201) as i32 - 100;
            st.mobility = r.below(41) as i32 - 20;
            for v in st.table.iter_mut() {
                *v = r.below(2001) as i16 - 1000;
            }
        }
        let w = Arc::new(w);
        let mut passes = 0;
        for seed in 0..40 {
            let (p, o) = random_position(seed, 8 + (seed as u32 * 7) % 48);
            if legal_moves(p, o).count_ones() < 2 {
                continue;
            }
            let depth = if (!(p | o)).count_ones() <= 12 { 12 } else { 5 };
            let mut inc = searcher().with_patterns(w.clone());
            let mut full = searcher().with_patterns(w.clone());
            full.incremental = false;
            let a = inc.search(p, o, f64::INFINITY, depth);
            let b = full.search(p, o, f64::INFINITY, depth);
            assert_eq!(a, b, "seed {seed}");
            assert_eq!(
                inc.score_moves(p, o, 3),
                full.score_moves(p, o, 3),
                "seed {seed}"
            );
            // count passes within two plies of the root, to make sure the trees contain passes
            for x in bits(legal_moves(p, o)) {
                let (np, no) = play(p, o, x);
                passes += usize::from(legal_moves(np, no) == 0);
                for y in bits(legal_moves(np, no)) {
                    let (qp, qo) = play(np, no, y);
                    passes += usize::from(legal_moves(qp, qo) == 0 && legal_moves(qo, qp) != 0);
                }
            }
        }
        assert!(passes > 0);
    }

    #[test]
    fn respects_time_limit() {
        let mut s = searcher();
        let (p, o) = random_position(5, 8);
        let t = std::time::Instant::now();
        let r = s.search(p, o, 0.05, 60);
        assert!(t.elapsed().as_secs_f64() < 0.5);
        assert_ne!(r.best_move & legal_moves(p, o), 0);
    }

    #[test]
    fn deadline_handles_extreme_values() {
        assert!(deadline_after(0.0, f64::INFINITY).is_none());
        assert!(deadline_after(0.0, f64::NAN).is_none());
        assert_eq!(deadline_after(1.0, -5.0), Some(1.0));
        assert_eq!(deadline_after(1.0, 2.0), Some(3.0));
    }
}
