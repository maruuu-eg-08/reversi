//! Recognize named openings (Tiger, Cow, Rose, ...) from a game record. Same results as `backend/openings.py`.
//!
//! The sequences come from Robert Gatliff's list of 77 openings (https://www.samsoft.org.uk/reversi/openings.htm).
//! The list starts with c4, so the record is rotated/reflected to start with c4 before comparing.
//! The table below is generated from the list in openings.py; a test checks that they agree.

use crate::book::transform;

/// (sequence, name)
pub const OPENINGS: [(&str, &str); 77] = [
    ("c4c3", "Diagonal Opening"),
    ("c4c3d3c5b2", "X-square Opening"),
    ("c4c3d3c5b3", "Snake/Peasant"),
    ("c4c3d3c5b3f3", "Lysons"),
    ("c4c3d3c5b3f4b5b4c6d6f5", "Pyramid/Checkerboarding Peasant"),
    ("c4c3d3c5b4", "Heath/Tobidashi"),
    ("c4c3d3c5b4d2c2f4d6c6f5e6f7", "Mimura Variation II"),
    ("c4c3d3c5b4d2d6", "Heath-Bat"),
    ("c4c3d3c5b4d2e2", "Iwasaki Variation"),
    ("c4c3d3c5b4e3", "Heath-Chimney"),
    ("c4c3d3c5b5", "Raccoon Dog"),
    ("c4c3d3c5b6", "Rocket"),
    ("c4c3d3c5b6c6b5", "Hamilton"),
    ("c4c3d3c5b6e3", "Lollipop"),
    ("c4c3d3c5d6", "Cow"),
    ("c4c3d3c5d6e3", "Chimney"),
    ("c4c3d3c5d6f4b4", "Cow Bat/Bat/Cambridge"),
    ("c4c3d3c5d6f4b4b6b5c6b3", "Bat (Piau Continuation 2)"),
    (
        "c4c3d3c5d6f4b4b6b5c6f5",
        "Melnikov/Bat (Piau Continuation 1)",
    ),
    (
        "c4c3d3c5d6f4b4c6b5b3b6e3c2a4a5a6d2",
        "Bat (Kling Continuation)",
    ),
    ("c4c3d3c5d6f4b4e3b3", "Bat (Kling Alternative)"),
    ("c4c3d3c5d6f4f5", "Rose-v-Toth"),
    ("c4c3d3c5d6f4f5d2", "Tanida"),
    ("c4c3d3c5d6f4f5d2b5", "Aircraft/Feldborg"),
    ("c4c3d3c5d6f4f5d2g4d7", "Sailboat"),
    ("c4c3d3c5d6f4f5e6c6d7", "Maruoka"),
    ("c4c3d3c5d6f4f5e6f6", "Landau"),
    ("c4c3d3c5f6", "Buffalo/Kenichi Variation"),
    ("c4c3d3c5f6e2c6", "Maruoka Buffalo"),
    ("c4c3d3c5f6e3c6f5f4g5", "Tanida Buffalo"),
    ("c4c3d3c5f6f5", "Hokuriku Buffalo"),
    ("c4c3e6c5", "Wing Variation"),
    ("c4c3f5c5", "Semi-Wing Variation"),
    ("c4c5", "Parallel Opening"),
    ("c4e3", "Perpendicular Opening"),
    ("c4e3f4c5d6e6", "Mimura"),
    ("c4e3f4c5d6f3c6", "Shaman/Danish"),
    ("c4e3f4c5d6f3d3", "Inoue"),
    ("c4e3f4c5d6f3d3c3", "Iago"),
    ("c4e3f4c5d6f3e2", "Bhagat"),
    ("c4e3f4c5d6f3e6c3d3e2", "Rose"),
    ("c4e3f4c5d6f3e6c3d3e2b5", "Flat"),
    ("c4e3f4c5d6f3e6c3d3e2b5f5", "Rotating Flat"),
    ("c4e3f4c5d6f3e6c3d3e2b5f5b3", "Murakami Variation"),
    (
        "c4e3f4c5d6f3e6c3d3e2b5f5b4f6c2e7d2c7",
        "Rotating Flat (Kling Continuation)",
    ),
    ("c4e3f4c5d6f3e6c3d3e2b6f5", "Rose-Birth"),
    ("c4e3f4c5d6f3e6c3d3e2b6f5b4f6g5d7", "Brightstein"),
    ("c4e3f4c5d6f3e6c3d3e2b6f5g5", "Rose-Birdie/Rose-Tamenori"),
    ("c4e3f4c5d6f3e6c3d3e2b6f5g5f6", "Rose-Tamenori-Kling"),
    ("c4e3f4c5d6f3e6c3d3e2d2", "Greenberg/Dawg"),
    ("c4e3f4c5d6f3e6c6", "Ralle"),
    ("c4e3f4c5e6", "Horse"),
    ("c4e3f5b4", "Ganglion/No-Cat"),
    ("c4e3f5b4f3", "Swallow"),
    ("c4e3f5b4f3f4e2e6g5f6d6c6", "No-Cat (Continuation)"),
    ("c4e3f5e6d3", "Italian"),
    ("c4e3f5e6f4", "Cat"),
    ("c4e3f5e6f4c5d6c6f7f3", "Sakaguchi"),
    ("c4e3f5e6f4c5d6c6f7g5g6", "Berner"),
    ("c4e3f6b4", "Bent Ganglion"),
    ("c4e3f6e6f5", "Tiger"),
    ("c4e3f6e6f5c5c3", "Stephenson"),
    ("c4e3f6e6f5c5c3b4", "No-Kung"),
    ("c4e3f6e6f5c5c3b4d6c6b5a6b6c7", "No-Kung (Continuation)"),
    ("c4e3f6e6f5c5c3c6", "Comp'Oth"),
    ("c4e3f6e6f5c5c3c6d3d2e2b3c1c2b4a3a5b5a6a4a2", "F.A.T. Draw"),
    ("c4e3f6e6f5c5c3c6d6", "Lightning Bolt"),
    ("c4e3f6e6f5c5c3g5", "Kung"),
    ("c4e3f6e6f5c5d3", "Leader's Tiger"),
    ("c4e3f6e6f5c5d6", "Brightwell"),
    ("c4e3f6e6f5c5f4g5g4f3c6d3d6", "Ishii"),
    ("c4e3f6e6f5c5f4g5g4f3c6d3d6b3c3b4e2b6", "Mainline Tiger"),
    ("c4e3f6e6f5c5f4g6f7", "Rose-Bill"),
    ("c4e3f6e6f5c5f4g6f7d3", "Tamenori"),
    ("c4e3f6e6f5c5f4g6f7g5", "Central Rose-Bill/Dead Draw"),
    ("c4e3f6e6f5g6", "Aubrey/Tanaka"),
    ("c4e3f6e6f5g6e7c5", "Aubrey (Feldborg Continuation)"),
];

const START: (u64, u64) = (0x0000_0008_1000_0000, 0x0000_0010_0800_0000);

fn parse_square(s: &[u8]) -> Option<u64> {
    let (c, r) = (s.first()?.to_ascii_lowercase(), *s.get(1)?);
    if !(b'a'..=b'h').contains(&c) || !(b'1'..=b'8').contains(&r) {
        return None;
    }
    Some(1u64 << ((r - b'1') as u32 * 8 + (c - b'a') as u32))
}

fn parse_transcript(t: &str) -> Option<Vec<u64>> {
    let b = t.as_bytes();
    if !b.len().is_multiple_of(2) {
        return None;
    }
    b.chunks(2).map(parse_square).collect()
}

/// Name of the longest opening matching a record ("f5d6c3...", no passes), e.g. "Tiger".
/// After the game leaves the book, the longest opening passed through is still returned. None if nothing matches.
pub fn identify(transcript: &str) -> Option<String> {
    let moves = parse_transcript(transcript)?;
    let first = *moves.first()?;
    let c4 = parse_square(b"c4").unwrap();
    // the symmetry that keeps the start position and maps the first move to c4
    let s = (0..8u8).find(|&s| {
        transform(START.0, s) == START.0
            && transform(START.1, s) == START.1
            && transform(first, s) == c4
    })?;
    let normalized: Vec<u64> = moves.iter().map(|&m| transform(m, s)).collect();
    let mut best: Option<(usize, &str)> = None;
    for (seq, name) in OPENINGS {
        let line = parse_transcript(seq).expect("the table's sequences are valid");
        if line.len() <= normalized.len()
            && normalized[..line.len()] == line[..]
            && best.is_none_or(|b| line.len() > b.0)
        {
            best = Some((line.len(), name));
        }
    }
    best.map(|(_, name)| name.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tiger_in_every_orientation() {
        for t in ["f5d6c3d3c4", "c4e3f6e6f5", "d3c5f6f5e6", "e6f4c3c4d3"] {
            assert_eq!(identify(t).as_deref(), Some("Tiger"));
        }
    }

    #[test]
    fn short_or_invalid() {
        assert_eq!(identify(""), None);
        assert_eq!(identify("f5"), None);
        assert_eq!(identify("a1"), None);
        assert_eq!(identify("zz"), None);
        assert_eq!(identify("f5d"), None);
        assert_eq!(identify("f5d6").as_deref(), Some("Perpendicular Opening"));
    }
}
