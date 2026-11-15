//! Opening book lookup. Reads the same file format as `backend/opening_book.py` and returns the same moves.
//!
//! Positions are stored in canonical form (the smallest of the 8 rotations/reflections), so a lookup
//! canonicalizes the query the same way and maps the stored move back to the original orientation.

use rustc_hash::FxHashMap;

use crate::board::legal_moves;

/// Flip vertically (row 1 <-> row 8)
fn flip_vertical(b: u64) -> u64 {
    b.swap_bytes()
}

/// Mirror horizontally (a-file <-> h-file)
fn mirror_horizontal(b: u64) -> u64 {
    let b = ((b >> 1) & 0x5555_5555_5555_5555) | ((b & 0x5555_5555_5555_5555) << 1);
    let b = ((b >> 2) & 0x3333_3333_3333_3333) | ((b & 0x3333_3333_3333_3333) << 2);
    ((b >> 4) & 0x0F0F_0F0F_0F0F_0F0F) | ((b & 0x0F0F_0F0F_0F0F_0F0F) << 4)
}

/// Reflect in the a1-h8 diagonal
fn transpose(mut b: u64) -> u64 {
    let t = 0x0F0F_0F0F_0000_0000 & (b ^ (b << 28));
    b ^= t ^ (t >> 28);
    let t = 0x3333_0000_3333_0000 & (b ^ (b << 14));
    b ^= t ^ (t >> 14);
    let t = 0x5500_5500_5500_5500 & (b ^ (b << 7));
    b ^= t ^ (t >> 7);
    b
}

/// Symmetry s (0-7): bit 2 transpose, then bit 1 vertical flip, then bit 0 mirror (same as Python)
pub fn transform(mut b: u64, s: u8) -> u64 {
    if s & 4 != 0 {
        b = transpose(b);
    }
    if s & 2 != 0 {
        b = flip_vertical(b);
    }
    if s & 1 != 0 {
        b = mirror_horizontal(b);
    }
    b
}

pub fn inverse_transform(mut b: u64, s: u8) -> u64 {
    if s & 1 != 0 {
        b = mirror_horizontal(b);
    }
    if s & 2 != 0 {
        b = flip_vertical(b);
    }
    if s & 4 != 0 {
        b = transpose(b);
    }
    b
}

/// The smallest (P, O) among the 8 images and the symmetry that produces it
pub fn canonical(p: u64, o: u64) -> (u64, u64, u8) {
    (0..8u8)
        .map(|s| (transform(p, s), transform(o, s), s))
        .min_by_key(|&(a, b, _)| (a, b))
        .unwrap()
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct BookHit {
    pub best_move: u64,
    pub score: f64,
    pub depth: u32,
}

#[derive(Default)]
pub struct OpeningBook {
    entries: FxHashMap<(u64, u64), (u64, f64, u32)>,
}

impl OpeningBook {
    /// Parse the contents of `opening_book.txt`.
    pub fn parse(text: &str) -> Result<Self, String> {
        let mut entries = FxHashMap::default();
        for (lineno, line) in text.lines().enumerate() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let err = || format!("line {}: invalid opening book line", lineno + 1);
            let f: Vec<&str> = line.split_whitespace().collect();
            if f.len() != 5 {
                return Err(err());
            }
            let p = u64::from_str_radix(f[0], 16).map_err(|_| err())?;
            let o = u64::from_str_radix(f[1], 16).map_err(|_| err())?;
            let m = f[2].as_bytes();
            if m.len() != 2 || !(b'a'..=b'h').contains(&m[0]) || !(b'1'..=b'8').contains(&m[1]) {
                return Err(err());
            }
            let mv = 1u64 << ((m[1] - b'1') as u32 * 8 + (m[0] - b'a') as u32);
            let score: f64 = f[3].parse().map_err(|_| err())?;
            let depth: u32 = f[4].parse().map_err(|_| err())?;
            entries.insert((p, o), (mv, score, depth));
        }
        Ok(Self { entries })
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// If the position is in the book, the move in the queried orientation (None if it is not legal).
    pub fn probe(&self, p: u64, o: u64) -> Option<BookHit> {
        let (cp, co, s) = canonical(p, o);
        let &(mv, score, depth) = self.entries.get(&(cp, co))?;
        let best_move = inverse_transform(mv, s);
        (best_move & legal_moves(p, o) != 0).then_some(BookHit {
            best_move,
            score,
            depth,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn transforms_are_involutions_and_distinct() {
        let b = 0x0123_4567_89AB_CDEFu64;
        let mut images: Vec<u64> = (0..8).map(|s| transform(b, s)).collect();
        for s in 0..8 {
            assert_eq!(inverse_transform(transform(b, s), s), b);
        }
        images.sort();
        images.dedup();
        assert_eq!(images.len(), 8);
        assert_eq!(transpose(1 << 1), 1 << 8); // b1 → a2
    }

    #[test]
    fn probe_in_every_orientation() {
        let (p, o) = (0x0000_0008_1000_0000u64, 0x0000_0010_0800_0000u64);
        let f5 = 1u64 << (4 * 8 + 5);
        let (cp, co, s) = canonical(p, o);
        let mv = transform(f5, s);
        let name = format!(
            "{}{}",
            (b'a' + (mv.trailing_zeros() % 8) as u8) as char,
            mv.trailing_zeros() / 8 + 1
        );
        let book =
            OpeningBook::parse(&format!("# c\n{cp:016x} {co:016x} {name} 0.50 10\n")).unwrap();
        assert_eq!(book.len(), 1);
        for t in 0..8 {
            let hit = book.probe(transform(p, t), transform(o, t)).unwrap();
            assert_ne!(
                hit.best_move & legal_moves(transform(p, t), transform(o, t)),
                0
            );
        }
        assert_eq!(book.probe(p, o).unwrap().best_move, f5);
        assert!(OpeningBook::parse("zz").is_err());
    }
}
