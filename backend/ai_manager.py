from alphabeta_ai import AlphaBetaAI
from minimax import MinimaxAI
from opening_book import default_book
from random_ai import RandomAI
from strong_ai import StrongAI
from weighted_ai import WeightedAI


def create_ai(level, color, weights=None, eval_coeffs=None, depth=4, time_limit=1.0, use_book=True):
    """レベル("1"〜"5")に対応する AI を作る。Lv.5 は time_limit 秒以内に手を返し、序盤は定石を使う。"""
    level = str(level)
    if level == "1":
        return RandomAI(color)
    elif level == "2":
        return WeightedAI(color)
    elif level == "3":
        return MinimaxAI(color)
    elif level == "4":
        return AlphaBetaAI(color, max_depth=depth, weights=weights, eval_coeffs=eval_coeffs)
    elif level == "5":
        return StrongAI(color, time_limit=time_limit, book=default_book() if use_book else None)
    else:
        return RandomAI(color)
