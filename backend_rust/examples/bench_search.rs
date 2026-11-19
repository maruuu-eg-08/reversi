//! Fixed-depth search benchmark (the speed figures in the README):
//!
//! ```text
//! cargo run --release --example bench_search -- examples/midgame_positions.txt 10 ../backend/pattern_weights.bin
//! ```
//!
//! Each line of the positions file is `p o` (decimal bitboards, player to move first);
//! `midgame_positions.txt` holds 24 positions from random play (8 each with 40, 30 and 20 empty squares).
//! Prints the move, score, nodes and time of every search and the totals.

use std::sync::Arc;
use std::time::Instant;

use reversi_engine::eval::Evaluator;
use reversi_engine::levels::params;
use reversi_engine::pattern::PatternWeights;
use reversi_engine::search::Searcher;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: bench_search <positions file> <depth> [pattern weights]");
        std::process::exit(2);
    }
    let text = std::fs::read_to_string(&args[1]).expect("cannot read the positions file");
    let depth: u32 = args[2].parse().expect("depth must be a number");
    let weights = args
        .get(3)
        .map(|path| Arc::new(PatternWeights::load(path).expect("pattern weights")));
    let (mut nodes, mut secs) = (0u64, 0f64);
    for line in text.lines().filter(|l| !l.trim().is_empty()) {
        let bad = || panic!("expected `p o` (two decimal numbers): {line}");
        let mut it = line
            .split_whitespace()
            .map(|v| v.parse::<u64>().unwrap_or_else(|_| bad()));
        let (p, o) = (it.next().unwrap_or_else(bad), it.next().unwrap_or_else(bad));
        let eval = Evaluator::new(&params::STRONG_EVAL_COEFFS, &params::POSITION_WEIGHTS).unwrap();
        let mut s = Searcher::new(eval);
        if let Some(w) = &weights {
            s = s.with_patterns(w.clone());
        }
        let t = Instant::now();
        let r = s.search(p, o, f64::INFINITY, depth);
        let dt = t.elapsed().as_secs_f64();
        println!(
            "{:016x} {:016x} move {:2} score {:10.4} nodes {:9} {:.3}s",
            p,
            o,
            r.best_move.trailing_zeros(),
            r.score,
            r.nodes,
            dt
        );
        nodes += r.nodes;
        secs += dt;
    }
    println!(
        "total nodes {nodes} time {secs:.3}s {:.2} Mnodes/s",
        nodes as f64 / secs / 1e6
    );
}
