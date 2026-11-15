//! 時刻（秒）。ブラウザ（wasm32）では Rust 標準の `Instant` が使えないので、JavaScript の
//! `performance.now()` を読み込む。それ以外の環境では `Instant` を使う。

#[cfg(not(target_arch = "wasm32"))]
pub fn now() -> f64 {
    use std::sync::OnceLock;
    use std::time::Instant;
    static ORIGIN: OnceLock<Instant> = OnceLock::new();
    ORIGIN.get_or_init(Instant::now).elapsed().as_secs_f64()
}

#[cfg(target_arch = "wasm32")]
pub fn now() -> f64 {
    #[link(wasm_import_module = "env")]
    extern "C" {
        /// JavaScript 側で `performance.now()`（ミリ秒）を渡す
        fn now_ms() -> f64;
    }
    // SAFETY: 引数のない関数を呼ぶだけ。JavaScript 側で必ず定義する
    unsafe { now_ms() / 1000.0 }
}
