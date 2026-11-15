//! Functions called from the browser (WebAssembly). Exposed as plain functions that exchange only
//! numbers, without extra tooling such as wasm-bindgen.
//!
//! - 64-bit boards are passed directly as JavaScript BigInts
//! - multiple results are written to the f64 array at `result_ptr()`, which JavaScript reads
//! - strings (opening names) are written as UTF-8 at `text_ptr()` and their length is returned
//! - weight and book files are copied by JavaScript into memory from `alloc`, then `load_*` is called
//!
//! Time comes from JavaScript's `env.now_ms` (performance.now); see clock.rs.

use std::cell::RefCell;
use std::sync::Arc;

use crate::board::{bits, flips as flip, legal_moves as legal};
use crate::book::OpeningBook;
use crate::eval::Evaluator;
use crate::levels::{self, params};
use crate::pattern::PatternWeights;
use crate::search::Searcher;
use crate::selfplay::Rng;

/// Size of the result array (the analysis needs at most 32 moves x 2 + 1)
const RESULT_LEN: usize = 128;

#[derive(Default)]
struct State {
    patterns: Option<Arc<PatternWeights>>,
    book: Option<OpeningBook>,
}

thread_local! {
    static STATE: RefCell<State> = RefCell::new(State::default());
    static RESULT: RefCell<Vec<f64>> = RefCell::new(vec![0.0; RESULT_LEN]);
    static TEXT: RefCell<Vec<u8>> = RefCell::new(Vec::with_capacity(256));
}

fn set_result(values: &[f64]) {
    RESULT.with(|r| {
        let mut r = r.borrow_mut();
        r.iter_mut().for_each(|v| *v = 0.0);
        r[..values.len()].copy_from_slice(values);
    });
}

/// Allocate `len` bytes and return their address (used to pass files in)
#[no_mangle]
pub extern "C" fn alloc(len: usize) -> *mut u8 {
    let mut v = Vec::<u8>::with_capacity(len);
    let ptr = v.as_mut_ptr();
    std::mem::forget(v);
    ptr
}

/// Free memory from `alloc`
///
/// # Safety
/// `ptr` and `len` must come from `alloc(len)`
#[no_mangle]
pub unsafe extern "C" fn dealloc(ptr: *mut u8, len: usize) {
    drop(Vec::from_raw_parts(ptr, 0, len));
}

/// View memory provided by the caller as bytes
///
/// # Safety
/// `ptr` must point to `len` readable bytes
unsafe fn bytes<'a>(ptr: *const u8, len: usize) -> &'a [u8] {
    std::slice::from_raw_parts(ptr, len)
}

#[no_mangle]
pub extern "C" fn result_ptr() -> *const f64 {
    RESULT.with(|r| r.borrow().as_ptr())
}

#[no_mangle]
pub extern "C" fn text_ptr() -> *const u8 {
    TEXT.with(|t| t.borrow().as_ptr())
}

/// Load a pattern-weights file. Returns 0 on success
///
/// # Safety
/// `ptr` must point to `len` readable bytes
#[no_mangle]
pub unsafe extern "C" fn load_patterns(ptr: *const u8, len: usize) -> i32 {
    match PatternWeights::from_bytes(bytes(ptr, len)) {
        Ok(w) => {
            STATE.with(|s| s.borrow_mut().patterns = Some(Arc::new(w)));
            0
        }
        Err(_) => 1,
    }
}

/// Load an opening-book file (text). Returns 0 on success
///
/// # Safety
/// `ptr` must point to `len` readable bytes
#[no_mangle]
pub unsafe extern "C" fn load_book(ptr: *const u8, len: usize) -> i32 {
    let Ok(text) = std::str::from_utf8(bytes(ptr, len)) else {
        return 1;
    };
    match OpeningBook::parse(text) {
        Ok(b) => {
            STATE.with(|s| s.borrow_mut().book = Some(b));
            0
        }
        Err(_) => 2,
    }
}

#[no_mangle]
pub extern "C" fn legal_moves(p: u64, o: u64) -> u64 {
    legal(p, o)
}

#[no_mangle]
pub extern "C" fn flips(p: u64, o: u64, x: u64) -> u64 {
    flip(p, o, x)
}

fn random_choice(list: &[u64], seed: u64) -> u64 {
    list[Rng::new(seed).below(list.len() as u64) as usize]
}

/// The AI's move (single bit, 0 if it cannot move), using the same AIs as `web_api.ai_move`.
/// Result array: [nodes (-1 if none), depth (-1 if none), solved?, book move?]
#[no_mangle]
pub extern "C" fn ai_move(
    black: u64,
    white: u64,
    color: i32,
    level: i32,
    depth: i32,
    time_limit: f64,
    seed: u64,
) -> u64 {
    let color = if color == 1 { 1i8 } else { -1i8 };
    let (p, o) = if color == 1 {
        (black, white)
    } else {
        (white, black)
    };
    let moves: Vec<u64> = bits(legal(p, o)).collect();
    if moves.is_empty() {
        set_result(&[-1.0, -1.0, 0.0, 0.0]);
        return 0;
    }
    match level {
        2 => {
            set_result(&[-1.0, -1.0, 0.0, 0.0]);
            random_choice(&levels::weighted_best_moves(black, white, color), seed)
        }
        3 => {
            set_result(&[-1.0, -1.0, 0.0, 0.0]);
            random_choice(&levels::minimax_best_moves(black, white, color, 4), seed)
        }
        4 => {
            let mut ab = levels::AlphaBeta::new(color, depth);
            let m = ab.get_move(black, white);
            set_result(&[ab.nodes as f64, f64::from(depth), 0.0, 0.0]);
            m
        }
        5 => strong_move(p, o, time_limit),
        _ => {
            set_result(&[-1.0, -1.0, 0.0, 0.0]);
            random_choice(&moves, seed)
        }
    }
}

/// Lv.5 (same order as StrongAI: single legal move -> book -> search)
fn strong_move(p: u64, o: u64, time_limit: f64) -> u64 {
    let moves = legal(p, o);
    if moves & (moves - 1) == 0 {
        set_result(&[0.0, 0.0, 0.0, 0.0]);
        return moves;
    }
    STATE.with(|s| {
        let s = s.borrow();
        if let Some(hit) = s.book.as_ref().and_then(|b| b.probe(p, o)) {
            set_result(&[0.0, f64::from(hit.depth), 0.0, 1.0]);
            return hit.best_move;
        }
        let eval = Evaluator::new(&params::STRONG_EVAL_COEFFS, &params::POSITION_WEIGHTS)
            .expect("fixed values are valid");
        let mut searcher = Searcher::new(eval);
        if let Some(w) = &s.patterns {
            searcher = searcher.with_patterns(w.clone());
        }
        let r = searcher.search(p, o, time_limit, 60);
        set_result(&[
            r.nodes as f64,
            f64::from(r.depth),
            f64::from(u8::from(r.solved)),
            0.0,
        ]);
        r.best_move
    })
}

/// Analysis (every move scored like Lv.4). Returns the number of moves and writes
/// [nodes, square1, score1, square2, score2, ...] (best first) to the result array
#[no_mangle]
pub extern "C" fn analyze(black: u64, white: u64, color: i32, depth: i32) -> i32 {
    let color = if color == 1 { 1i8 } else { -1i8 };
    let mut ab = levels::AlphaBeta::new(color, depth);
    let results = ab.analyze(black, white);
    let mut out = vec![ab.nodes as f64];
    for (m, s) in results.iter().take((RESULT_LEN - 1) / 2) {
        out.push(f64::from(m.trailing_zeros()));
        out.push(*s);
    }
    set_result(&out);
    results.len() as i32
}

/// Look up the opening name. Writes it to `text_ptr()` and returns its byte length, or -1 if none
///
/// # Safety
/// `ptr` must point to `len` readable bytes
#[no_mangle]
pub unsafe extern "C" fn opening(ptr: *const u8, len: usize) -> i32 {
    let Ok(transcript) = std::str::from_utf8(bytes(ptr, len)) else {
        return -1;
    };
    match crate::openings::identify(transcript) {
        Some(name) => TEXT.with(|t| {
            let mut t = t.borrow_mut();
            t.clear();
            t.extend_from_slice(name.as_bytes());
            name.len() as i32
        }),
        None => -1,
    }
}

/// Whether pattern weights are loaded (0 / 1)
#[no_mangle]
pub extern "C" fn has_patterns() -> i32 {
    STATE.with(|s| i32::from(s.borrow().patterns.is_some()))
}
