//! パターン評価を学習するための自己対戦データの生成。
//!
//! 1局の流れ:
//! 1. 序盤はランダムな手を `random_min`〜`random_max` 手打つ（局面の多様性のため）
//! 2. その後は双方が深さ `depth` で読んで打つ
//! 3. 空きマスが `solve_empties` 以下になったら終局まで読み切り、最善手で打ち進める
//!
//! 各局面の正解ラベルは「その局面の手番側から見た最終石差」。読み切りを始めた局面より後は
//! 完全読みの正確な値で、それより前は「読み切りを始めた局面の正確な値」（＝そこから先は
//! 双方が最善を尽くした場合の結果）を使う。空きマスは勝った側に加える（`final_score` と同じ）。
//!
//! 各局はゲーム番号から決まる乱数だけを使うので、同じ設定なら並列数によらず同じデータになる。

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use crate::board::{bits, legal_moves, play};
use crate::eval::{final_score, Evaluator, WIN_SCORE};
use crate::search::Searcher;

/// 1局面分のレコードの大きさ（バイト）
pub const RECORD_SIZE: usize = 22;

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub depth: u32,
    pub random_min: u32,
    pub random_max: u32,
    pub solve_empties: u32,
    pub seed: u64,
}

/// 学習データの1局面
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Record {
    /// 手番側の石
    pub p: u64,
    /// 相手の石
    pub o: u64,
    /// 手番側から見た最終石差（空きマスは勝者に加える）
    pub score: i8,
    /// 開始局面からの手数
    pub ply: u8,
    /// ゲーム番号（学習用と検証用をゲーム単位で分けるため）
    pub game: u32,
}

impl Record {
    /// リトルエンディアンで `RECORD_SIZE` バイトにする。
    pub fn to_bytes(&self) -> [u8; RECORD_SIZE] {
        let mut b = [0u8; RECORD_SIZE];
        b[0..8].copy_from_slice(&self.p.to_le_bytes());
        b[8..16].copy_from_slice(&self.o.to_le_bytes());
        b[16] = self.score as u8;
        b[17] = self.ply;
        b[18..22].copy_from_slice(&self.game.to_le_bytes());
        b
    }

    pub fn from_bytes(b: &[u8]) -> Self {
        Self {
            p: u64::from_le_bytes(b[0..8].try_into().unwrap()),
            o: u64::from_le_bytes(b[8..16].try_into().unwrap()),
            score: b[16] as i8,
            ply: b[17],
            game: u32::from_le_bytes(b[18..22].try_into().unwrap()),
        }
    }
}

/// SplitMix64: 小さく速い、再現性のある乱数
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Self {
        Self(seed)
    }

    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// 0 以上 n 未満の整数（n > 0）
    pub fn below(&mut self, n: u64) -> u64 {
        // n は小さいので剰余の偏りは無視できる
        self.next_u64() % n
    }
}

/// 完全読みの評価値（`WIN_SCORE` ± 石差、または引き分けの 0）を石差に直す。
fn exact_discs(score: f64) -> i32 {
    if score >= WIN_SCORE {
        (score - WIN_SCORE) as i32
    } else if score <= -WIN_SCORE {
        (score + WIN_SCORE) as i32
    } else {
        assert_eq!(score, 0.0, "完全読みの値が終局の値になっていない: {score}");
        0
    }
}

/// 1局打ち、その対局のレコードを手数の順に返す。
pub fn play_game(game: u32, cfg: &Config, searcher: &mut Searcher) -> Vec<Record> {
    let mut rng = Rng::new(cfg.seed ^ u64::from(game).wrapping_mul(0xD1B5_4A32_D192_ED03));
    let n_random =
        cfg.random_min + rng.below(u64::from(cfg.random_max - cfg.random_min + 1)) as u32;

    let (mut p, mut o) = (0x0000_0008_1000_0000u64, 0x0000_0010_0800_0000u64);
    let mut black_to_move = true;
    // (局面, 手数, 黒の番か, 正確な石差（読み切り後のみ）)
    let mut history: Vec<(u64, u64, u8, bool, Option<i32>)> = Vec::new();
    // 読み切りを始めた時点での、黒から見た最終石差
    let mut black_result: Option<i32> = None;
    let mut ply: u8 = 0;

    loop {
        let moves = legal_moves(p, o);
        if moves == 0 {
            if legal_moves(o, p) == 0 {
                break; // 終局
            }
            (p, o) = (o, p); // パス（局面としては記録しない）
            black_to_move = !black_to_move;
            continue;
        }
        let n_empty = (!(p | o)).count_ones();
        let x = if n_empty <= cfg.solve_empties {
            let (best, score) = searcher.solve(p, o);
            let discs = exact_discs(score);
            if black_result.is_none() {
                black_result = Some(if black_to_move { discs } else { -discs });
            }
            history.push((p, o, ply, black_to_move, Some(discs)));
            best
        } else {
            history.push((p, o, ply, black_to_move, None));
            if u32::from(ply) < n_random {
                let list: Vec<u64> = bits(moves).collect();
                list[rng.below(list.len() as u64) as usize]
            } else {
                searcher.search(p, o, f64::INFINITY, cfg.depth).best_move
            }
        };
        (p, o) = play(p, o, x);
        black_to_move = !black_to_move;
        ply += 1;
    }

    // 読み切りに入る前に終局した場合は、実際の最終結果を使う
    let black_result = black_result.unwrap_or_else(|| {
        let discs = exact_discs(final_score(p, o));
        if black_to_move {
            discs
        } else {
            -discs
        }
    });
    history
        .into_iter()
        .map(|(p, o, ply, black, exact)| {
            let score = exact.unwrap_or(if black { black_result } else { -black_result });
            Record {
                p,
                o,
                score: score as i8,
                ply,
                game,
            }
        })
        .collect()
}

/// ゲーム番号 `first`〜`first + count - 1` を `threads` 個のスレッドで並列に打ち、
/// ゲーム番号の順にレコードを並べて返す。`on_progress` は1局終わるたびに呼ばれる。
pub fn play_games(
    first: u32,
    count: u32,
    cfg: &Config,
    eval: &Evaluator,
    threads: usize,
    on_progress: &(dyn Fn(usize) + Sync),
) -> Vec<Record> {
    let next = AtomicUsize::new(0);
    let done = AtomicUsize::new(0);
    let results: Mutex<Vec<Option<Vec<Record>>>> = Mutex::new(vec![None; count as usize]);
    std::thread::scope(|scope| {
        for _ in 0..threads.max(1) {
            scope.spawn(|| {
                let mut searcher = Searcher::new(eval.clone());
                loop {
                    let i = next.fetch_add(1, Ordering::Relaxed);
                    if i >= count as usize {
                        break;
                    }
                    let records = play_game(first + i as u32, cfg, &mut searcher);
                    results.lock().unwrap()[i] = Some(records);
                    on_progress(done.fetch_add(1, Ordering::Relaxed) + 1);
                }
            });
        }
    });
    results
        .into_inner()
        .unwrap()
        .into_iter()
        .flat_map(|r| r.expect("全ゲームが終わっている"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn eval() -> Evaluator {
        let weights: Vec<f64> = (0..64).map(|i| ((i * 7) % 11) as f64 - 5.0).collect();
        let coeffs = [1.0, 0.7, 0.3, 0.2, 1.0, 0.6, 0.4, 0.3, 0.0, 0.5, 1.0, 0.1];
        Evaluator::new(&coeffs, &weights).unwrap()
    }

    fn cfg() -> Config {
        Config {
            depth: 2,
            random_min: 4,
            random_max: 10,
            solve_empties: 8,
            seed: 42,
        }
    }

    #[test]
    fn record_bytes_round_trip() {
        let r = Record {
            p: 0x0123_4567_89AB_CDEF,
            o: 0xF0,
            score: -37,
            ply: 59,
            game: 123_456,
        };
        assert_eq!(Record::from_bytes(&r.to_bytes()), r);
    }

    #[test]
    fn labels_are_exact_after_solving_and_consistent_before() {
        let mut s = Searcher::new(eval());
        for game in 0..10 {
            let records = play_game(game, &cfg(), &mut s);
            assert!(!records.is_empty());
            for r in &records {
                assert_eq!(r.game, game);
                assert_eq!(r.p & r.o, 0);
                assert_ne!(legal_moves(r.p, r.o), 0, "記録した局面は打てる手がある");
                let n_empty = (!(r.p | r.o)).count_ones();
                if n_empty <= cfg().solve_empties {
                    let (_, exact) = s.solve(r.p, r.o);
                    assert_eq!(
                        i32::from(r.score),
                        exact_discs(exact),
                        "game {game} ply {}",
                        r.ply
                    );
                }
            }
            // 手数は 0 から順に増える
            assert!(records.windows(2).all(|w| w[1].ply == w[0].ply + 1));
        }
    }

    #[test]
    fn same_seed_gives_same_games_regardless_of_threads() {
        let e = eval();
        let a = play_games(0, 12, &cfg(), &e, 1, &|_| {});
        let b = play_games(0, 12, &cfg(), &e, 4, &|_| {});
        assert_eq!(a, b);
        let c = play_games(0, 12, &Config { seed: 43, ..cfg() }, &e, 4, &|_| {});
        assert_ne!(a, c);
    }

    #[test]
    fn games_differ_from_each_other() {
        let mut s = Searcher::new(eval());
        let games: Vec<Vec<Record>> = (0..20).map(|g| play_game(g, &cfg(), &mut s)).collect();
        let distinct: std::collections::BTreeSet<(u64, u64)> = games
            .iter()
            .map(|g| (g.last().unwrap().p, g.last().unwrap().o))
            .collect();
        assert!(
            distinct.len() >= 18,
            "ランダムな序盤でほぼすべての対局が別の進行になる"
        );
    }
}
