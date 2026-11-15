"""ブラウザ版（Pyodide）から呼び出すための薄い窓口。

JavaScript とのやり取りは JSON 文字列で行う。
64ビットの盤面は JavaScript の Number では精度が足りないため、10進文字列で受け渡す。
"""

import json
import time

from ai_manager import create_ai
from alphabeta_ai import AlphaBetaAI
from bitboard import BitBoard
from weights import WIN_SCORE


def _board(black, white):
    b = BitBoard()
    b.black = int(black)
    b.white = int(white)
    return b


def _state(b, color, flipped=0):
    return {
        "black": str(b.black),
        "white": str(b.white),
        "color": color,
        "blackCount": b.count_discs(1),
        "whiteCount": b.count_discs(-1),
        "legal": [list(m) for m in b.listUp(color)],
        "opponentHasMove": b.has_valid_move(-color),
        "flipped": [[i // 8, i % 8] for i in range(64) if (flipped >> i) & 1],
    }


def new_game():
    return json.dumps(_state(BitBoard(), 1))


def get_state(black, white, color):
    return json.dumps(_state(_board(black, white), color))


def play(black, white, color, row, col):
    """color が (row, col) に打った後の盤面を返す。手番は打った側のまま返すので、交代は呼び出し側で行う。"""
    b = _board(black, white)
    flipped = b.get_flip_mask(row, col, color)
    if not b.put_disc(row, col, color):
        return json.dumps({"error": "illegal move"})
    return json.dumps(_state(b, -color, flipped))


def ai_move(black, white, color, level, depth, time_limit=1.0):
    b = _board(black, white)
    ai = create_ai(str(level), color, depth=depth, time_limit=time_limit)
    start = time.perf_counter()
    move = ai.get_move(b)
    elapsed = time.perf_counter() - start
    return json.dumps({
        "move": list(move) if move else None,
        "ms": round(elapsed * 1000),
        "nodes": getattr(ai, "nodes", None),
        # Lv.4 は固定の深さ、Lv.5 は時間内に読み終えた深さ
        "depth": getattr(ai, "last_depth", getattr(ai, "depth", None)),
        "solved": getattr(ai, "solved", False),
    })


def analyze(black, white, color, depth):
    """手番側の全合法手の評価値（AlphaBetaAI 視点）を返す。"""
    b = _board(black, white)
    ai = AlphaBetaAI(color, max_depth=depth)
    start = time.perf_counter()
    results = ai.analyze(b)
    elapsed = time.perf_counter() - start
    moves = []
    for (r, c), score in results:
        if score >= WIN_SCORE:
            outcome = "win"
        elif score <= -WIN_SCORE:
            outcome = "loss"
        else:
            outcome = None
        moves.append({
            "row": r,
            "col": c,
            "score": round(score, 2),
            "outcome": outcome,
            "discDiff": int(score - WIN_SCORE) if outcome == "win" else int(score + WIN_SCORE) if outcome == "loss" else None,
        })
    return json.dumps({"moves": moves, "ms": round(elapsed * 1000), "nodes": ai.nodes, "depth": depth})
