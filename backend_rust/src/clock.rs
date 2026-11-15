//! Current time in seconds. In the browser (wasm32) Rust's `Instant` is unavailable, so JavaScript's
//! `performance.now()` is imported instead; elsewhere `Instant` is used.

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
        /// provided by JavaScript as `performance.now()` (milliseconds)
        fn now_ms() -> f64;
    }
    // SAFETY: calls an argument-less function that JavaScript always provides
    unsafe { now_ms() / 1000.0 }
}
