//! パターン評価。`backend/patterns.py` と同じ定義・同じ計算をする。
//!
//! 盤面のいくつかの「形」（パターン）について、石の並び（空き / 手番側 / 相手 の3通り）ごとに
//! 点数の表を持ち、局面に現れた並びの点数を足し合わせて評価値にする。
//! 点数はすべて整数（1/`SCALE` 石単位）なので、Python 版と完全に同じ値になる。

use std::fs;
use std::io;
use std::path::Path;
use std::sync::OnceLock;

/// 点数の単位。表の値 64 が石1個分
pub const SCALE: i32 = 64;
/// 段階の数。手数（60 - 空きマス）を4手ごとに区切る
pub const N_STAGES: usize = 15;

/// (名前, 基本の向きでのマス)。マスの順番が並びの番号の桁の順番になる
pub const FAMILIES: [(&str, &str); 11] = [
    ("hv2", "a2 b2 c2 d2 e2 f2 g2 h2"),
    ("hv3", "a3 b3 c3 d3 e3 f3 g3 h3"),
    ("hv4", "a4 b4 c4 d4 e4 f4 g4 h4"),
    ("diag8", "a1 b2 c3 d4 e5 f6 g7 h8"),
    ("diag7", "b1 c2 d3 e4 f5 g6 h7"),
    ("diag6", "c1 d2 e3 f4 g5 h6"),
    ("diag5", "d1 e2 f3 g4 h5"),
    ("diag4", "e1 f2 g3 h4"),
    ("edge2x", "a1 b1 c1 d1 e1 f1 g1 h1 b2 g2"),
    ("corner3x3", "a1 b1 c1 a2 b2 c2 a3 b3 c3"),
    ("corner2x5", "a1 b1 c1 d1 e1 a2 b2 c2 d2 e2"),
];

const MAGIC: &[u8] = b"RVPAT\x01";

/// 回転・反転したパターン1つ分（どのパターンか、どのマスをどの順で見るか）
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Instance {
    pub family: usize,
    pub squares: Vec<u8>,
}

/// 定義から決まる表の大きさなどの情報
pub struct Layout {
    pub instances: Vec<Instance>,
    pub family_sizes: Vec<usize>,
    pub family_offsets: Vec<usize>,
    pub table_size: usize,
}

fn parse_square(name: &str) -> u8 {
    let b = name.as_bytes();
    (b[1] - b'1') * 8 + (b[0] - b'a')
}

/// マス i を対称変換 s で移す（Python 版の `_map_square` と同じ）。
fn map_square(i: u8, s: u8) -> u8 {
    let (mut r, mut c) = (i / 8, i % 8);
    if s & 4 != 0 {
        (r, c) = (c, r);
    }
    if s & 2 != 0 {
        r = 7 - r;
    }
    if s & 1 != 0 {
        c = 7 - c;
    }
    r * 8 + c
}

/// パターンの定義（Python 版と同じ順番でインスタンスを作る）。
pub fn layout() -> &'static Layout {
    static LAYOUT: OnceLock<Layout> = OnceLock::new();
    LAYOUT.get_or_init(|| {
        let mut instances = Vec::new();
        let mut family_sizes = Vec::new();
        for (family, (_, squares)) in FAMILIES.iter().enumerate() {
            let base: Vec<u8> = squares.split_whitespace().map(parse_square).collect();
            family_sizes.push(3usize.pow(base.len() as u32));
            // マスとその順番がまったく同じになるものだけを除く（Python 版と同じ）。
            // 一覧が回転・反転について閉じるので、評価値は盤面の対称性を必ず保つ
            let mut seen: Vec<Vec<u8>> = Vec::new();
            for s in 0..8 {
                let image: Vec<u8> = base.iter().map(|&i| map_square(i, s)).collect();
                if !seen.contains(&image) {
                    seen.push(image.clone());
                    instances.push(Instance {
                        family,
                        squares: image,
                    });
                }
            }
        }
        let family_offsets = family_sizes
            .iter()
            .scan(0, |acc, &n| {
                let start = *acc;
                *acc += n;
                Some(start)
            })
            .collect();
        let table_size = family_sizes.iter().sum();
        Layout {
            instances,
            family_sizes,
            family_offsets,
            table_size,
        }
    })
}

/// 空きマスの数から段階を求める（0: 序盤 〜 N_STAGES-1: 終盤）。
#[inline]
pub fn stage_of(n_empty: u32) -> usize {
    (60u32.saturating_sub(n_empty) / 4).min(N_STAGES as u32 - 1) as usize
}

/// 各インスタンスの並びの番号（Σ 桁 × 3^k、桁は 空き=0 / 手番側=1 / 相手=2）。
pub fn indices(p: u64, o: u64) -> Vec<u32> {
    layout()
        .instances
        .iter()
        .map(|inst| index_of(p, o, &inst.squares))
        .collect()
}

#[inline]
fn index_of(p: u64, o: u64, squares: &[u8]) -> u32 {
    squares.iter().rev().fold(0u32, |idx, &i| {
        idx * 3 + ((p >> i) & 1) as u32 + 2 * ((o >> i) & 1) as u32
    })
}

/// 1段階分の点数
#[derive(Clone, Debug, PartialEq)]
pub struct Stage {
    pub bias: i32,
    pub mobility: i32,
    /// 全パターンの表を並べたもの（`Layout::family_offsets` の位置から各パターンの表）
    pub table: Vec<i16>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PatternWeights {
    pub stages: Vec<Stage>,
}

impl PatternWeights {
    /// すべて 0 の重み。
    pub fn zeros() -> Self {
        let size = layout().table_size;
        Self {
            stages: (0..N_STAGES)
                .map(|_| Stage {
                    bias: 0,
                    mobility: 0,
                    table: vec![0; size],
                })
                .collect(),
        }
    }

    /// 手番側 `p` から見た評価値の整数部分（1/SCALE 石単位）。`my_moves` / `opp_moves` は両者の合法手。
    #[inline]
    pub fn evaluate_raw(&self, p: u64, o: u64, my_moves: u64, opp_moves: u64) -> i32 {
        let lay = layout();
        let stage = &self.stages[stage_of((!(p | o)).count_ones())];
        let mobility = my_moves.count_ones() as i32 - opp_moves.count_ones() as i32;
        let mut total = stage.bias + stage.mobility * mobility;
        for inst in &lay.instances {
            let idx = index_of(p, o, &inst.squares) as usize;
            total += i32::from(stage.table[lay.family_offsets[inst.family] + idx]);
        }
        total
    }

    /// 手番側 `p` から見た評価値（石数の単位）。
    #[inline]
    pub fn evaluate(&self, p: u64, o: u64, my_moves: u64, opp_moves: u64) -> f64 {
        f64::from(self.evaluate_raw(p, o, my_moves, opp_moves)) / f64::from(SCALE)
    }

    /// Python 版と同じ形式（リトルエンディアン）で保存する。
    pub fn save(&self, path: impl AsRef<Path>) -> io::Result<()> {
        let lay = layout();
        let mut out = Vec::with_capacity(16 + N_STAGES * (8 + 2 * lay.table_size));
        out.extend_from_slice(MAGIC);
        out.extend_from_slice(&(N_STAGES as u16).to_le_bytes());
        out.extend_from_slice(&(FAMILIES.len() as u16).to_le_bytes());
        for &size in &lay.family_sizes {
            out.extend_from_slice(&(size as u32).to_le_bytes());
        }
        for stage in &self.stages {
            out.extend_from_slice(&stage.bias.to_le_bytes());
            out.extend_from_slice(&stage.mobility.to_le_bytes());
            for v in &stage.table {
                out.extend_from_slice(&v.to_le_bytes());
            }
        }
        fs::write(path, out)
    }

    pub fn load(path: impl AsRef<Path>) -> io::Result<Self> {
        let path = path.as_ref();
        let data = fs::read(path)?;
        Self::from_bytes(&data).map_err(|e| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                format!("{}: {e}", path.display()),
            )
        })
    }

    pub fn from_bytes(data: &[u8]) -> Result<Self, String> {
        let lay = layout();
        let mut r = Reader { data, pos: 0 };
        if r.take(MAGIC.len())? != MAGIC {
            return Err("パターンの重みファイルではありません".into());
        }
        let n_stages = r.u16()? as usize;
        let n_families = r.u16()? as usize;
        let sizes: Vec<usize> = (0..n_families)
            .map(|_| r.u32().map(|v| v as usize))
            .collect::<Result<_, _>>()?;
        if n_stages != N_STAGES || sizes != lay.family_sizes {
            return Err("パターンの定義がこのプログラムと違います".into());
        }
        let mut stages = Vec::with_capacity(N_STAGES);
        for _ in 0..N_STAGES {
            let bias = r.i32()?;
            let mobility = r.i32()?;
            let bytes = r.take(2 * lay.table_size)?;
            let table = bytes
                .chunks_exact(2)
                .map(|b| i16::from_le_bytes([b[0], b[1]]))
                .collect();
            stages.push(Stage {
                bias,
                mobility,
                table,
            });
        }
        if r.pos != data.len() {
            return Err("ファイルの大きさが正しくありません".into());
        }
        Ok(Self { stages })
    }
}

struct Reader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], String> {
        let end = self
            .pos
            .checked_add(n)
            .filter(|&e| e <= self.data.len())
            .ok_or("ファイルが途中で切れています")?;
        let s = &self.data[self.pos..end];
        self.pos = end;
        Ok(s)
    }
    fn u16(&mut self) -> Result<u16, String> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into().unwrap()))
    }
    fn u32(&mut self) -> Result<u32, String> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn i32(&mut self) -> Result<i32, String> {
        Ok(i32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::board::legal_moves;

    #[test]
    fn layout_has_expected_sizes() {
        let lay = layout();
        assert_eq!(lay.instances.len(), 84); // 対角線（diag8）は4通り、ほかは8通り
        assert_eq!(lay.table_size, 167_265);
        // 各インスタンスのマスは重複しない
        for inst in &lay.instances {
            let mut s = inst.squares.clone();
            s.sort();
            s.dedup();
            assert_eq!(s.len(), inst.squares.len());
        }
    }

    #[test]
    fn stages_cover_the_game() {
        assert_eq!(stage_of(60), 0);
        assert_eq!(stage_of(57), 0);
        assert_eq!(stage_of(56), 1);
        assert_eq!(stage_of(4), 14);
        assert_eq!(stage_of(0), 14);
    }

    #[test]
    fn index_encodes_each_square_in_base3() {
        // corner3x3 の最初のインスタンス（a1 b1 c1 a2 b2 c2 a3 b3 c3）
        let inst = &layout()
            .instances
            .iter()
            .find(|i| FAMILIES[i.family].0 == "corner3x3")
            .unwrap()
            .squares;
        let p = 1u64 << inst[0]; // 1桁目 = 手番側 → 1
        let o = 1u64 << inst[1]; // 2桁目 = 相手 → 2*3
        assert_eq!(index_of(p, o, inst), 1 + 2 * 3);
    }

    #[test]
    fn file_round_trip_and_validation() {
        let mut w = PatternWeights::zeros();
        w.stages[3].bias = -5;
        w.stages[3].mobility = 7;
        w.stages[3].table[123] = -321;
        let path = std::env::temp_dir().join("reversi_pattern_test.bin");
        w.save(&path).unwrap();
        assert_eq!(PatternWeights::load(&path).unwrap(), w);
        let bytes = fs::read(&path).unwrap();
        assert!(PatternWeights::from_bytes(&bytes[..bytes.len() - 1]).is_err());
        assert!(PatternWeights::from_bytes(b"nope").is_err());
        let _ = fs::remove_file(path);
    }

    #[test]
    fn evaluate_sums_bias_mobility_and_table() {
        let mut w = PatternWeights::zeros();
        let (p, o) = (0x0000_0008_1000_0000u64, 0x0000_0010_0800_0000u64);
        w.stages[0].bias = 10;
        w.stages[0].mobility = 3;
        let (mp, mo) = (legal_moves(p, o), legal_moves(o, p));
        // 開始局面は互いに4手ずつなので着手可能数の差は 0
        assert_eq!(w.evaluate_raw(p, o, mp, mo), 10);
        // ある並びに点数を入れると、その並びになっているインスタンスの数だけ足される
        let lay = layout();
        let diag = lay
            .instances
            .iter()
            .find(|i| FAMILIES[i.family].0 == "diag8")
            .unwrap();
        let idx = index_of(p, o, &diag.squares);
        w.stages[0].table[lay.family_offsets[diag.family] + idx as usize] = 64;
        let hits = lay
            .instances
            .iter()
            .filter(|i| i.family == diag.family && index_of(p, o, &i.squares) == idx)
            .count() as f64;
        assert!(hits >= 1.0);
        assert_eq!(w.evaluate(p, o, mp, mo), (10.0 + 64.0 * hits) / 64.0);
    }
}
