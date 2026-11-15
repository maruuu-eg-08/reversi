//! 探索。`backend/strong_ai.py` の `StrongAI` と同じ手順で読む。
//!
//! 時間制限なし（固定の深さ）で読んだ場合、Python 版と同じ最善手・評価値・探索局面数になる
//! （tests/test_rust_engine.py で確認）。違いは速さだけなので、同じ時間ならより深く読める。

use std::sync::Arc;

use rustc_hash::FxHashMap;

use crate::board::{bits, legal_moves, play};
use crate::clock::now;
use crate::eval::{final_score, Evaluator};
use crate::pattern::PatternWeights;

/// PVS のヌルウィンドウの幅（Python 版と同じ値）
const NULL_WINDOW: f64 = 1e-6;
/// この局面数ごとに時間切れかどうかを確かめる
const TIME_CHECK_INTERVAL: u64 = 1024;
/// 経過時間がこの割合を超えたら、次の深さを読み始めない
const NEXT_DEPTH_TIME_RATIO: f64 = 0.7;

/// 置換表の値の種類
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

/// 時間切れで探索を打ち切ったことを表す
#[derive(Debug)]
struct Timeout;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SearchResult {
    /// 最善手（1ビット）。打てる手がなければ 0
    pub best_move: u64,
    /// 手番側から見た評価値
    pub score: f64,
    /// 読み終えた深さ
    pub depth: u32,
    /// 探索した局面数
    pub nodes: u64,
    /// 終局まで読み切ったか
    pub solved: bool,
}

pub struct Searcher {
    /// 線形評価（パターン評価を使う場合も、手の並べ替えにはこの位置の重みを使う）
    eval: Evaluator,
    /// パターン評価の重み。あれば葉の評価にこちらを使う
    pattern: Option<Arc<PatternWeights>>,
    tt: FxHashMap<(u64, u64), Entry>,
    nodes: u64,
    /// 打ち切る時刻（`clock::now()` の秒）
    deadline: Option<f64>,
    /// 読みかけの深さで、ここまでに見つかった最善手（時間切れのときに使う）
    iter_best: Option<(u64, f64)>,
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
        }
    }

    /// 葉の評価にパターン評価を使うようにする。
    pub fn with_patterns(mut self, weights: Arc<PatternWeights>) -> Self {
        self.pattern = Some(weights);
        self
    }

    /// 手番側 `p` から見た静的評価値（深さ0）。`my_moves` は `legal_moves(p, o)`。
    #[inline]
    pub fn evaluate(&self, p: u64, o: u64, my_moves: u64) -> f64 {
        match &self.pattern {
            Some(w) => w.evaluate(p, o, my_moves, legal_moves(o, p)),
            None => self.eval.evaluate(p, o, my_moves),
        }
    }

    /// 反復深化で読む。`time_limit` 秒（無限大なら制限なし）か深さ `max_depth` まで。
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
            return result(moves, 0.0, 0, 0, false); // 打てる手が1つだけ
        }
        self.deepen(p, o, moves, start, time_limit, max_depth)
    }

    /// 終局まで読み切り、(最善手, 手番側から見た正確な評価値) を返す。
    /// `search` と違い、打てる手が1つだけの局面でも読んで正確な値を返す。打てる手がない局面には使えない。
    pub fn solve(&mut self, p: u64, o: u64) -> (u64, f64) {
        let moves = legal_moves(p, o);
        assert_ne!(moves, 0, "solve は打てる手がある局面で呼ぶ");
        self.tt.clear();
        self.nodes = 0;
        self.deadline = None;
        let r = self.deepen(p, o, moves, now(), f64::INFINITY, 60);
        debug_assert!(r.solved);
        (r.best_move, r.score)
    }

    /// 反復深化の本体。
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
                    // 前回の最善手を最初に読むので、それより良い手が見つかっていれば採用する
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
                break; // 残り時間では次の深さの最初の手すら読み終わらない
            }
        }
        if best_move == 0 {
            best_move = self.ordered(p, o, moves, 0, 0)[0]; // 深さ1すら読み終わらなかった場合
        }
        result(best_move, best_score, done_depth, self.nodes, solved)
    }

    /// 全合法手を `depth` 手先まで全幅窓で読み、良い順に (手, 評価値) を返す。
    pub fn score_moves(&mut self, p: u64, o: u64, depth: u32) -> Vec<(u64, f64)> {
        self.tt.clear();
        self.nodes = 0;
        self.deadline = None;
        let mut results = Vec::new();
        for x in self.ordered(p, o, legal_moves(p, o), 0, depth as i32) {
            let (np, no) = play(p, o, x);
            let score = -self
                .negamax(np, no, depth as i32 - 1, f64::NEG_INFINITY, f64::INFINITY)
                .expect("時間制限なしなので打ち切られない");
            results.push((x, score));
        }
        // 評価値の高い順、同点はマスの番号順（Python 版と同じ並び）
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

    /// 探索する手の順番を決める（Python 版の `_ordered` と同じ並び）。
    fn ordered(&self, p: u64, o: u64, moves: u64, tt_move: u64, depth: i32) -> Vec<u64> {
        let mut list: Vec<u64> = bits(moves).collect();
        if list.len() > 1 {
            if depth >= 3 {
                // 速さ優先: 打った後の相手の着手可能数が少ない手から（同数なら重みの高い手、さらに同じならマスの番号順）
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
                // 重みの高い順（安定ソートなので同じ重みはマスの番号順のまま）
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

    fn negamax(
        &mut self,
        p: u64,
        o: u64,
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
            return Ok(-self.negamax(o, p, depth, -beta, -alpha)?); // パス
        }
        if depth <= 0 {
            return Ok(self.evaluate(p, o, moves));
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
        for (i, x) in self
            .ordered(p, o, moves, tt_move, depth)
            .into_iter()
            .enumerate()
        {
            let (np, no) = play(p, o, x);
            let score = if i == 0 {
                -self.negamax(np, no, depth - 1, -beta, -alpha)?
            } else {
                // PVS: まずヌルウィンドウで「alpha を超えるか」だけ調べ、超えたら読み直す
                let s = -self.negamax(np, no, depth - 1, -alpha - NULL_WINDOW, -alpha)?;
                if alpha < s && s < beta {
                    -self.negamax(np, no, depth - 1, -beta, -s)?
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

    /// ルートで全手を読み、(最善手, 評価値) を返す。
    fn root(&mut self, p: u64, o: u64, depth: i32, prev_best: u64) -> Result<(u64, f64), Timeout> {
        let beta = f64::INFINITY;
        let mut alpha = f64::NEG_INFINITY;
        let mut best_move = 0;
        for (i, x) in self
            .ordered(p, o, legal_moves(p, o), prev_best, depth)
            .into_iter()
            .enumerate()
        {
            let (np, no) = play(p, o, x);
            let score = if i == 0 {
                -self.negamax(np, no, depth - 1, -beta, -alpha)?
            } else {
                let s = -self.negamax(np, no, depth - 1, -alpha - NULL_WINDOW, -alpha)?;
                if s > alpha {
                    -self.negamax(np, no, depth - 1, -beta, -s)?
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

/// Python の `<` と同じ意味の比較（0.0 と -0.0 は等しい）。値に NaN は現れない。
fn cmp_f64(a: f64, b: f64) -> std::cmp::Ordering {
    a.partial_cmp(&b).unwrap_or(std::cmp::Ordering::Equal)
}

/// `time_limit` 秒後の時刻。無限大や NaN なら制限なし。
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

    /// 開始局面から乱数で n 手進めた局面（簡単な線形合同法で再現性を保つ）
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

    /// 単純な（枝刈りなしの）negamax による終局までの正確な値
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
