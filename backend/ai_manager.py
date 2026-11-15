from random_ai import RandomAI
from minimax import MinimaxAI
from weighted_ai import WeightedAI
from alphabeta_ai import AlphaBetaAI

# 🌟 eval_coeffs=None を追加
def create_ai(level, color, weights=None, eval_coeffs=None):

    if level == "1":
        return RandomAI(color)
    elif level == "2":
        return WeightedAI(color)
    elif level == "3":
        return MinimaxAI(color)
    elif level == '4':
        # 🌟 AlphaBetaAI に eval_coeffs を渡す
        return AlphaBetaAI(color, max_depth=4, weights=weights, eval_coeffs=eval_coeffs)
    else:
        return RandomAI(color)