//! ブラウザ（WebAssembly）から呼ぶ関数。追加の道具（wasm-bindgen など）を使わず、
//! 数値だけをやり取りする素の関数として公開する。
//!
//! - 64 ビットの盤面は JavaScript の BigInt としてそのまま受け渡す
//! - 結果が複数あるときは、`result_ptr()` の位置にある f64 の配列に書き、JavaScript がそこを読む
//! - 文字列（定石名）は `text_ptr()` の位置に UTF-8 で書き、長さを返す
//! - 重みファイル・定石ファイルは JavaScript が `alloc` した領域にコピーしてから `load_*` を呼ぶ
//!
//! 時刻は JavaScript 側の `env.now_ms`（performance.now）を使う（clock.rs）。

use std::cell::RefCell;
use std::sync::Arc;

use crate::board::{bits, flips as flip, legal_moves as legal};
use crate::book::OpeningBook;
use crate::eval::Evaluator;
use crate::levels::{self, params};
use crate::pattern::PatternWeights;
use crate::search::Searcher;
use crate::selfplay::Rng;

/// 結果の配列の大きさ（読み筋は最大 32 手 × 2 + 1）
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

/// `len` バイトの領域を確保して先頭の位置を返す（ファイルを渡すのに使う）
#[no_mangle]
pub extern "C" fn alloc(len: usize) -> *mut u8 {
    let mut v = Vec::<u8>::with_capacity(len);
    let ptr = v.as_mut_ptr();
    std::mem::forget(v);
    ptr
}

/// `alloc` した領域を返す
///
/// # Safety
/// `ptr` と `len` は `alloc(len)` が返したものでなければならない
#[no_mangle]
pub unsafe extern "C" fn dealloc(ptr: *mut u8, len: usize) {
    drop(Vec::from_raw_parts(ptr, 0, len));
}

/// 呼び出し側が渡した領域をバイト列として読む
///
/// # Safety
/// `ptr` から `len` バイトが読める領域でなければならない
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

/// パターン評価の重みファイルを読み込む。成功なら 0
///
/// # Safety
/// `ptr` から `len` バイトが読める領域でなければならない
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

/// 定石ファイル（テキスト）を読み込む。成功なら 0
///
/// # Safety
/// `ptr` から `len` バイトが読める領域でなければならない
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

/// AI の手（1ビット、打てなければ 0）を返す。`web_api.ai_move` と同じ AI を使う。
/// 結果の配列: [探索局面数（なければ -1）, 読んだ深さ（なければ -1）, 読み切ったか, 定石の手か]
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

/// Lv.5（StrongAI と同じ順番: 打てる手が1つ → 定石 → 探索）
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
            .expect("固定の値なので正しい");
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

/// 読み筋（Lv.4 と同じ評価で全手を読む）。手の数を返し、結果の配列に
/// [探索局面数, マス番号1, 評価値1, マス番号2, 評価値2, ...]（良い順）を書く
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

/// 定石名を探す。見つかれば名前を `text_ptr()` に書いてそのバイト数を、なければ -1 を返す
///
/// # Safety
/// `ptr` から `len` バイトが読める領域でなければならない
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

/// パターン評価の重みを読み込み済みか（0 / 1）
#[no_mangle]
pub extern "C" fn has_patterns() -> i32 {
    STATE.with(|s| i32::from(s.borrow().patterns.is_some()))
}
