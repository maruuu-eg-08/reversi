//! パターン評価の重みの学習。
//!
//! 段階（stage）ごとに、局面の特徴（各パターンの並び・定数項・着手可能数の差）から最終石差を予測する
//! 線形モデルを、L2 正則化つき最小二乗法で解く:
//!
//! ```text
//!   最小化  Σ (y_i - x_i · w)^2 + λ |w|^2   ⇔   (XᵀX + λI) w = Xᵀy
//! ```
//!
//! X は1行あたり 86 個しか 0 でない値がない疎な行列なので、XᵀX を作らずに
//! 「X v」と「Xᵀ u」だけを使う前処理つき共役勾配法（Jacobi 前処理）で解く。
//! 学習率などの調整がいらず、解が一つに決まる。
//!
//! 足し算の順番がスレッド数に左右されないように並列化しているので、何スレッドで
//! 計算しても同じ重みになる（X v は行ごと、Xᵀ u は列ごとに独立に計算し、内積は固定の大きさの塊ごとに足す）。

use crate::board::legal_moves;
use crate::eval::Evaluator;
use crate::pattern::{layout, stage_of, PatternWeights, Stage, N_STAGES, SCALE};
use crate::selfplay::Record;

/// 内積を足し合わせる塊の大きさ（スレッド数によらず固定）
const DOT_CHUNK: usize = 1 << 14;

#[derive(Clone, Copy, Debug)]
pub struct TrainConfig {
    /// L2 正則化の強さ
    pub lambda: f64,
    /// 共役勾配法の最大反復回数
    pub max_iter: usize,
    /// 残差がこの割合（初期値に対する比）を下回ったら止める
    pub tol: f64,
    /// ゲーム番号をこの数で割った余りが 0 の対局を検証用にする
    pub valid_mod: u32,
    pub threads: usize,
}

/// 1段階分の学習結果
#[derive(Clone, Debug)]
pub struct StageReport {
    pub stage: usize,
    pub n_train: usize,
    pub n_valid: usize,
    pub iterations: usize,
    /// 学習データでの誤差（整数に丸めた重みで計算）
    pub train_rmse: f64,
    /// 検証データでの誤差と決定係数（整数に丸めた重みで計算）
    pub valid_rmse: f64,
    pub valid_r2: f64,
    /// 比較用: 今の線形評価関数の検証データでの誤差と決定係数
    pub linear_rmse: f64,
    pub linear_r2: f64,
    /// i16 の範囲に収まらず切り詰めた重みの数
    pub clamped: usize,
}

/// 学習用に特徴を取り出した1段階分のデータ
struct Dataset {
    /// 各行のパターンの特徴番号（表の中の位置）。行 i は ids[i*k .. (i+1)*k]
    ids: Vec<u32>,
    k: usize,
    mobility: Vec<f64>,
    y: Vec<f64>,
    /// 列 → その特徴を含む行（同じ行に2回現れれば2回入る）。CSC 形式
    col_start: Vec<usize>,
    col_rows: Vec<u32>,
}

impl Dataset {
    fn new(records: &[&Record]) -> Self {
        let lay = layout();
        let k = lay.instances.len();
        let n = records.len();
        let mut ids = Vec::with_capacity(n * k);
        let mut mobility = Vec::with_capacity(n);
        let mut y = Vec::with_capacity(n);
        for r in records {
            for inst in &lay.instances {
                let idx = inst.squares.iter().rev().fold(0u32, |idx, &i| {
                    idx * 3 + ((r.p >> i) & 1) as u32 + 2 * ((r.o >> i) & 1) as u32
                });
                ids.push((lay.family_offsets[inst.family] as u32) + idx);
            }
            mobility.push(f64::from(
                legal_moves(r.p, r.o).count_ones() as i32
                    - legal_moves(r.o, r.p).count_ones() as i32,
            ));
            y.push(f64::from(r.score));
        }
        // 列ごとの行の一覧（行番号の小さい順）
        let mut col_start = vec![0usize; lay.table_size + 1];
        for &id in &ids {
            col_start[id as usize + 1] += 1;
        }
        for c in 0..lay.table_size {
            col_start[c + 1] += col_start[c];
        }
        let mut fill = col_start.clone();
        let mut col_rows = vec![0u32; ids.len()];
        for (pos, &id) in ids.iter().enumerate() {
            col_rows[fill[id as usize]] = (pos / k) as u32;
            fill[id as usize] += 1;
        }
        Self {
            ids,
            k,
            mobility,
            y,
            col_start,
            col_rows,
        }
    }

    fn rows(&self) -> usize {
        self.y.len()
    }
}

/// 未知数の並び: [パターンの表 (table_size) | 定数項 | 着手可能数の係数]
fn dim() -> usize {
    layout().table_size + 2
}

/// `out[i] = f(i)` を並列に計算する（各要素は独立なので結果はスレッド数によらない）。
fn par_fill(out: &mut [f64], threads: usize, f: &(dyn Fn(usize) -> f64 + Sync)) {
    let chunk = out.len().div_ceil(threads.max(1)).max(1);
    std::thread::scope(|s| {
        for (c, part) in out.chunks_mut(chunk).enumerate() {
            s.spawn(move || {
                for (j, v) in part.iter_mut().enumerate() {
                    *v = f(c * chunk + j);
                }
            });
        }
    });
}

/// 内積。固定の大きさの塊ごとに足し、塊の合計を順番に足すので結果はスレッド数によらない。
fn dot(a: &[f64], b: &[f64], threads: usize) -> f64 {
    let n_chunks = a.len().div_ceil(DOT_CHUNK);
    let mut partial = vec![0.0; n_chunks];
    par_fill(&mut partial, threads, &|c| {
        let range = c * DOT_CHUNK..((c + 1) * DOT_CHUNK).min(a.len());
        a[range.clone()]
            .iter()
            .zip(&b[range])
            .map(|(x, y)| x * y)
            .sum()
    });
    partial.iter().sum()
}

/// 総和（`dot` と同じく、結果はスレッド数によらない）。
fn sum(a: &[f64], threads: usize) -> f64 {
    let n_chunks = a.len().div_ceil(DOT_CHUNK);
    let mut partial = vec![0.0; n_chunks];
    par_fill(&mut partial, threads, &|c| {
        a[c * DOT_CHUNK..((c + 1) * DOT_CHUNK).min(a.len())]
            .iter()
            .sum()
    });
    partial.iter().sum()
}

/// X v（各行の予測値）
fn mul_x(d: &Dataset, v: &[f64], out: &mut [f64], threads: usize) {
    let t = layout().table_size;
    let (bias, mob) = (v[t], v[t + 1]);
    par_fill(out, threads, &|i| {
        let row = &d.ids[i * d.k..(i + 1) * d.k];
        row.iter()
            .fold(bias + mob * d.mobility[i], |acc, &id| acc + v[id as usize])
    });
}

/// (XᵀX + λI) v
fn mul_a(d: &Dataset, v: &[f64], lambda: f64, xv: &mut [f64], out: &mut [f64], threads: usize) {
    let t = layout().table_size;
    mul_x(d, v, xv, threads);
    let xv: &[f64] = xv;
    par_fill(&mut out[..t], threads, &|c| {
        let rows = &d.col_rows[d.col_start[c]..d.col_start[c + 1]];
        rows.iter().map(|&r| xv[r as usize]).sum::<f64>() + lambda * v[c]
    });
    out[t] = sum(xv, threads) + lambda * v[t];
    out[t + 1] = dot(xv, &d.mobility, threads) + lambda * v[t + 1];
}

/// Xᵀ y と、前処理に使う (XᵀX + λI) の対角成分
fn rhs_and_diag(d: &Dataset, lambda: f64, threads: usize) -> (Vec<f64>, Vec<f64>) {
    let t = layout().table_size;
    let mut b = vec![0.0; dim()];
    par_fill(&mut b[..t], threads, &|c| {
        d.col_rows[d.col_start[c]..d.col_start[c + 1]]
            .iter()
            .map(|&r| d.y[r as usize])
            .sum()
    });
    b[t] = sum(&d.y, threads);
    b[t + 1] = dot(&d.y, &d.mobility, threads);

    // 列 c の対角成分 = Σ_行 (その行に c が現れる回数)^2 + λ
    let mut diag = vec![lambda; dim()];
    par_fill(&mut diag[..t], threads, &|c| {
        let rows = &d.col_rows[d.col_start[c]..d.col_start[c + 1]];
        let mut sum = 0.0;
        let mut i = 0;
        while i < rows.len() {
            let mut j = i;
            while j < rows.len() && rows[j] == rows[i] {
                j += 1;
            }
            sum += ((j - i) * (j - i)) as f64;
            i = j;
        }
        sum + lambda
    });
    diag[t] += d.rows() as f64;
    diag[t + 1] += dot(&d.mobility, &d.mobility, threads);
    (b, diag)
}

/// 前処理つき共役勾配法で (XᵀX + λI) w = Xᵀy を解く。(解, 反復回数) を返す。
fn solve(d: &Dataset, cfg: &TrainConfig) -> (Vec<f64>, usize) {
    let n = dim();
    let th = cfg.threads;
    let (b, diag) = rhs_and_diag(d, cfg.lambda, th);
    let mut w = vec![0.0; n];
    let mut r = b.clone(); // w = 0 なので残差 = b
    let mut z: Vec<f64> = r.iter().zip(&diag).map(|(r, d)| r / d).collect();
    let mut p = z.clone();
    let mut rz = dot(&r, &z, th);
    let r0 = dot(&r, &r, th).sqrt();
    let mut xv = vec![0.0; d.rows()];
    let mut ap = vec![0.0; n];
    let mut iterations = 0;
    while iterations < cfg.max_iter && r0 > 0.0 {
        mul_a(d, &p, cfg.lambda, &mut xv, &mut ap, th);
        let alpha = rz / dot(&p, &ap, th);
        for i in 0..n {
            w[i] += alpha * p[i];
            r[i] -= alpha * ap[i];
        }
        iterations += 1;
        if dot(&r, &r, th).sqrt() <= cfg.tol * r0 {
            break;
        }
        for i in 0..n {
            z[i] = r[i] / diag[i];
        }
        let rz_new = dot(&r, &z, th);
        let beta = rz_new / rz;
        rz = rz_new;
        for i in 0..n {
            p[i] = z[i] + beta * p[i];
        }
    }
    (w, iterations)
}

/// 実数の重みを 1/SCALE 単位の整数に丸める。(段階の重み, 切り詰めた数)
fn quantize(w: &[f64]) -> (Stage, usize) {
    let t = layout().table_size;
    let mut clamped = 0;
    let table = w[..t]
        .iter()
        .map(|&v| {
            let q = (v * f64::from(SCALE)).round();
            if q > f64::from(i16::MAX) || q < f64::from(i16::MIN) {
                clamped += 1;
            }
            q.clamp(f64::from(i16::MIN), f64::from(i16::MAX)) as i16
        })
        .collect();
    let to_i32 = |v: f64| (v * f64::from(SCALE)).round() as i32;
    (
        Stage {
            bias: to_i32(w[t]),
            mobility: to_i32(w[t + 1]),
            table,
        },
        clamped,
    )
}

/// 予測の誤差（RMSE）と決定係数（R²）
fn metrics(pred: impl Iterator<Item = f64>, y: &[f64]) -> (f64, f64) {
    if y.is_empty() {
        return (f64::NAN, f64::NAN);
    }
    let n = y.len() as f64;
    let mean = y.iter().sum::<f64>() / n;
    let (mut sse, mut sst) = (0.0, 0.0);
    for (p, &t) in pred.zip(y) {
        sse += (t - p) * (t - p);
        sst += (t - mean) * (t - mean);
    }
    (
        (sse / n).sqrt(),
        if sst > 0.0 { 1.0 - sse / sst } else { f64::NAN },
    )
}

/// 全段階を学習する。`linear` は比較用の今の評価関数。`on_stage` は段階ごとの終了時に呼ばれる。
pub fn train(
    records: &[Record],
    cfg: &TrainConfig,
    linear: &Evaluator,
    on_stage: &mut dyn FnMut(&StageReport),
) -> (PatternWeights, Vec<StageReport>) {
    let mut weights = PatternWeights::zeros();
    let mut reports = Vec::new();
    for stage in 0..N_STAGES {
        let in_stage = |r: &&Record| stage_of((!(r.p | r.o)).count_ones()) == stage;
        let train_rows: Vec<&Record> = records
            .iter()
            .filter(in_stage)
            .filter(|r| r.game % cfg.valid_mod != 0)
            .collect();
        let valid_rows: Vec<&Record> = records
            .iter()
            .filter(in_stage)
            .filter(|r| r.game % cfg.valid_mod == 0)
            .collect();

        let data = Dataset::new(&train_rows);
        let (w, iterations) = if data.rows() > 0 {
            solve(&data, cfg)
        } else {
            (vec![0.0; dim()], 0)
        };
        let (stage_weights, clamped) = quantize(&w);
        weights.stages[stage] = stage_weights;

        let predict =
            |r: &Record| weights.evaluate(r.p, r.o, legal_moves(r.p, r.o), legal_moves(r.o, r.p));
        let (train_rmse, _) = metrics(train_rows.iter().map(|r| predict(r)), &data.y);
        let valid_y: Vec<f64> = valid_rows.iter().map(|r| f64::from(r.score)).collect();
        let (valid_rmse, valid_r2) = metrics(valid_rows.iter().map(|r| predict(r)), &valid_y);
        let (linear_rmse, linear_r2) = metrics(
            valid_rows
                .iter()
                .map(|r| linear.evaluate(r.p, r.o, legal_moves(r.p, r.o))),
            &valid_y,
        );

        let report = StageReport {
            stage,
            n_train: train_rows.len(),
            n_valid: valid_rows.len(),
            iterations,
            train_rmse,
            valid_rmse,
            valid_r2,
            linear_rmse,
            linear_r2,
            clamped,
        };
        on_stage(&report);
        reports.push(report);
    }
    (weights, reports)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::selfplay::{play_games, Config};

    fn linear() -> Evaluator {
        let weights: Vec<f64> = (0..64).map(|i| ((i * 7) % 11) as f64 - 5.0).collect();
        Evaluator::new(
            &[1.0, 0.7, 0.3, 0.2, 1.0, 0.6, 0.4, 0.3, 0.0, 0.5, 1.0, 0.1],
            &weights,
        )
        .unwrap()
    }

    fn positions() -> Vec<Record> {
        let cfg = Config {
            depth: 1,
            random_min: 10,
            random_max: 40,
            solve_empties: 0,
            seed: 5,
        };
        play_games(0, 400, &cfg, &linear(), 4, &|_| {})
    }

    /// ラベルを「既知の重みでの評価値」にしたデータなら、学習でその評価値をほぼ再現できる
    #[test]
    fn recovers_a_known_linear_target() {
        let mut target = PatternWeights::zeros();
        let mut rng = crate::selfplay::Rng::new(1);
        for st in &mut target.stages {
            st.bias = 64 * 2;
            st.mobility = 64;
            for v in st.table.iter_mut() {
                *v = (rng.below(129) as i16 - 64) / 8; // 小さな値
            }
        }
        let records: Vec<Record> = positions()
            .into_iter()
            .map(|mut r| {
                let v = target.evaluate(r.p, r.o, legal_moves(r.p, r.o), legal_moves(r.o, r.p));
                r.score = v.round().clamp(-64.0, 64.0) as i8;
                r
            })
            .collect();
        let cfg = TrainConfig {
            lambda: 1e-3,
            max_iter: 500,
            tol: 1e-10,
            valid_mod: 1_000_000,
            threads: 4,
        };
        let (w, reports) = train(&records, &cfg, &linear(), &mut |_| {});
        for rep in reports.iter().filter(|r| r.n_train > 0) {
            // ラベル自体が整数に丸めてあるので、誤差は丸めの分（0.5 以下）程度に収まる
            assert!(
                rep.train_rmse < 0.6,
                "stage {} rmse {}",
                rep.stage,
                rep.train_rmse
            );
        }
        assert_eq!(w.stages.len(), N_STAGES);
    }

    #[test]
    fn result_does_not_depend_on_thread_count() {
        let records = positions();
        let cfg = |threads| TrainConfig {
            lambda: 1.0,
            max_iter: 50,
            tol: 1e-12,
            valid_mod: 5,
            threads,
        };
        let (a, ra) = train(&records, &cfg(1), &linear(), &mut |_| {});
        let (b, rb) = train(&records, &cfg(7), &linear(), &mut |_| {});
        assert_eq!(a, b);
        for (x, y) in ra.iter().zip(&rb) {
            assert_eq!(x.valid_rmse.to_bits(), y.valid_rmse.to_bits());
        }
    }

    #[test]
    fn validation_split_is_by_game() {
        let records = positions();
        let cfg = TrainConfig {
            lambda: 1.0,
            max_iter: 5,
            tol: 1e-12,
            valid_mod: 4,
            threads: 2,
        };
        let (_, reports) = train(&records, &cfg, &linear(), &mut |_| {});
        let valid: usize = reports.iter().map(|r| r.n_valid).sum();
        let expected = records.iter().filter(|r| r.game % 4 == 0).count();
        assert_eq!(valid, expected);
        assert_eq!(
            reports.iter().map(|r| r.n_train + r.n_valid).sum::<usize>(),
            records.len()
        );
    }

    #[test]
    fn quantize_rounds_and_clamps() {
        let mut w = vec![0.0; dim()];
        w[0] = 1.0; // → 64
        w[1] = -0.5 / 64.0; // → -0.5 → 四捨五入で -1（偶数丸めではなく 0 から遠い方）
        w[2] = 1e6; // → 切り詰め
        let t = layout().table_size;
        w[t] = 0.25;
        w[t + 1] = -2.0;
        let (s, clamped) = quantize(&w);
        assert_eq!((s.table[0], s.table[1], s.table[2]), (64, -1, i16::MAX));
        assert_eq!((s.bias, s.mobility, clamped), (16, -128, 1));
    }
}
