import pytest

from opening_book import parse_square, transform
from openings import _START_SYMMETRIES, OPENINGS, identify, replay


def test_all_named_openings_are_legal_sequences():
    for op in OPENINGS:
        replay(op.moves)  # 不正な手があれば ValueError


def test_openings_are_unique():
    seqs = [op.moves for op in OPENINGS]
    assert len(seqs) == len(set(seqs)) == 77


def test_replay_rejects_illegal_move():
    with pytest.raises(ValueError):
        replay([parse_square("a1")])


@pytest.mark.parametrize(
    "transcript",
    [
        "f5d6c3d3c4",  # 一般的な f5 始まりの表記
        "c4e3f6e6f5",  # リストと同じ向き
        "d3c5f6f5e6",
        "e6f4c3c4d3",
    ],
)
def test_tiger_is_recognized_in_every_orientation(transcript):
    moves = [transcript[i : i + 2] for i in range(0, len(transcript), 2)]
    op = identify(moves)
    assert op is not None and op.name == "Tiger"
    assert op.display_name == "虎（Tiger）"


def test_longest_matching_opening_wins():
    # 虎（c4e3f6e6f5）の続き Leader's Tiger（+ c5 d3）。どの向きで打っても長い方が選ばれる
    leaders = next(op for op in OPENINGS if op.name == "Leader's Tiger").moves
    for s in _START_SYMMETRIES:
        assert identify([transform(m, s) for m in leaders]).name == "Leader's Tiger"
        assert identify([transform(m, s) for m in leaders[:6]]).name == "Tiger"


def test_keeps_last_opening_after_leaving_book():
    # 虎のあと、リストにない手（a1 ではなく合法な別の手）に進んでも「虎」のまま
    assert identify(["f5", "d6", "c3", "d3", "c4", "b4"]).name == "Tiger"


def test_short_or_unknown_transcripts():
    assert identify([]) is None
    assert identify(["f5"]) is None  # 1手目だけでは定石名はない
    assert identify(["f5", "d6"]).name == "Perpendicular Opening"
    assert identify(["f5", "f6"]).name == "Diagonal Opening"
    assert identify(["f5", "f4"]).name == "Parallel Opening"
    assert identify(["a1"]) is None  # 初手として不正
