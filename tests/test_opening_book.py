import random

import pytest

from opening_book import (
    N_SYMMETRIES,
    OpeningBook,
    canonical,
    flip_vertical,
    inverse_transform,
    mirror_horizontal,
    parse_square,
    square_name,
    transform,
    transpose,
)
from strong_ai import flips, legal_moves

START = (0x0000000810000000, 0x0000001008000000)  # (黒=手番, 白)


def _naive(b, f):
    """マスごとに座標変換 f(row, col) を適用する素朴な実装（比較用）。"""
    out = 0
    for i in range(64):
        if b >> i & 1:
            r, c = f(i // 8, i % 8)
            out |= 1 << (r * 8 + c)
    return out


def _random_position(rng, plies):
    """開始局面から plies 手ランダムに進めた (手番側, 相手側)。"""
    P, O = START
    for _ in range(plies):
        moves = legal_moves(P, O)
        if not moves:
            if not legal_moves(O, P):
                break
            P, O = O, P
            continue
        choices = [1 << i for i in range(64) if moves >> i & 1]
        x = rng.choice(choices)
        f = flips(P, O, x)
        P, O = O ^ f, P | x | f
    return P, O


def _random_bits(rng):
    return rng.getrandbits(64)


@pytest.mark.parametrize(
    "fn, coord",
    [
        (flip_vertical, lambda r, c: (7 - r, c)),
        (mirror_horizontal, lambda r, c: (r, 7 - c)),
        (transpose, lambda r, c: (c, r)),
    ],
)
def test_basic_transforms_match_naive(fn, coord):
    rng = random.Random(1)
    for _ in range(200):
        b = _random_bits(rng)
        assert fn(b) == _naive(b, coord)


def test_transforms_are_eight_distinct_bijections_with_inverse():
    rng = random.Random(2)
    b = _random_bits(rng)
    images = {transform(b, s) for s in range(N_SYMMETRIES)}
    assert len(images) == 8  # ランダムな盤面なら8通りすべて異なる
    for s in range(N_SYMMETRIES):
        for _ in range(50):
            x = _random_bits(rng)
            assert transform(x, s).bit_count() == x.bit_count()
            assert inverse_transform(transform(x, s), s) == x


def test_legal_moves_commute_with_symmetry():
    """回転・反転した局面の合法手は、元の合法手を同じように回転・反転したもの。"""
    rng = random.Random(3)
    for _ in range(100):
        P, O = _random_position(rng, rng.randint(0, 40))
        for s in range(N_SYMMETRIES):
            assert legal_moves(transform(P, s), transform(O, s)) == transform(legal_moves(P, O), s)


def test_canonical_is_same_for_all_orientations():
    rng = random.Random(4)
    for _ in range(50):
        P, O = _random_position(rng, rng.randint(0, 30))
        cP, cO, s = canonical(P, O)
        assert (transform(P, s), transform(O, s)) == (cP, cO)
        for t in range(N_SYMMETRIES):
            assert canonical(transform(P, t), transform(O, t))[:2] == (cP, cO)


def test_square_names_round_trip():
    for i in range(64):
        assert parse_square(square_name(1 << i)) == 1 << i
    assert parse_square("a1") == 1
    assert parse_square("H8") == 1 << 63
    for bad in ("i1", "a9", "f", "f55"):
        with pytest.raises(ValueError):
            parse_square(bad)


def test_probe_returns_move_in_queried_orientation():
    """ある向きで登録した手が、回転・反転した局面からも正しい向きで引ける。"""
    rng = random.Random(5)
    book = OpeningBook()
    P, O = _random_position(rng, 10)
    moves = legal_moves(P, O)
    move = 1 << (moves.bit_length() - 1)
    book.add(P, O, move, 3.5, 10)
    assert len(book) == 1
    for s in range(N_SYMMETRIES):
        hit = book.probe(transform(P, s), transform(O, s))
        assert hit is not None
        assert hit.move == transform(move, s)
        assert (hit.score, hit.depth) == (3.5, 10)
        assert (transform(P, s), transform(O, s)) in book


def test_probe_misses_unknown_position():
    book = OpeningBook()
    book.add(*START, parse_square("f5"), 0.0, 8)
    P, O = _random_position(random.Random(6), 12)
    assert book.probe(P, O) is None


def test_add_rejects_illegal_move():
    book = OpeningBook()
    with pytest.raises(ValueError):
        book.add(*START, parse_square("a1"), 0.0, 1)


def test_save_and_load_round_trip(tmp_path):
    rng = random.Random(7)
    book = OpeningBook()
    for _ in range(30):
        P, O = _random_position(rng, rng.randint(0, 20))
        moves = legal_moves(P, O)
        if moves:
            book.add(P, O, moves & -moves, rng.uniform(-20, 20), rng.randint(1, 12))
    path = tmp_path / "book.txt"
    book.save(path, header=["test"])
    loaded = OpeningBook.load(path)
    assert len(loaded) == len(book)
    for (P, O, e), (P2, O2, e2) in zip(book.items(), loaded.items(), strict=True):
        assert (P, O, e.move, e.depth) == (P2, O2, e2.move, e2.depth)
        assert e2.score == pytest.approx(e.score, abs=0.005)


def test_load_reports_line_number_on_corrupt_file(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_text("# comment\n0000000810000000 0000001008000000 z9 0 1\n")
    with pytest.raises(ValueError, match=":2:"):
        OpeningBook.load(path)


def test_probe_ignores_illegal_entry_from_file(tmp_path):
    """ファイルが壊れていて合法手でない手が書かれていても、それを返さない。"""
    cP, cO, _ = canonical(*START)
    path = tmp_path / "book.txt"
    path.write_text(f"{cP:016x} {cO:016x} a1 0.00 1\n")
    assert OpeningBook.load(path).probe(*START) is None
