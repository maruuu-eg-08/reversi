//! リバーシ Lv.5 エンジンの Rust 実装。
//!
//! `backend/strong_ai.py` の盤面計算・評価・探索のうち、計算の重い部分だけを移植したもの。
//! 固定の深さで読めば Python 版と同じ結果になり、速さだけが違う。
//! Python からは `import reversi_engine` で使う（`python` フィーチャー、maturin でビルド）。

pub mod board;
pub mod eval;
pub mod pattern;
pub mod search;

#[cfg(feature = "python")]
mod python {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    use crate::eval::Evaluator;

    /// 手番側 p が打てるマス。
    #[pyfunction]
    fn legal_moves(p: u64, o: u64) -> u64 {
        crate::board::legal_moves(p, o)
    }

    /// p が x（1ビット）に打ったときに裏返る石。
    #[pyfunction]
    fn flips(p: u64, o: u64, x: u64) -> u64 {
        crate::board::flips(p, o, x)
    }

    /// 評価関数の係数と重み表を持つ探索器。置換表は探索のたびに作り直す。
    #[pyclass]
    struct Searcher {
        inner: crate::search::Searcher,
    }

    #[pymethods]
    impl Searcher {
        #[new]
        fn new(coeffs: Vec<f64>, weights: Vec<f64>) -> PyResult<Self> {
            let eval = Evaluator::new(&coeffs, &weights).map_err(PyValueError::new_err)?;
            Ok(Self {
                inner: crate::search::Searcher::new(eval),
            })
        }

        /// 反復深化で読み、(最善手, 評価値, 読んだ深さ, 探索局面数, 終局まで読み切ったか) を返す。
        /// time_limit に float("inf") を渡すと時間制限なし。探索中は GIL を手放す。
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

        /// 全合法手を depth 手先まで読んだ評価値を、良い順に [(手, 評価値)] で返す。
        fn score_moves(&mut self, py: Python<'_>, p: u64, o: u64, depth: u32) -> Vec<(u64, f64)> {
            py.allow_threads(|| self.inner.score_moves(p, o, depth))
        }

        /// 直前の探索（search / score_moves）で探索した局面数。
        #[getter]
        fn nodes(&self) -> u64 {
            self.inner.nodes()
        }

        /// 手番側 p から見た評価値（深さ0）。
        fn evaluate(&self, p: u64, o: u64) -> f64 {
            self.inner
                .evaluator()
                .evaluate(p, o, crate::board::legal_moves(p, o))
        }
    }

    /// 各パターンのインスタンスの並びの番号（テスト用。Python 版の patterns.indices と同じ）。
    #[pyfunction]
    fn pattern_indices(p: u64, o: u64) -> Vec<u32> {
        crate::pattern::indices(p, o)
    }

    /// パターン評価（重みファイルを読み込んで使う）。
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

        /// 手番側 p から見た評価値（石数の単位）。
        fn evaluate(&self, p: u64, o: u64) -> f64 {
            let (mp, mo) = (
                crate::board::legal_moves(p, o),
                crate::board::legal_moves(o, p),
            );
            self.weights.evaluate(p, o, mp, mo)
        }
    }

    #[pymodule]
    fn reversi_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(legal_moves, m)?)?;
        m.add_function(wrap_pyfunction!(flips, m)?)?;
        m.add_class::<Searcher>()?;
        m.add_function(wrap_pyfunction!(pattern_indices, m)?)?;
        m.add_class::<PatternEval>()?;
        Ok(())
    }
}
