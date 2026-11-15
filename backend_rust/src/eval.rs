//! 評価関数。`StrongAI.evaluate` / `StrongAI.final_score` と同じ値を返す。
//!
//! Python 版とビット単位で同じ浮動小数点数になるよう、足し算の順番まで揃えている
//! （浮動小数点の足し算は順番を変えると結果が変わることがあるため）。

use crate::board::{legal_moves, neighbors};

/// 特徴量の数（位置, 着手可能数, 石数, 開放度）
pub const N_FEATURES: usize = 4;
/// 係数の数（特徴量 × 序盤・中盤・終盤）
pub const N_COEFFS: usize = 3 * N_FEATURES;
/// 終局の評価値の基準（`weights.WIN_SCORE`）
pub const WIN_SCORE: f64 = 10_000.0;

#[derive(Clone, Debug)]
pub struct Evaluator {
    coeffs: [f64; N_COEFFS],
    /// 行ごと（8ビット）の石の並び 256 通りに対する重みの合計
    row_tables: [[f64; 256]; 8],
    /// マスごとの重み（手の並べ替えに使う）
    weights: [f64; 64],
}

impl Evaluator {
    /// `coeffs` は 12 個、`weights` は 64 個。
    pub fn new(coeffs: &[f64], weights: &[f64]) -> Result<Self, String> {
        let coeffs: [f64; N_COEFFS] = coeffs
            .try_into()
            .map_err(|_| format!("coeffs must have {N_COEFFS} values, got {}", coeffs.len()))?;
        let weights: [f64; 64] = weights
            .try_into()
            .map_err(|_| format!("weights must have 64 values, got {}", weights.len()))?;
        let mut row_tables = [[0.0; 256]; 8];
        for (row, table) in row_tables.iter_mut().enumerate() {
            for (pattern, value) in table.iter_mut().enumerate() {
                // Python の sum() と同じく、列の小さい順に足す
                *value = (0..8)
                    .filter(|c| (pattern >> c) & 1 == 1)
                    .fold(0.0, |acc, c| acc + weights[row * 8 + c]);
            }
        }
        Ok(Self {
            coeffs,
            row_tables,
            weights,
        })
    }

    /// マス `x`（1ビット）の重み。
    #[inline]
    pub fn weight(&self, x: u64) -> f64 {
        self.weights[x.trailing_zeros() as usize]
    }

    /// 石の並び `b` の位置の重みの合計。
    #[inline]
    pub fn position(&self, b: u64) -> f64 {
        let t = &self.row_tables;
        t[0][(b & 255) as usize]
            + t[1][((b >> 8) & 255) as usize]
            + t[2][((b >> 16) & 255) as usize]
            + t[3][((b >> 24) & 255) as usize]
            + t[4][((b >> 32) & 255) as usize]
            + t[5][((b >> 40) & 255) as usize]
            + t[6][((b >> 48) & 255) as usize]
            + t[7][((b >> 56) & 255) as usize]
    }

    /// 手番側 `p` から見た評価値。`my_moves` は `legal_moves(p, o)`。
    #[inline]
    pub fn evaluate(&self, p: u64, o: u64, my_moves: u64) -> f64 {
        let empty = !(p | o);
        let n_empty = empty.count_ones();
        let base = if n_empty >= 45 {
            0
        } else if n_empty >= 15 {
            N_FEATURES
        } else {
            2 * N_FEATURES
        };
        let c = &self.coeffs;
        let adj = neighbors(empty);
        let mobility = my_moves.count_ones() as i32 - legal_moves(o, p).count_ones() as i32;
        let discs = p.count_ones() as i32 - o.count_ones() as i32;
        let frontier = (o & adj).count_ones() as i32 - (p & adj).count_ones() as i32;
        c[base] * (self.position(p) - self.position(o))
            + c[base + 1] * f64::from(mobility)
            + c[base + 2] * f64::from(discs)
            + c[base + 3] * f64::from(frontier)
    }
}

/// 終局時の評価（`p` から見て）。空きマスは勝った側に加える。
#[inline]
pub fn final_score(p: u64, o: u64) -> f64 {
    let pc = p.count_ones() as i32;
    let oc = o.count_ones() as i32;
    let empty = 64 - pc - oc;
    if pc > oc {
        WIN_SCORE + f64::from(pc - oc + empty)
    } else if pc < oc {
        -WIN_SCORE + f64::from(pc - oc - empty)
    } else {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn evaluator() -> Evaluator {
        let weights: Vec<f64> = (0..64).map(|i| i as f64 * 0.5 - 7.0).collect();
        let coeffs: Vec<f64> = (0..12).map(|i| 1.0 + i as f64).collect();
        Evaluator::new(&coeffs, &weights).unwrap()
    }

    #[test]
    fn rejects_wrong_lengths() {
        assert!(Evaluator::new(&[0.0; 11], &[0.0; 64]).is_err());
        assert!(Evaluator::new(&[0.0; 12], &[0.0; 63]).is_err());
    }

    #[test]
    fn position_equals_sum_of_weights() {
        let e = evaluator();
        let b = 0x8100_0000_0000_0081u64 | (1 << 27);
        let naive: f64 = (0..64)
            .filter(|i| (b >> i) & 1 == 1)
            .map(|i| i as f64 * 0.5 - 7.0)
            .sum();
        assert_eq!(e.position(b), naive);
    }

    #[test]
    fn final_score_gives_empties_to_winner() {
        // P: 3石, O: 1石, 空き 60
        assert_eq!(final_score(0b111, 1 << 63), WIN_SCORE + 2.0 + 60.0);
        assert_eq!(final_score(1 << 63, 0b111), -WIN_SCORE - 2.0 - 60.0);
        assert_eq!(final_score(1, 2), 0.0);
    }
}
