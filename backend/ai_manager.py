from alphabeta_ai import AlphaBetaAI
from minimax import MinimaxAI
from random_ai import RandomAI
from weighted_ai import WeightedAI


def create_ai(level, color, weights=None, eval_coeffs=None, depth=4):
    """レベル("1"〜"4")に対応する AI を作る。"""
    level = str(level)
    if level == "1":
        return RandomAI(color)
    elif level == "2":
        return WeightedAI(color)
    elif level == "3":
        return MinimaxAI(color)
    elif level == "4":
        return AlphaBetaAI(color, max_depth=depth, weights=weights, eval_coeffs=eval_coeffs)
    else:
        return RandomAI(color)
