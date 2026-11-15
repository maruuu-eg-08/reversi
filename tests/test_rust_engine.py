"""Rust 版エンジン（backend_rust/）が Python 版と同じ結果を返すことを確かめる。

固定の深さ（時間制限なし）で読めば、最善手・評価値・読んだ深さだけでなく、
探索した局面数まで一致するはず。局面数が一致するということは、手の並べ替え・置換表・枝刈りが
すべて同じ順番で動いているということ。

Rust 版をビルドしていない環境ではスキップする（CI ではビルドして実行する）。
"""

import random
import time

import pytest

reversi_engine = pytest.importorskip("reversi_engine")

from strong_ai import StrongAI, flips, legal_moves  # noqa: E402

START = (0x0000000810000000, 0x0000001008000000)
INF = float("inf")


def random_position(rng, plies):
    P, O = START
    for _ in range(plies):
        moves = legal_moves(P, O)
        if not moves:
            if not legal_moves(O, P):
                break
            P, O = O, P
            continue
        x = rng.choice([1 << i for i in range(64) if moves >> i & 1])
        f = flips(P, O, x)
        P, O = O ^ f, P | x | f
    return P, O


def pair(**kw):
    return StrongAI(1, engine="python", **kw), StrongAI(1, engine="rust", **kw)


def test_move_generation_matches():
    rng = random.Random(0)
    for _ in range(300):
        P, O = random_position(rng, rng.randint(0, 58))
        moves = legal_moves(P, O)
        assert reversi_engine.legal_moves(P, O) == moves
        for i in range(64):
            if moves >> i & 1:
                assert reversi_engine.flips(P, O, 1 << i) == flips(P, O, 1 << i)


def test_evaluation_matches_exactly():
    py, rs = pair()
    rng = random.Random(1)
    for _ in range(300):
        P, O = random_position(rng, rng.randint(0, 58))
        assert rs._native.evaluate(P, O) == py.evaluate(P, O)  # 浮動小数点数としても完全に一致


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_fixed_depth_search_matches(depth):
    rng = random.Random(100 + depth)
    for _ in range(25):
        P, O = random_position(rng, rng.randint(4, 40))
        py, rs = pair(time_limit=INF, max_depth=depth)
        assert rs.search(P, O) == py.search(P, O)
        assert (rs.nodes, rs.solved) == (py.nodes, py.solved)


def test_endgame_solve_matches():
    rng = random.Random(7)
    checked = 0
    while checked < 15:
        P, O = random_position(rng, 50)
        if legal_moves(P, O).bit_count() < 2:
            continue
        py, rs = pair(time_limit=INF)
        assert rs.search(P, O) == py.search(P, O)
        assert rs.solved and py.solved
        assert rs.nodes == py.nodes
        checked += 1


def test_custom_coefficients_and_weights_match():
    rng = random.Random(8)
    coeffs = [rng.uniform(-2, 2) for _ in range(12)]
    weights = [rng.uniform(-10, 10) for _ in range(64)]
    for _ in range(10):
        P, O = random_position(rng, rng.randint(4, 30))
        py, rs = pair(time_limit=INF, max_depth=4, eval_coeffs=coeffs, weights=weights)
        assert rs.search(P, O) == py.search(P, O)
        assert rs.nodes == py.nodes


def test_score_moves_matches():
    rng = random.Random(9)
    for _ in range(10):
        P, O = random_position(rng, rng.randint(4, 40))
        if not legal_moves(P, O):
            continue
        py, rs = pair()
        assert rs.score_moves(P, O, 3) == py.score_moves(P, O, 3)
        assert rs.nodes == py.nodes


def test_time_limited_search_returns_legal_move_in_time():
    _, rs = pair(time_limit=0.05)
    P, O = random_position(random.Random(10), 8)
    start = time.perf_counter()
    move, _, depth = rs.search(P, O)
    assert time.perf_counter() - start < 0.5
    assert move & legal_moves(P, O)
    assert depth >= 1


def test_rust_reads_deeper_in_same_time():
    """同じ時間なら、Rust 版の方が深く読める（この差が強さの差になる）。"""
    P, O = random_position(random.Random(11), 12)
    py, rs = pair(time_limit=0.2)
    py.search(P, O)
    rs.search(P, O)
    assert rs.last_depth > py.last_depth


def test_engine_selection():
    assert StrongAI(1).engine == "rust"  # インストールされていれば既定で Rust 版
    assert StrongAI(1, engine="python").engine == "python"
    with pytest.raises(ValueError):
        StrongAI(1, engine="c++")
    with pytest.raises(ValueError):
        reversi_engine.Searcher([0.0] * 11, [0.0] * 64)


# ---------- パターン評価 ----------
def test_pattern_indices_match():
    from patterns import indices

    rng = random.Random(20)
    for _ in range(200):
        P, O = random_position(rng, rng.randint(0, 58))
        assert reversi_engine.pattern_indices(P, O) == indices(P, O)


def test_pattern_evaluation_matches(tmp_path):
    from test_patterns import random_weights

    rng = random.Random(21)
    w = random_weights(rng)
    path = tmp_path / "w.bin"
    w.save(path)
    rust = reversi_engine.PatternEval(str(path))
    for _ in range(200):
        P, O = random_position(rng, rng.randint(0, 58))
        assert rust.evaluate(P, O) == w.evaluate(P, O, legal_moves(P, O), legal_moves(O, P))


def test_pattern_eval_rejects_bad_file(tmp_path):
    path = tmp_path / "bad.bin"
    path.write_bytes(b"not a weights file")
    with pytest.raises(ValueError):
        reversi_engine.PatternEval(str(path))


@pytest.fixture(scope="module")
def pattern_file(tmp_path_factory):
    from test_patterns import random_weights

    path = tmp_path_factory.mktemp("pat") / "w.bin"
    random_weights(random.Random(30)).save(path)
    return str(path)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_search_with_patterns_matches(pattern_file, depth):
    rng = random.Random(40 + depth)
    for _ in range(12):
        P, O = random_position(rng, rng.randint(4, 44))
        py, rs = pair(time_limit=INF, max_depth=depth, patterns=pattern_file)
        assert rs.search(P, O) == py.search(P, O)
        assert rs.nodes == py.nodes


def test_patterns_change_the_evaluation(pattern_file):
    P, O = random_position(random.Random(50), 20)
    linear = StrongAI(1, engine="rust")
    pat = StrongAI(1, engine="rust", patterns=pattern_file)
    assert pat._native.evaluate(P, O) == pat.evaluate(P, O)
    assert pat.evaluate(P, O) != linear.evaluate(P, O)


def test_level5_uses_bundled_patterns_with_rust():
    from ai_manager import create_ai
    from strong_ai import DEFAULT_PATTERNS

    ai = create_ai("5", 1)
    assert ai.engine == "rust" and ai.patterns_path == DEFAULT_PATTERNS
    assert StrongAI(1, engine="python", patterns="auto").patterns_path is None  # Python 版では使わない
