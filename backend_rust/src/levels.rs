//! Rust port of the Lv.1-4 AIs and the web analysis view (for the browser).
//!
//! Searches exactly like `backend/random_ai.py`, `weighted_ai.py`, `minimax.py` and `alphabeta_ai.py`.
//! Lv.2/3 choose randomly among equally good moves, so the set of best moves is compared with Python;
//! for Lv.4 the move, scores and node count are compared (tests/test_rust_web_port.py).
//!
//! Boards are taken like the Python versions: (black, white, color to move 1 = black / -1 = white).

use rustc_hash::FxHashMap;

use crate::board::{bits, flips, legal_moves};

/// Evaluation parameters (same values as `backend/weights.py`; checked by a test)
pub mod params {
    pub const POSITION_WEIGHTS: [f64; 64] = [
        27.87, 10.59, 27.35, 15.77, 15.77, 27.35, 10.59, 27.87, //
        10.59, 4.51, 33.77, -25.49, -25.49, 33.77, 4.51, 10.59, //
        27.35, 33.77, 0.61, -6.42, -6.42, 0.61, 33.77, 27.35, //
        15.77, -25.49, -6.42, 25.08, 25.08, -6.42, -25.49, 15.77, //
        15.77, -25.49, -6.42, 25.08, 25.08, -6.42, -25.49, 15.77, //
        27.35, 33.77, 0.61, -6.42, -6.42, 0.61, 33.77, 27.35, //
        10.59, 4.51, 33.77, -25.49, -25.49, 33.77, 4.51, 10.59, //
        27.87, 10.59, 27.35, 15.77, 15.77, 27.35, 10.59, 27.87,
    ];
    pub const EVAL_COEFFS: [f64; 9] = [
        1.11265999, 0.73565285, 0.34340917, //
        1.05687437, 0.65200396, 0.43294245, //
        -0.0449974, 0.53306816, 1.0032734,
    ];
    pub const WEIGHTED_AI_WEIGHTS: [f64; 64] = [
        50.0, 17.29, 6.81, 11.32, 11.32, 6.81, 17.29, 50.0, //
        17.29, 18.43, 38.49, -28.38, -28.38, 38.49, 18.43, 17.29, //
        6.81, 38.49, -17.33, -11.03, -11.03, -17.33, 38.49, 6.81, //
        11.32, -28.38, -11.03, 18.70, 18.70, -11.03, -28.38, 11.32, //
        11.32, -28.38, -11.03, 18.70, 18.70, -11.03, -28.38, 11.32, //
        6.81, 38.49, -17.33, -11.03, -11.03, -17.33, 38.49, 6.81, //
        17.29, 18.43, 38.49, -28.38, -28.38, 38.49, 18.43, 17.29, //
        50.0, 17.29, 6.81, 11.32, 11.32, 6.81, 17.29, 50.0,
    ];
    /// Weight table of MinimaxAI in `minimax.py`
    pub const MINIMAX_WEIGHTS: [i32; 64] = [
        30, -12, 0, -1, -1, 0, -12, 30, //
        -12, -15, -3, -3, -3, -3, -15, -12, //
        0, -3, 0, -1, -1, 0, -3, 0, //
        -1, -3, -1, -1, -1, -1, -3, -1, //
        -1, -3, -1, -1, -1, -1, -3, -1, //
        0, -3, 0, -1, -1, 0, -3, 0, //
        -12, -15, -3, -3, -3, -3, -15, -12, //
        30, -12, 0, -1, -1, 0, -12, 30,
    ];
    pub const STRONG_EVAL_COEFFS: [f64; 12] = [
        -0.0148403, -0.0521191, 4.72193, 5.18808, //
        0.0284557, 1.34012, 1.2702, 1.5966, //
        0.0176706, 2.25813, 0.871555, 0.799645,
    ];
    pub const WIN_SCORE: f64 = 10_000.0;
}

use params::*;

/// (black, white, color to move) -> (player, opponent)
#[inline]
fn sides(black: u64, white: u64, color: i8) -> (u64, u64) {
    if color == 1 {
        (black, white)
    } else {
        (white, black)
    }
}

/// (black, white) after `color` plays `x`
#[inline]
fn put(black: u64, white: u64, color: i8, x: u64) -> (u64, u64) {
    let (p, o) = sides(black, white, color);
    let f = flips(p, o, x);
    let (np, no) = (p | x | f, o ^ f);
    if color == 1 {
        (np, no)
    } else {
        (no, np)
    }
}

/// Legal moves in the order of Python's `BitBoard.listUp` (increasing square index)
fn list_moves(black: u64, white: u64, color: i8) -> Vec<u64> {
    let (p, o) = sides(black, white, color);
    bits(legal_moves(p, o)).collect()
}

fn sq(x: u64) -> usize {
    x.trailing_zeros() as usize
}

// ---------- Lv.2: WeightedAI ----------

/// Score the board after each move with the weight table and return the best moves (Python picks one at random).
pub fn weighted_best_moves(black: u64, white: u64, color: i8) -> Vec<u64> {
    let evaluate = |b: u64, w: u64| {
        let mut score = 0.0;
        for (i, &wt) in WEIGHTED_AI_WEIGHTS.iter().enumerate() {
            if (b >> i) & 1 != 0 {
                score += wt;
            } else if (w >> i) & 1 != 0 {
                score -= wt;
            }
        }
        if color == 1 {
            score
        } else {
            -score
        }
    };
    best_by(list_moves(black, white, color), |x| {
        let (b, w) = put(black, white, color, x);
        evaluate(b, w)
    })
}

/// All moves with the maximum score, in their original order
fn best_by<T: PartialOrd + Copy>(moves: Vec<u64>, mut score: impl FnMut(u64) -> T) -> Vec<u64> {
    let mut best: Option<T> = None;
    let mut out = Vec::new();
    for x in moves {
        let s = score(x);
        match best {
            Some(b) if s < b => {}
            Some(b) if s == b => out.push(x),
            _ => {
                best = Some(s);
                out = vec![x];
            }
        }
    }
    out
}

// ---------- Lv.3: MinimaxAI ----------

/// Best moves of a depth-`depth` minimax (Python picks one at random).
pub fn minimax_best_moves(black: u64, white: u64, color: i8, depth: i32) -> Vec<u64> {
    let me = color;
    let evaluate = |b: u64, w: u64| -> i32 {
        let mut score = 0;
        for (i, &wt) in MINIMAX_WEIGHTS.iter().enumerate() {
            if (b >> i) & 1 != 0 {
                score += wt;
            } else if (w >> i) & 1 != 0 {
                score -= wt;
            }
        }
        if me == 1 {
            score
        } else {
            -score
        }
    };
    fn minimax(
        b: u64,
        w: u64,
        depth: i32,
        maximizing: bool,
        color: i8,
        eval: &dyn Fn(u64, u64) -> i32,
    ) -> i32 {
        if depth == 0 {
            return eval(b, w);
        }
        let moves = list_moves(b, w, color);
        if moves.is_empty() {
            if list_moves(b, w, -color).is_empty() {
                return eval(b, w);
            }
            return minimax(b, w, depth, !maximizing, -color, eval);
        }
        let scores = moves.into_iter().map(|x| {
            let (nb, nw) = put(b, w, color, x);
            minimax(nb, nw, depth - 1, !maximizing, -color, eval)
        });
        if maximizing {
            scores.max().unwrap()
        } else {
            scores.min().unwrap()
        }
    }
    best_by(list_moves(black, white, color), |x| {
        let (b, w) = put(black, white, color, x);
        minimax(b, w, depth - 1, false, -color, &evaluate)
    })
}

// ---------- Lv.4: AlphaBetaAI ----------

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Exact,
    Lower,
    Upper,
}

/// AlphaBetaAI from `alphabeta_ai.py` (default weights and coefficients)
pub struct AlphaBeta {
    color: i8,
    depth: i32,
    tt: FxHashMap<(u64, u64, i8), (f64, i32, Kind)>,
    pub nodes: u64,
}

impl AlphaBeta {
    pub fn new(color: i8, depth: i32) -> Self {
        Self {
            color,
            depth,
            tt: FxHashMap::default(),
            nodes: 0,
        }
    }

    fn weight_sum(b: u64) -> f64 {
        bits(b).fold(0.0, |acc, x| acc + POSITION_WEIGHTS[sq(x)])
    }

    fn final_score(&self, black: u64, white: u64) -> f64 {
        let (me, opp) = sides(black, white, self.color);
        let diff = f64::from(me.count_ones() as i32 - opp.count_ones() as i32);
        if diff > 0.0 {
            WIN_SCORE + diff
        } else if diff < 0.0 {
            -WIN_SCORE + diff
        } else {
            0.0
        }
    }

    fn evaluate(&self, black: u64, white: u64) -> f64 {
        let (me, opp) = sides(black, white, self.color);
        let (mc, oc) = (me.count_ones() as i32, opp.count_ones() as i32);
        let empty = 64 - mc - oc;
        let position = Self::weight_sum(me) - Self::weight_sum(opp);
        let mobility = f64::from(
            legal_moves(me, opp).count_ones() as i32 - legal_moves(opp, me).count_ones() as i32,
        );
        let disc = f64::from(mc - oc);
        let c = if empty >= 45 {
            &EVAL_COEFFS[0..3]
        } else if empty >= 15 {
            &EVAL_COEFFS[3..6]
        } else {
            &EVAL_COEFFS[6..9]
        };
        position * c[0] + mobility * c[1] + disc * c[2]
    }

    /// Highest weight first (equal weights keep square order)
    fn ordered(moves: Vec<u64>) -> Vec<u64> {
        let mut moves = moves;
        moves.sort_by(|a, b| {
            POSITION_WEIGHTS[sq(*b)]
                .partial_cmp(&POSITION_WEIGHTS[sq(*a)])
                .unwrap()
        });
        moves
    }

    /// Best move (0 if there is none)
    pub fn get_move(&mut self, black: u64, white: u64) -> u64 {
        self.tt.clear();
        self.nodes = 0;
        let moves = list_moves(black, white, self.color);
        if moves.is_empty() {
            return 0;
        }
        let mut alpha = f64::NEG_INFINITY;
        let beta = f64::INFINITY;
        let mut max_val = f64::NEG_INFINITY;
        let mut best = moves[0];
        for x in Self::ordered(moves) {
            let (b, w) = put(black, white, self.color, x);
            let score = self.alphabeta(b, w, self.depth - 1, alpha, beta, false, -self.color);
            if score > max_val {
                max_val = score;
                best = x;
            }
            alpha = alpha.max(max_val);
        }
        best
    }

    /// Score of every legal move (full-window search), best first
    pub fn analyze(&mut self, black: u64, white: u64) -> Vec<(u64, f64)> {
        self.tt.clear();
        self.nodes = 0;
        let mut results = Vec::new();
        for x in Self::ordered(list_moves(black, white, self.color)) {
            let (b, w) = put(black, white, self.color, x);
            let score = self.alphabeta(
                b,
                w,
                self.depth - 1,
                f64::NEG_INFINITY,
                f64::INFINITY,
                false,
                -self.color,
            );
            results.push((x, score));
        }
        // stable sort keeps equal scores in search order (like Python's sort(reverse=True))
        results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
        results
    }

    #[allow(clippy::too_many_arguments)]
    fn alphabeta(
        &mut self,
        b: u64,
        w: u64,
        depth: i32,
        mut alpha: f64,
        mut beta: f64,
        maximizing: bool,
        color: i8,
    ) -> f64 {
        self.nodes += 1;
        let key = (b, w, color);
        let (original_alpha, original_beta) = (alpha, beta);
        if let Some(&(score, d, kind)) = self.tt.get(&key) {
            if d >= depth {
                match kind {
                    Kind::Exact => return score,
                    Kind::Lower => alpha = alpha.max(score),
                    Kind::Upper => beta = beta.min(score),
                }
                if alpha >= beta {
                    return score;
                }
            }
        }

        let moves = list_moves(b, w, color);
        if moves.is_empty() {
            if list_moves(b, w, -color).is_empty() {
                return self.final_score(b, w);
            }
            return self.alphabeta(b, w, depth, alpha, beta, !maximizing, -color);
        }
        if depth == 0 {
            return self.evaluate(b, w);
        }

        let mut best;
        if maximizing {
            best = f64::NEG_INFINITY;
            for x in Self::ordered(moves) {
                let (nb, nw) = put(b, w, color, x);
                let score = self.alphabeta(nb, nw, depth - 1, alpha, beta, false, -color);
                best = best.max(score);
                alpha = alpha.max(best);
                if alpha >= beta {
                    break;
                }
            }
        } else {
            best = f64::INFINITY;
            for x in Self::ordered(moves) {
                let (nb, nw) = put(b, w, color, x);
                let score = self.alphabeta(nb, nw, depth - 1, alpha, beta, true, -color);
                best = best.min(score);
                beta = beta.min(best);
                if beta <= alpha {
                    break;
                }
            }
        }
        let kind = if best <= original_alpha {
            Kind::Upper
        } else if best >= original_beta {
            Kind::Lower
        } else {
            Kind::Exact
        };
        self.tt.insert(key, (best, depth, kind));
        best
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const START: (u64, u64) = (0x0000_0008_1000_0000, 0x0000_0010_0800_0000);

    #[test]
    fn levels_return_legal_moves_from_start() {
        let (b, w) = START;
        let legal = legal_moves(b, w);
        for x in weighted_best_moves(b, w, 1)
            .into_iter()
            .chain(minimax_best_moves(b, w, 1, 3))
        {
            assert_ne!(x & legal, 0);
        }
        let mut ab = AlphaBeta::new(1, 4);
        assert_ne!(ab.get_move(b, w) & legal, 0);
        assert!(ab.nodes > 0);
        let scores = ab.analyze(b, w);
        assert_eq!(scores.len(), 4);
        assert!(scores.windows(2).all(|p| p[0].1 >= p[1].1));
    }

    #[test]
    fn best_move_lists_are_nonempty_and_legal() {
        // even in the symmetric start position the float sums can differ slightly, so not all moves tie
        // (Python behaves the same; agreement is checked in tests/test_rust_web_port.py)
        let (b, w) = START;
        let best = weighted_best_moves(b, w, 1);
        assert!(!best.is_empty() && best.len() <= 4);
        assert!(best.iter().all(|&x| x & legal_moves(b, w) != 0));
    }

    #[test]
    fn alphabeta_scores_finished_game_by_result() {
        // a position where neither side can move is scored by the result (disc difference)
        let black = 1u64 << 9; // a single black disc on b2
        let white = 0u64;
        let ab = AlphaBeta::new(1, 3);
        assert_eq!(ab.final_score(black, white), WIN_SCORE + 1.0);
    }
}
