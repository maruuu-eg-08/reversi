//! Rust implementation of the reversi Lv.5 engine.
//!
//! A port of the computationally heavy parts of `backend/strong_ai.py` (board, evaluation, search).
//! At a fixed depth it returns the same results as the Python version; only the speed differs.
//! Used from Python as `import reversi_engine` (the `python` feature, built with maturin).

pub mod board;
pub mod book;
pub mod clock;
pub mod eval;
pub mod levels;
pub mod openings;
pub mod pattern;
pub mod search;
pub mod selfplay;
pub mod train;
#[cfg(target_arch = "wasm32")]
pub mod wasm;

#[cfg(feature = "python")]
// PyO3 0.22's macro-generated code triggers a false clippy::useless_conversion
#[allow(clippy::useless_conversion)]
mod python {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    use crate::eval::Evaluator;

    /// Squares where the player to move p can play.
    #[pyfunction]
    fn legal_moves(p: u64, o: u64) -> u64 {
        crate::board::legal_moves(p, o)
    }

    /// Discs flipped when p plays on x (a single bit).
    #[pyfunction]
    fn flips(p: u64, o: u64, x: u64) -> u64 {
        crate::board::flips(p, o, x)
    }

    /// Searcher holding the evaluation coefficients and weights. The transposition table is reset for every search.
    #[pyclass]
    struct Searcher {
        inner: crate::search::Searcher,
    }

    #[pymethods]
    impl Searcher {
        /// With pattern_path, the leaves use that file's pattern evaluation (each file is loaded only once).
        #[new]
        #[pyo3(signature = (coeffs, weights, pattern_path=None))]
        fn new(coeffs: Vec<f64>, weights: Vec<f64>, pattern_path: Option<&str>) -> PyResult<Self> {
            let eval = Evaluator::new(&coeffs, &weights).map_err(PyValueError::new_err)?;
            let mut inner = crate::search::Searcher::new(eval);
            if let Some(path) = pattern_path {
                inner = inner.with_patterns(load_patterns(path)?);
            }
            Ok(Self { inner })
        }

        /// Iterative deepening; returns (best move, score, depth, nodes, solved to the end?).
        /// Pass float("inf") as time_limit for no limit. Releases the GIL while searching.
        fn search(
            &mut self,
            py: Python<'_>,
            p: u64,
            o: u64,
            time_limit: f64,
            max_depth: u32,
        ) -> (u64, f64, u32, u64, bool) {
            let r = py.allow_threads(|| self.inner.search(p, o, time_limit, max_depth));
            (r.best_move, r.score, r.depth, r.nodes, r.solved)
        }

        /// Score every legal move at `depth` and return [(move, score)], best first.
        fn score_moves(&mut self, py: Python<'_>, p: u64, o: u64, depth: u32) -> Vec<(u64, f64)> {
            py.allow_threads(|| self.inner.score_moves(p, o, depth))
        }

        /// Nodes searched by the last search (search / score_moves).
        #[getter]
        fn nodes(&self) -> u64 {
            self.inner.nodes()
        }

        /// Evaluation (depth 0) for the player to move p.
        fn evaluate(&self, p: u64, o: u64) -> f64 {
            self.inner.evaluate(p, o, crate::board::legal_moves(p, o))
        }
    }

    /// Load a pattern-weights file; later calls with the same path reuse the loaded weights.
    fn load_patterns(path: &str) -> PyResult<std::sync::Arc<crate::pattern::PatternWeights>> {
        use std::collections::HashMap;
        use std::sync::{Arc, Mutex, OnceLock};
        static CACHE: OnceLock<Mutex<HashMap<String, Arc<crate::pattern::PatternWeights>>>> =
            OnceLock::new();
        let mut cache = CACHE.get_or_init(Default::default).lock().unwrap();
        if let Some(w) = cache.get(path) {
            return Ok(w.clone());
        }
        let w = Arc::new(
            crate::pattern::PatternWeights::load(path)
                .map_err(|e| PyValueError::new_err(e.to_string()))?,
        );
        cache.insert(path.to_string(), w.clone());
        Ok(w)
    }

    /// Configuration index of every pattern instance (for tests; same as Python's patterns.indices).
    #[pyfunction]
    fn pattern_indices(p: u64, o: u64) -> Vec<u32> {
        crate::pattern::indices(p, o)
    }

    /// Pattern evaluation backed by a weights file.
    #[pyclass]
    struct PatternEval {
        weights: crate::pattern::PatternWeights,
    }

    #[pymethods]
    impl PatternEval {
        #[new]
        fn new(path: &str) -> PyResult<Self> {
            let weights = crate::pattern::PatternWeights::load(path)
                .map_err(|e| PyValueError::new_err(e.to_string()))?;
            Ok(Self { weights })
        }

        /// Evaluation in discs for the player to move p.
        fn evaluate(&self, p: u64, o: u64) -> f64 {
            let (mp, mo) = (
                crate::board::legal_moves(p, o),
                crate::board::legal_moves(o, p),
            );
            self.weights.evaluate(p, o, mp, mo)
        }
    }

    /// Generate training data by self-play: all positions of games first..first+count-1 as bytes of
    /// RECORD_SIZE-byte records (in game order). Releases the GIL while searching.
    #[pyfunction]
    #[allow(clippy::too_many_arguments)]
    fn generate_games<'py>(
        py: Python<'py>,
        first: u32,
        count: u32,
        seed: u64,
        depth: u32,
        random_min: u32,
        random_max: u32,
        solve_empties: u32,
        coeffs: Vec<f64>,
        weights: Vec<f64>,
        threads: usize,
    ) -> PyResult<Bound<'py, pyo3::types::PyBytes>> {
        if random_min > random_max {
            return Err(PyValueError::new_err(
                "random_min must not exceed random_max",
            ));
        }
        let eval = Evaluator::new(&coeffs, &weights).map_err(PyValueError::new_err)?;
        let cfg = crate::selfplay::Config {
            depth,
            random_min,
            random_max,
            solve_empties,
            seed,
        };
        let records = py.allow_threads(|| {
            crate::selfplay::play_games(first, count, &cfg, &eval, threads, &|_| {})
        });
        let bytes: Vec<u8> = records.iter().flat_map(|r| r.to_bytes()).collect();
        Ok(pyo3::types::PyBytes::new_bound(py, &bytes))
    }

    /// Train pattern-evaluation weights from self-play data and save them to out_path.
    /// Returns per-stage results as a list of dicts; progress goes to stderr. Releases the GIL while working.
    #[pyfunction]
    #[allow(clippy::too_many_arguments)]
    fn train_patterns(
        py: Python<'_>,
        data_path: &str,
        out_path: &str,
        lam: f64,
        max_iter: usize,
        tol: f64,
        valid_mod: u32,
        threads: usize,
        coeffs: Vec<f64>,
        weights: Vec<f64>,
    ) -> PyResult<Vec<std::collections::HashMap<&'static str, f64>>> {
        if valid_mod == 0 {
            return Err(PyValueError::new_err("valid_mod must be at least 1"));
        }
        let linear = Evaluator::new(&coeffs, &weights).map_err(PyValueError::new_err)?;
        let records = crate::selfplay::read_data_file(std::path::Path::new(data_path))
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        let cfg = crate::train::TrainConfig {
            lambda: lam,
            max_iter,
            tol,
            valid_mod,
            threads,
        };
        let (w, reports) = py.allow_threads(|| {
            let start = std::time::Instant::now();
            crate::train::train(&records, &cfg, &linear, &mut |r| {
                eprintln!(
                    "stage {:2}: train {:>8} / valid {:>7} positions, {:3} iterations, valid RMSE {:.2} (linear {:.2}) ({:.0}s)",
                    r.stage, r.n_train, r.n_valid, r.iterations, r.valid_rmse, r.linear_rmse,
                    start.elapsed().as_secs_f64()
                );
            })
        });
        w.save(out_path)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(reports
            .iter()
            .map(|r| {
                std::collections::HashMap::from([
                    ("stage", r.stage as f64),
                    ("n_train", r.n_train as f64),
                    ("n_valid", r.n_valid as f64),
                    ("iterations", r.iterations as f64),
                    ("train_rmse", r.train_rmse),
                    ("valid_rmse", r.valid_rmse),
                    ("valid_r2", r.valid_r2),
                    ("linear_rmse", r.linear_rmse),
                    ("linear_r2", r.linear_r2),
                    ("clamped", r.clamped as f64),
                ])
            })
            .collect())
    }

    // ---------- parts ported for the web version (for equality tests with Python) ----------

    /// Evaluation parameters embedded in Rust (to test that they match weights.py)
    #[pyfunction]
    fn params() -> std::collections::HashMap<&'static str, Vec<f64>> {
        use crate::levels::params::*;
        std::collections::HashMap::from([
            ("POSITION_WEIGHTS", POSITION_WEIGHTS.to_vec()),
            ("EVAL_COEFFS", EVAL_COEFFS.to_vec()),
            ("WEIGHTED_AI_WEIGHTS", WEIGHTED_AI_WEIGHTS.to_vec()),
            (
                "MINIMAX_WEIGHTS",
                MINIMAX_WEIGHTS.iter().map(|&v| f64::from(v)).collect(),
            ),
            ("STRONG_EVAL_COEFFS", STRONG_EVAL_COEFFS.to_vec()),
        ])
    }

    /// Best moves of Lv.2
    #[pyfunction]
    fn weighted_best_moves(black: u64, white: u64, color: i8) -> Vec<u64> {
        crate::levels::weighted_best_moves(black, white, color)
    }

    /// Best moves of Lv.3
    #[pyfunction]
    fn minimax_best_moves(black: u64, white: u64, color: i8, depth: i32) -> Vec<u64> {
        crate::levels::minimax_best_moves(black, white, color, depth)
    }

    /// Best move and node count of Lv.4
    #[pyfunction]
    fn alphabeta_move(black: u64, white: u64, color: i8, depth: i32) -> (u64, u64) {
        let mut ab = crate::levels::AlphaBeta::new(color, depth);
        let m = ab.get_move(black, white);
        (m, ab.nodes)
    }

    /// Scores of every move for Lv.4 (best first) and the node count
    #[pyfunction]
    fn alphabeta_analyze(black: u64, white: u64, color: i8, depth: i32) -> (Vec<(u64, f64)>, u64) {
        let mut ab = crate::levels::AlphaBeta::new(color, depth);
        let r = ab.analyze(black, white);
        (r, ab.nodes)
    }

    /// Opening name (same as openings.identify)
    #[pyfunction]
    fn opening_name(transcript: &str) -> Option<String> {
        crate::openings::identify(transcript)
    }

    /// Opening book (same lookup as opening_book.OpeningBook)
    #[pyclass]
    struct Book {
        inner: crate::book::OpeningBook,
    }

    #[pymethods]
    impl Book {
        #[new]
        fn new(text: &str) -> PyResult<Self> {
            Ok(Self {
                inner: crate::book::OpeningBook::parse(text).map_err(PyValueError::new_err)?,
            })
        }

        fn __len__(&self) -> usize {
            self.inner.len()
        }

        /// (move, score, depth) or None
        fn probe(&self, p: u64, o: u64) -> Option<(u64, f64, u32)> {
            self.inner
                .probe(p, o)
                .map(|h| (h.best_move, h.score, h.depth))
        }
    }

    #[pymodule]
    fn reversi_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(legal_moves, m)?)?;
        m.add_function(wrap_pyfunction!(flips, m)?)?;
        m.add_class::<Searcher>()?;
        m.add_function(wrap_pyfunction!(pattern_indices, m)?)?;
        m.add_class::<PatternEval>()?;
        m.add_function(wrap_pyfunction!(generate_games, m)?)?;
        m.add("RECORD_SIZE", crate::selfplay::RECORD_SIZE)?;
        m.add_function(wrap_pyfunction!(train_patterns, m)?)?;
        m.add_function(wrap_pyfunction!(params, m)?)?;
        m.add_function(wrap_pyfunction!(weighted_best_moves, m)?)?;
        m.add_function(wrap_pyfunction!(minimax_best_moves, m)?)?;
        m.add_function(wrap_pyfunction!(alphabeta_move, m)?)?;
        m.add_function(wrap_pyfunction!(alphabeta_analyze, m)?)?;
        m.add_function(wrap_pyfunction!(opening_name, m)?)?;
        m.add_class::<Book>()?;
        Ok(())
    }
}
