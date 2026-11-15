//! Bitboard primitives. Same results as the functions of the same name in `backend/strong_ai.py`.
//!
//! Boards are (player P, opponent O) 64-bit integers; square i = row * 8 + col (a1 = 0, h8 = 63).

/// Squares outside the a- and h-files (horizontal/diagonal runs must not wrap across rows)
const NOT_EDGE_COLS: u64 = 0x7E7E_7E7E_7E7E_7E7E;
/// Clears bits that wrapped onto the a-file after a left shift
const NOT_COL_A: u64 = 0xFEFE_FEFE_FEFE_FEFE;
/// Clears bits that wrapped onto the h-file after a right shift
const NOT_COL_H: u64 = 0x7F7F_7F7F_7F7F_7F7F;

/// (shift, opponent mask) pairs. Only the vertical direction (8) keeps the edge files.
#[inline(always)]
fn directions(o: u64) -> [(u32, u64); 4] {
    let oh = o & NOT_EDGE_COLS;
    [(1, oh), (8, o), (7, oh), (9, oh)]
}

/// Squares where the player to move `p` can play.
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

/// Discs flipped when `p` plays on `x` (a single bit).
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

/// The 8-neighborhood of `b`.
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

/// Position after `p` plays `x`, as (P, O) for the next player to move.
#[inline]
pub fn play(p: u64, o: u64, x: u64) -> (u64, u64) {
    let f = flips(p, o, x);
    (o ^ f, p | x | f)
}

/// Iterate over the set bits from the lowest.
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

    /// A pass counts as a ply (same definition as Python's tests/test_bitboard.py).
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
        // the bit after h1 is a2 on the next row; capturing a2 by playing b2 would be a wrap-around bug
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
