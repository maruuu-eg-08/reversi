"""Web版のために Rust へ移植した部分（Lv.2〜4・読み筋・定石・定石名）が Python 版と同じ結果を返すことを確かめる。

ブラウザ版は Python を使わずに Rust（WebAssembly）だけで動くので、Python 版と同じ強さ・同じ表示になるよう
この一致を保つ。Rust 版をビルドしていない環境ではスキップする。
"""

import os
import random

import pytest

reversi_engine = pytest.importorskip("reversi_engine")

import weights  # noqa: E402
from alphabeta_ai import AlphaBetaAI  # noqa: E402
from bitboard import BitBoard  # noqa: E402
from minimax import MinimaxAI  # noqa: E402
from opening_book import default_book, square_name  # noqa: E402
from openings import OPENINGS, identify  # noqa: E402
from weighted_ai import WeightedAI  # noqa: E402

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")


def random_board(rng, plies):
    """(盤面, 手番の色) を返す。"""
    b = BitBoard()
    color = 1
    for _ in range(plies):
        moves = b.listUp(color)
        if not moves:
            color = -color
            if not b.listUp(color):
                break
            continue
        b.put_disc(*rng.choice(moves), color)
        color = -color
    if not b.listUp(color) and b.listUp(-color):
        color = -color
    return b, color


def bit(rc):
    r, c = rc
    return 1 << (r * 8 + c)


def python_best_moves(ai, board, color, score_of):
    """Python の WeightedAI / MinimaxAI が「この中からランダムに選ぶ」最高点の手の一覧。"""
    best, out = -float("inf"), []
    for r, c in board.listUp(color):
        ob, ow = board.black, board.white
        board.put_disc(r, c, color)
        s = score_of(board)
        board.black, board.white = ob, ow
        if s > best:
            best, out = s, [bit((r, c))]
        elif s == best:
            out.append(bit((r, c)))
    return out


def test_parameters_match_weights_py():
    p = reversi_engine.params()
    assert p["POSITION_WEIGHTS"] == weights.POSITION_WEIGHTS
    assert p["EVAL_COEFFS"] == weights.EVAL_COEFFS
    assert p["WEIGHTED_AI_WEIGHTS"] == weights.WEIGHTED_AI_WEIGHTS
    assert p["STRONG_EVAL_COEFFS"] == weights.STRONG_EVAL_COEFFS
    assert p["MINIMAX_WEIGHTS"] == MinimaxAI(1).weights


def test_level2_best_moves_match():
    rng = random.Random(0)
    for _ in range(150):
        b, color = random_board(rng, rng.randint(0, 55))
        if not b.listUp(color):
            continue
        ai = WeightedAI(color)
        expected = python_best_moves(ai, b, color, ai.evaluate)
        assert reversi_engine.weighted_best_moves(b.black, b.white, color) == expected


def test_level3_best_moves_match():
    rng = random.Random(1)
    for _ in range(40):
        b, color = random_board(rng, rng.randint(0, 55))
        if not b.listUp(color):
            continue
        ai = MinimaxAI(color, max_depth=3)
        expected = python_best_moves(ai, b, color, lambda bd, ai=ai, color=color: ai.minimax(bd, 2, False, -color))
        assert reversi_engine.minimax_best_moves(b.black, b.white, color, 3) == expected


@pytest.mark.parametrize("depth", [1, 2, 3, 4])
def test_level4_move_and_analysis_match(depth):
    rng = random.Random(10 + depth)
    for _ in range(25):
        b, color = random_board(rng, rng.randint(0, 58))
        if not b.listUp(color):
            continue
        ai = AlphaBetaAI(color, max_depth=depth)
        move = ai.get_move(b)
        rust_move, rust_nodes = reversi_engine.alphabeta_move(b.black, b.white, color, depth)
        assert (rust_move, rust_nodes) == (bit(move), ai.nodes)

        analysis = ai.analyze(b)
        rust_analysis, rust_nodes = reversi_engine.alphabeta_analyze(b.black, b.white, color, depth)
        assert rust_analysis == [(bit(m), s) for m, s in analysis]
        assert rust_nodes == ai.nodes


def test_opening_names_match():
    rng = random.Random(2)
    transcripts = ["", "f5", "a1", "zz", "f5d"]
    for op in OPENINGS:
        transcripts.append("".join(square_name(m) for m in op.moves))
    for _ in range(300):  # ランダムな序盤（定石から外れるものも含む）
        b, color = BitBoard(), 1
        moves = []
        for _ in range(rng.randint(1, 14)):
            legal = b.listUp(color)
            if not legal:
                break
            r, c = rng.choice(legal)
            b.put_disc(r, c, color)
            moves.append(f"{'abcdefgh'[c]}{r + 1}")
            color = -color
        transcripts.append("".join(moves))
    for t in transcripts:
        pieces = [t[i : i + 2] for i in range(0, len(t), 2)]
        try:
            op = identify(pieces)
        except ValueError:
            op = None
        assert reversi_engine.opening_name(t) == (op.display_name if op else None), t


def test_opening_book_probe_matches():
    book = default_book()
    rust = reversi_engine.Book(open(os.path.join(BACKEND, "opening_book.txt")).read())
    assert len(rust) == len(book)
    rng = random.Random(3)
    for _ in range(400):
        b, color = random_board(rng, rng.randint(0, 9))
        P, O = (b.black, b.white) if color == 1 else (b.white, b.black)
        hit = book.probe(P, O)
        expected = (hit.move, hit.score, hit.depth) if hit else None
        assert rust.probe(P, O) == expected
