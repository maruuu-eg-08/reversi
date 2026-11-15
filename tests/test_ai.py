import pytest

from ai_manager import create_ai
from alphabeta_ai import AlphaBetaAI
from bitboard import BitBoard
from player import parse_input
from weights import WIN_SCORE


def make_board(black=(), white=()):
    b = BitBoard()
    b.black = sum(1 << (r * 8 + c) for r, c in black)
    b.white = sum(1 << (r * 8 + c) for r, c in white)
    return b


@pytest.mark.parametrize("level", ["1", "2", "3", "4"])
@pytest.mark.parametrize("color", [1, -1])
def test_ai_returns_legal_move(level, color):
    b = BitBoard()
    if color == -1:
        b.put_disc(2, 3, 1)
    ai = create_ai(level, color, depth=3)
    before = (b.black, b.white)
    move = ai.get_move(b)
    assert move in b.listUp(color)
    assert (b.black, b.white) == before  # the board is restored after the search


@pytest.mark.parametrize("level", ["1", "2", "3", "4"])
def test_ai_returns_none_without_legal_moves(level):
    b = make_board(black=[(0, 1)], white=[(0, 0)])
    assert create_ai(level, 1).get_move(b) is None


@pytest.mark.parametrize("level_black,level_white", [("4", "1"), ("1", "4")])
def test_full_game_completes(level_black, level_white):
    b = BitBoard()
    players = {1: create_ai(level_black, 1, depth=2), -1: create_ai(level_white, -1, depth=2)}
    color = 1
    for _ in range(200):
        if not b.has_valid_move(1) and not b.has_valid_move(-1):
            break
        if not b.has_valid_move(color):
            color = -color
            continue
        r, c = players[color].get_move(b)
        assert b.put_disc(r, c, color)
        color = -color
    else:
        pytest.fail("the game does not end")
    assert b.count_discs(1) + b.count_discs(-1) <= 64


def test_final_score_prefers_win_over_any_heuristic():
    ai = AlphaBetaAI(1)
    win = make_board(black=[(0, 0), (0, 1)], white=[(7, 7)])
    loss = make_board(black=[(0, 0)], white=[(7, 6), (7, 7)])
    assert ai.final_score(win) == WIN_SCORE + 1
    assert ai.final_score(loss) == -WIN_SCORE - 1
    assert ai.final_score(make_board(black=[(0, 0)], white=[(7, 7)])) == 0


def test_alphabeta_uses_final_score_at_game_over():
    """A finished game is scored by its result, not by position (it used to use the positional score only)."""
    # black has two poor squares, white one corner: white is better positionally but black wins on discs
    b = make_board(black=[(1, 3), (6, 6)], white=[(0, 0)])
    assert not b.has_valid_move(1) and not b.has_valid_move(-1)
    ai = AlphaBetaAI(1, max_depth=3)
    assert ai.evaluate(b) < 0
    score = ai.alphabeta(b, 3, -float("inf"), float("inf"), True, 1)
    assert score == WIN_SCORE + 1


def test_alphabeta_avoids_move_that_loses_immediately():
    """White to move; (0,2) captures every black disc and wins at once. Check that it is chosen."""
    b = make_board(black=[(0, 1)], white=[(0, 0)])
    ai = AlphaBetaAI(-1, max_depth=2)
    assert ai.get_move(b) == (0, 2)


@pytest.mark.parametrize(
    "text,expected",
    [("d3", (2, 3)), ("3d", (2, 3)), ("A1", (0, 0)), (" h 8 ", (7, 7)), ("z9", None), ("d", None)],
)
def test_parse_input(text, expected):
    assert parse_input(text) == expected
