//! 名前の付いた定石（虎・牛・ローズなど）を棋譜から判定する。`backend/openings.py` と同じ結果を返す。
//!
//! 手順は Robert Gatliff の定石リスト（77種、https://www.samsoft.org.uk/reversi/openings.htm）による。
//! リストは初手を c4 で書いているので、棋譜を回転・反転して初手を c4 に合わせてから比べる。
//! 下の表は openings.py の一覧から機械的に作ったもので、一致はテストで確認している。

use crate::book::transform;

/// (手順, 英語名, 日本語名)
pub const OPENINGS: [(&str, &str, Option<&str>); 77] = [
    ("c4c3", "Diagonal Opening", Some("斜め取り")),
    ("c4c3d3c5b2", "X-square Opening", None),
    ("c4c3d3c5b3", "Snake/Peasant", None),
    ("c4c3d3c5b3f3", "Lysons", None),
    (
        "c4c3d3c5b3f4b5b4c6d6f5",
        "Pyramid/Checkerboarding Peasant",
        None,
    ),
    ("c4c3d3c5b4", "Heath/Tobidashi", Some("ヒース（飛び出し）")),
    ("c4c3d3c5b4d2c2f4d6c6f5e6f7", "Mimura Variation II", None),
    ("c4c3d3c5b4d2d6", "Heath-Bat", None),
    ("c4c3d3c5b4d2e2", "Iwasaki Variation", None),
    ("c4c3d3c5b4e3", "Heath-Chimney", None),
    ("c4c3d3c5b5", "Raccoon Dog", None),
    ("c4c3d3c5b6", "Rocket", None),
    ("c4c3d3c5b6c6b5", "Hamilton", None),
    ("c4c3d3c5b6e3", "Lollipop", None),
    ("c4c3d3c5d6", "Cow", Some("牛")),
    ("c4c3d3c5d6e3", "Chimney", None),
    ("c4c3d3c5d6f4b4", "Cow Bat/Bat/Cambridge", None),
    ("c4c3d3c5d6f4b4b6b5c6b3", "Bat (Piau Continuation 2)", None),
    (
        "c4c3d3c5d6f4b4b6b5c6f5",
        "Melnikov/Bat (Piau Continuation 1)",
        None,
    ),
    (
        "c4c3d3c5d6f4b4c6b5b3b6e3c2a4a5a6d2",
        "Bat (Kling Continuation)",
        None,
    ),
    ("c4c3d3c5d6f4b4e3b3", "Bat (Kling Alternative)", None),
    ("c4c3d3c5d6f4f5", "Rose-v-Toth", None),
    ("c4c3d3c5d6f4f5d2", "Tanida", None),
    ("c4c3d3c5d6f4f5d2b5", "Aircraft/Feldborg", None),
    ("c4c3d3c5d6f4f5d2g4d7", "Sailboat", None),
    ("c4c3d3c5d6f4f5e6c6d7", "Maruoka", None),
    ("c4c3d3c5d6f4f5e6f6", "Landau", None),
    (
        "c4c3d3c5f6",
        "Buffalo/Kenichi Variation",
        Some("バッファロー"),
    ),
    ("c4c3d3c5f6e2c6", "Maruoka Buffalo", None),
    ("c4c3d3c5f6e3c6f5f4g5", "Tanida Buffalo", None),
    ("c4c3d3c5f6f5", "Hokuriku Buffalo", None),
    ("c4c3e6c5", "Wing Variation", None),
    ("c4c3f5c5", "Semi-Wing Variation", None),
    ("c4c5", "Parallel Opening", Some("並び取り")),
    ("c4e3", "Perpendicular Opening", Some("縦取り")),
    ("c4e3f4c5d6e6", "Mimura", None),
    ("c4e3f4c5d6f3c6", "Shaman/Danish", None),
    ("c4e3f4c5d6f3d3", "Inoue", None),
    ("c4e3f4c5d6f3d3c3", "Iago", None),
    ("c4e3f4c5d6f3e2", "Bhagat", None),
    ("c4e3f4c5d6f3e6c3d3e2", "Rose", Some("ローズ")),
    ("c4e3f4c5d6f3e6c3d3e2b5", "Flat", None),
    ("c4e3f4c5d6f3e6c3d3e2b5f5", "Rotating Flat", None),
    ("c4e3f4c5d6f3e6c3d3e2b5f5b3", "Murakami Variation", None),
    (
        "c4e3f4c5d6f3e6c3d3e2b5f5b4f6c2e7d2c7",
        "Rotating Flat (Kling Continuation)",
        None,
    ),
    ("c4e3f4c5d6f3e6c3d3e2b6f5", "Rose-Birth", None),
    ("c4e3f4c5d6f3e6c3d3e2b6f5b4f6g5d7", "Brightstein", None),
    (
        "c4e3f4c5d6f3e6c3d3e2b6f5g5",
        "Rose-Birdie/Rose-Tamenori",
        None,
    ),
    ("c4e3f4c5d6f3e6c3d3e2b6f5g5f6", "Rose-Tamenori-Kling", None),
    ("c4e3f4c5d6f3e6c3d3e2d2", "Greenberg/Dawg", None),
    ("c4e3f4c5d6f3e6c6", "Ralle", None),
    ("c4e3f4c5e6", "Horse", None),
    ("c4e3f5b4", "Ganglion/No-Cat", None),
    ("c4e3f5b4f3", "Swallow", None),
    ("c4e3f5b4f3f4e2e6g5f6d6c6", "No-Cat (Continuation)", None),
    ("c4e3f5e6d3", "Italian", None),
    ("c4e3f5e6f4", "Cat", Some("猫")),
    ("c4e3f5e6f4c5d6c6f7f3", "Sakaguchi", None),
    ("c4e3f5e6f4c5d6c6f7g5g6", "Berner", None),
    ("c4e3f6b4", "Bent Ganglion", None),
    ("c4e3f6e6f5", "Tiger", Some("虎")),
    ("c4e3f6e6f5c5c3", "Stephenson", None),
    ("c4e3f6e6f5c5c3b4", "No-Kung", None),
    (
        "c4e3f6e6f5c5c3b4d6c6b5a6b6c7",
        "No-Kung (Continuation)",
        None,
    ),
    ("c4e3f6e6f5c5c3c6", "Comp'Oth", None),
    (
        "c4e3f6e6f5c5c3c6d3d2e2b3c1c2b4a3a5b5a6a4a2",
        "F.A.T. Draw",
        None,
    ),
    ("c4e3f6e6f5c5c3c6d6", "Lightning Bolt", None),
    ("c4e3f6e6f5c5c3g5", "Kung", None),
    ("c4e3f6e6f5c5d3", "Leader's Tiger", None),
    ("c4e3f6e6f5c5d6", "Brightwell", None),
    ("c4e3f6e6f5c5f4g5g4f3c6d3d6", "Ishii", None),
    (
        "c4e3f6e6f5c5f4g5g4f3c6d3d6b3c3b4e2b6",
        "Mainline Tiger",
        None,
    ),
    ("c4e3f6e6f5c5f4g6f7", "Rose-Bill", None),
    ("c4e3f6e6f5c5f4g6f7d3", "Tamenori", None),
    ("c4e3f6e6f5c5f4g6f7g5", "Central Rose-Bill/Dead Draw", None),
    ("c4e3f6e6f5g6", "Aubrey/Tanaka", None),
    ("c4e3f6e6f5g6e7c5", "Aubrey (Feldborg Continuation)", None),
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

/// 棋譜（"f5d6c3..."、パスは含めない）に一致する、いちばん長い定石の表示名（例: "虎（Tiger）"）。
/// 定石から外れた後も、外れる前に通った最も長い定石を返す。当てはまらなければ None。
pub fn identify(transcript: &str) -> Option<String> {
    let moves = parse_transcript(transcript)?;
    let first = *moves.first()?;
    let c4 = parse_square(b"c4").unwrap();
    // 開始局面を変えない対称変換のうち、初手を c4 に移すもの
    let s = (0..8u8).find(|&s| {
        transform(START.0, s) == START.0
            && transform(START.1, s) == START.1
            && transform(first, s) == c4
    })?;
    let normalized: Vec<u64> = moves.iter().map(|&m| transform(m, s)).collect();
    let mut best: Option<(usize, &str, Option<&str>)> = None;
    for (seq, name, ja) in OPENINGS {
        let line = parse_transcript(seq).expect("表の手順は正しい");
        if line.len() <= normalized.len()
            && normalized[..line.len()] == line[..]
            && best.is_none_or(|b| line.len() > b.0)
        {
            best = Some((line.len(), name, ja));
        }
    }
    best.map(|(_, name, ja)| match ja {
        Some(ja) => format!("{ja}（{name}）"),
        None => name.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tiger_in_every_orientation() {
        for t in ["f5d6c3d3c4", "c4e3f6e6f5", "d3c5f6f5e6", "e6f4c3c4d3"] {
            assert_eq!(identify(t).as_deref(), Some("虎（Tiger）"));
        }
    }

    #[test]
    fn short_or_invalid() {
        assert_eq!(identify(""), None);
        assert_eq!(identify("f5"), None);
        assert_eq!(identify("a1"), None);
        assert_eq!(identify("zz"), None);
        assert_eq!(identify("f5d"), None);
        assert_eq!(
            identify("f5d6").as_deref(),
            Some("縦取り（Perpendicular Opening）")
        );
    }
}
