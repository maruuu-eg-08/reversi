import random
import time

import pytest

from ai_manager import create_ai
from bitboard import BitBoard
from strong_ai import StrongAI, flips, legal_moves


def random_position(seed, n_moves):
    rng = random.Random(seed)
    b = BitBoard()
    color = 1
    for _ in range(n_moves):
        moves = b.listUp(color)
        if not moves:
            color = -color
            if not b.listUp(color):
                break
            continue
        b.put_disc(*rng.choice(moves), color)
        color = -color
    return b, color


def side(b, color):
    return (b.black, b.white) if color == 1 else (b.white, b.black)


def test_fast_move_generation_matches_bitboard():
    rng = random.Random(7)
    for _ in range(100):
        b = BitBoard()
        color = 1
        while b.has_valid_move(1) or b.has_valid_move(-1):
            P, O = side(b, color)
            assert legal_moves(P, O) == b.get_legal_board(color)
            moves = b.listUp(color)
            if not moves:
                color = -color
                continue
            r, c = rng.choice(moves)
            assert flips(P, O, 1 << (r * 8 + c)) == b.get_flip_mask(r, c, color)
            b.put_disc(r, c, color)
            color = -color


def brute_force(P, O, passed=False):
    """枝刈りなしで終局まで全探索した、手番側から見た最終評価。"""
    moves = legal_moves(P, O)
    if not moves:
        if passed:
            return StrongAI.final_score(O, P) * -1
        return -brute_force(O, P, True)
    best = -float("inf")
    while moves:
        x = moves & -moves
        moves ^= x
        f = flips(P, O, x)
        best = max(best, -brute_force(O ^ f, P | x | f))
    return best


@pytest.mark.parametrize("seed", range(6))
def test_endgame_solver_is_exact(seed):
    # 残り 8〜9 マス程度の局面で、完全読みの結果が全探索と一致することを確認する
    b, color = random_position(1000 + seed, 52)
    P, O = side(b, color)
    if not legal_moves(P, O):
        pytest.skip("手番側に合法手がない局面")
    ai = StrongAI(color, time_limit=30)
    move, score, _ = ai.search(P, O)
    assert ai.solved
    assert score == brute_force(P, O)
    # 選んだ手を打った後の局面も、その評価値どおりになっている
    f = flips(P, O, move)
    assert -brute_force(O ^ f, P | move | f) == score


def test_respects_time_limit():
    b, color = random_position(3, 20)
    ai = StrongAI(color, time_limit=0.2)
    start = time.perf_counter()
    move = ai.get_move(b)
    elapsed = time.perf_counter() - start
    assert move in b.listUp(color)
    assert elapsed < 0.6
    assert ai.last_depth >= 2


def test_single_legal_move_returns_immediately():
    b = BitBoard()
    b.black, b.white = 1 << 1, 1 << 0  # 白(0,0) 黒(0,1): 白は (0,2) しか打てない
    ai = StrongAI(-1, time_limit=5)
    assert ai.get_move(b) == (0, 2)
    assert ai.nodes == 0


def test_no_legal_move_returns_none():
    b = BitBoard()
    b.black, b.white = 1 << 1, 1 << 0
    assert StrongAI(1).get_move(b) is None


@pytest.mark.parametrize("color", [1, -1])
def test_create_level5(color):
    b = BitBoard()
    if color == -1:
        b.put_disc(2, 3, 1)
    ai = create_ai("5", color, time_limit=0.1)
    assert isinstance(ai, StrongAI)
    assert ai.get_move(b) in b.listUp(color)


def test_board_is_not_modified():
    b, color = random_position(5, 30)
    before = (b.black, b.white)
    StrongAI(color, time_limit=0.1).get_move(b)
    assert (b.black, b.white) == before


# ---------- 定石 ----------
def test_book_move_is_played_without_searching():
    from opening_book import OpeningBook

    b, color = random_position(11, 12)
    P, O = side(b, color)
    # わざと最善でない手を登録し、読まずにその手を打つことを確かめる
    scored = StrongAI(color, time_limit=float("inf")).score_moves(P, O, 2)
    worst = scored[-1][0]
    book = OpeningBook()
    book.add(P, O, worst, -1.0, 7)
    ai = StrongAI(color, time_limit=1.0, book=book)
    i = worst.bit_length() - 1
    assert ai.get_move(b) == (i // 8, i % 8)
    assert ai.from_book is True
    assert ai.nodes == 0
    assert ai.last_depth == 7


def test_falls_back_to_search_outside_book():
    from opening_book import OpeningBook

    b, color = random_position(12, 20)
    ai = StrongAI(color, time_limit=0.1, book=OpeningBook())
    assert ai.get_move(b) in b.listUp(color)
    assert ai.from_book is False
    assert ai.nodes > 0


def test_score_moves_best_matches_search():
    for seed in range(5):
        b, color = random_position(seed + 30, 16)
        P, O = side(b, color)
        if legal_moves(P, O).bit_count() < 2:
            continue
        ai = StrongAI(color, time_limit=float("inf"), max_depth=3)
        scored = ai.score_moves(P, O, 3)
        _, score, _ = ai.search(P, O)
        assert scored[0][1] == pytest.approx(score)
        assert [s for _, s in scored] == sorted((s for _, s in scored), reverse=True)


def test_create_ai_level5_uses_book_by_default():
    assert create_ai("5", 1).book is not None
    assert create_ai("5", 1, use_book=False).book is None


def test_auto_patterns_follow_the_engine():
    from strong_ai import _native

    ai = create_ai("5", 1)
    if _native is None:  # ブラウザ版と同じ環境: 線形評価のまま
        assert ai.patterns_path is None
    else:
        assert ai.patterns_path is not None
