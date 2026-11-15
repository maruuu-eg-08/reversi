//! ビットボードの基本操作。`backend/strong_ai.py` の同名の関数と同じ結果を返す。
//!
//! 盤面は (手番側 P, 相手側 O) の 64 ビット整数。マス i = 行 * 8 + 列（a1 = 0, h8 = 63）。

/// a列・h列を除くマス（横・斜め方向で行をまたいで回り込まないようにする）
const NOT_EDGE_COLS: u64 = 0x7E7E_7E7E_7E7E_7E7E;
/// 左シフト後に a列へ回り込んだビットを消す
const NOT_COL_A: u64 = 0xFEFE_FEFE_FEFE_FEFE;
/// 右シフト後に h列へ回り込んだビットを消す
const NOT_COL_H: u64 = 0x7F7F_7F7F_7F7F_7F7F;

/// (シフト量, 相手石のマスク) の組。縦方向(8)だけは端の列を除かない。
#[inline(always)]
fn directions(o: u64) -> [(u32, u64); 4] {
    let oh = o & NOT_EDGE_COLS;
    [(1, oh), (8, o), (7, oh), (9, oh)]
}

/// 手番側 `p` が打てるマス。
#[inline]
pub fn legal_moves(p: u64, o: u64) -> u64 {
    let empty = !(p | o);
    let mut moves = 0;
    for (s, m) in directions(o) {
        let mut t = (p << s) & m;
        t |= (t << s) & m;
        t |= (t << s) & m;
        t |= (t << s) & m;
        t |= (t << s) & m;
        t |= (t << s) & m;
        moves |= (t << s) & empty;

        let mut t = (p >> s) & m;
        t |= (t >> s) & m;
        t |= (t >> s) & m;
        t |= (t >> s) & m;
        t |= (t >> s) & m;
        t |= (t >> s) & m;
        moves |= (t >> s) & empty;
    }
    moves
}

/// `p` が `x`（1ビット）に打ったときに裏返る石。
#[inline]
pub fn flips(p: u64, o: u64, x: u64) -> u64 {
    let mut f = 0;
    for (s, m) in directions(o) {
        let mut t = 0;
        let mut y = x << s;
        while y & m != 0 {
            t |= y;
            y <<= s;
        }
        if y & p != 0 {
            f |= t;
        }

        let mut t = 0;
        let mut y = x >> s;
        while y & m != 0 {
            t |= y;
            y >>= s;
        }
        if y & p != 0 {
            f |= t;
        }
    }
    f
}

/// `b` の8近傍のマス。
#[inline]
pub fn neighbors(b: u64) -> u64 {
    ((b << 1) & NOT_COL_A)
        | ((b >> 1) & NOT_COL_H)
        | (b << 8)
        | (b >> 8)
        | ((b << 9) & NOT_COL_A)
        | ((b >> 9) & NOT_COL_H)
        | ((b << 7) & NOT_COL_H)
        | ((b >> 7) & NOT_COL_A)
}

/// `p` が `x` に打った後の局面を、次の手番側から見た (P, O) で返す。
#[inline]
pub fn play(p: u64, o: u64, x: u64) -> (u64, u64) {
    let f = flips(p, o, x);
    (o ^ f, p | x | f)
}

/// 立っているビットを下位から1つずつ取り出す。
#[inline]
pub fn bits(mut m: u64) -> impl Iterator<Item = u64> {
    std::iter::from_fn(move || {
        if m == 0 {
            None
        } else {
            let x = m & m.wrapping_neg();
            m ^= x;
            Some(x)
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    pub const START: (u64, u64) = (0x0000_0008_1000_0000, 0x0000_0010_0800_0000);

    fn sq(name: &str) -> u64 {
        let b = name.as_bytes();
        1 << ((b[1] - b'1') as u64 * 8 + (b[0] - b'a') as u64)
    }

    /// パスも1手として数える（Python の tests/test_bitboard.py と同じ定義）。
    fn perft(p: u64, o: u64, depth: u32, passed: bool) -> u64 {
        if depth == 0 {
            return 1;
        }
        let moves = legal_moves(p, o);
        if moves == 0 {
            return if passed {
                1
            } else {
                perft(o, p, depth - 1, true)
            };
        }
        bits(moves)
            .map(|x| {
                let (np, no) = play(p, o, x);
                perft(np, no, depth - 1, false)
            })
            .sum()
    }

    #[test]
    fn start_position_moves() {
        let (p, o) = START;
        assert_eq!(legal_moves(p, o), sq("d3") | sq("c4") | sq("f5") | sq("e6"));
        assert_eq!(flips(p, o, sq("f5")), sq("e5"));
    }

    #[test]
    fn perft_matches_known_values() {
        let (p, o) = START;
        let expected = [1, 4, 12, 56, 244, 1396, 8200, 55092, 390216];
        for (depth, &n) in expected.iter().enumerate() {
            assert_eq!(perft(p, o, depth as u32, false), n, "depth {depth}");
        }
    }

    #[test]
    fn moves_do_not_wrap_around_rows() {
        // h1 の右隣はビットの上では次の行の a2。a2 の相手石を挟んで b2 に打てたら回り込みのバグ
        let p = sq("h1");
        let o = sq("a2");
        assert_eq!(legal_moves(p, o) & sq("b2"), 0);
        assert_eq!(flips(p, o, sq("b2")), 0);
    }

    #[test]
    fn neighbors_of_corner() {
        assert_eq!(neighbors(sq("a1")), sq("b1") | sq("a2") | sq("b2"));
        assert_eq!(neighbors(sq("h8")), sq("g8") | sq("h7") | sq("g7"));
    }

    #[test]
    fn bits_iterates_low_to_high() {
        let v: Vec<u64> = bits(0b1010_0001).collect();
        assert_eq!(v, vec![1, 0b10_0000, 0b1000_0000]);
    }
}
