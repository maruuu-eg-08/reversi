//! Self-play data generation for training the pattern evaluation.
//!
//! How a game is played:
//! 1. `random_min`-`random_max` random opening moves (for variety)
//! 2. then both sides search to depth `depth`
//! 3. from `solve_empties` empty squares on, the game is solved exactly and played perfectly
//!
//! Each position is labeled with the final disc difference for its side to move. From the first solved
//! position on the labels are exact; earlier positions get the exact value of that first solved position
//! (the result if both sides play perfectly from there). Empty squares go to the winner (as in `final_score`).
//!
//! Each game uses only randomness derived from its game number, so the data does not depend on the thread count.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

use crate::board::{bits, legal_moves, play};
use crate::eval::{final_score, Evaluator, WIN_SCORE};
use crate::pattern::PatternWeights;
use crate::search::Searcher;

/// Size of one record in bytes
pub const RECORD_SIZE: usize = 22;

#[derive(Clone, Copy, Debug)]
pub struct Config {
    pub depth: u32,
    pub random_min: u32,
    pub random_max: u32,
    pub solve_empties: u32,
    pub seed: u64,
}

/// One training position
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Record {
    /// discs of the side to move
    pub p: u64,
    /// discs of the opponent
    pub o: u64,
    /// final disc difference for the side to move (empty squares go to the winner)
    pub score: i8,
    /// ply from the start position
    pub ply: u8,
    /// game number (to split training and validation data by game)
    pub game: u32,
}

impl Record {
    /// Encode as `RECORD_SIZE` little-endian bytes.
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

/// Read a file written by gen_data.py (header + records).
pub fn read_data_file(path: &std::path::Path) -> std::io::Result<Vec<Record>> {
    let invalid = |msg: &str| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!("{}: {msg}", path.display()),
        )
    };
    let data = std::fs::read(path)?;
    const MAGIC: &[u8] = b"RVDAT\x01";
    if !data.starts_with(MAGIC) || data.len() < MAGIC.len() + 4 {
        return Err(invalid("not a self-play data file"));
    }
    let n = u32::from_le_bytes(data[MAGIC.len()..MAGIC.len() + 4].try_into().unwrap()) as usize;
    let body = data
        .get(MAGIC.len() + 4 + n..)
        .ok_or_else(|| invalid("truncated header"))?;
    if body.len() % RECORD_SIZE != 0 {
        return Err(invalid("truncated record"));
    }
    Ok(body
        .chunks_exact(RECORD_SIZE)
        .map(Record::from_bytes)
        .collect())
}

/// SplitMix64: a small, fast, reproducible random number generator
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

    /// An integer in 0..n (n > 0)
    pub fn below(&mut self, n: u64) -> u64 {
        // n is small, so the modulo bias is negligible
        self.next_u64() % n
    }
}

/// Convert an exact-solve score (`WIN_SCORE` +/- discs, or 0 for a draw) into a disc difference.
fn exact_discs(score: f64) -> i32 {
    if score >= WIN_SCORE {
        (score - WIN_SCORE) as i32
    } else if score <= -WIN_SCORE {
        (score + WIN_SCORE) as i32
    } else {
        assert_eq!(
            score, 0.0,
            "an exact solve did not return a final score: {score}"
        );
        0
    }
}

/// Play one game and return its records in move order.
pub fn play_game(game: u32, cfg: &Config, searcher: &mut Searcher) -> Vec<Record> {
    let mut rng = Rng::new(cfg.seed ^ u64::from(game).wrapping_mul(0xD1B5_4A32_D192_ED03));
    let n_random =
        cfg.random_min + rng.below(u64::from(cfg.random_max - cfg.random_min + 1)) as u32;

    let (mut p, mut o) = (0x0000_0008_1000_0000u64, 0x0000_0010_0800_0000u64);
    let mut black_to_move = true;
    // (position, ply, black to move?, exact disc difference (after solving only))
    let mut history: Vec<(u64, u64, u8, bool, Option<i32>)> = Vec::new();
    // final disc difference for black at the first solved position
    let mut black_result: Option<i32> = None;
    let mut ply: u8 = 0;

    loop {
        let moves = legal_moves(p, o);
        if moves == 0 {
            if legal_moves(o, p) == 0 {
                break; // game over
            }
            (p, o) = (o, p); // pass (not recorded as a position)
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

    // if the game ended before solving started, use the actual final result
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

/// Play games `first`..`first + count - 1` on `threads` threads and return the records
/// in game order. With `patterns`, the searches use that pattern evaluation at the leaves (as Lv.5 does);
/// otherwise the linear evaluation `eval`. `on_progress` is called after each finished game.
#[allow(clippy::too_many_arguments)]
pub fn play_games(
    first: u32,
    count: u32,
    cfg: &Config,
    eval: &Evaluator,
    patterns: Option<&std::sync::Arc<PatternWeights>>,
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
                if let Some(w) = patterns {
                    searcher = searcher.with_patterns(w.clone());
                }
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
        .flat_map(|r| r.expect("all games are finished"))
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
                assert_ne!(
                    legal_moves(r.p, r.o),
                    0,
                    "recorded positions have a legal move"
                );
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
            // plies increase from 0 one by one
            assert!(records.windows(2).all(|w| w[1].ply == w[0].ply + 1));
        }
    }

    #[test]
    fn same_seed_gives_same_games_regardless_of_threads() {
        let e = eval();
        let a = play_games(0, 12, &cfg(), &e, None, 1, &|_| {});
        let b = play_games(0, 12, &cfg(), &e, None, 4, &|_| {});
        assert_eq!(a, b);
        let c = play_games(0, 12, &Config { seed: 43, ..cfg() }, &e, None, 4, &|_| {});
        assert_ne!(a, c);
    }

    #[test]
    fn pattern_evaluation_games_are_deterministic_and_differ_from_linear() {
        let path = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../backend/pattern_weights.bin"
        );
        let w = std::sync::Arc::new(PatternWeights::load(path).unwrap());
        let e = eval();
        let a = play_games(0, 12, &cfg(), &e, Some(&w), 1, &|_| {});
        let b = play_games(0, 12, &cfg(), &e, Some(&w), 4, &|_| {});
        assert_eq!(a, b);
        let linear = play_games(0, 12, &cfg(), &e, None, 4, &|_| {});
        assert_ne!(a, linear, "the evaluation changes the moves played");
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
            "random openings make almost every game different"
        );
    }
}
