from alphabeta_ai import AlphaBetaAI
from minimax import MinimaxAI
from opening_book import default_book
from random_ai import RandomAI
from strong_ai import StrongAI
from weighted_ai import WeightedAI


def create_ai(level, color, weights=None, eval_coeffs=None, depth=4, time_limit=1.0, use_book=True):
    """Create the AI for a level ("1" to "5").

    Lv.5 moves within time_limit seconds and uses the opening book; with the Rust engine it uses pattern evaluation.
    """
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
        return StrongAI(color, time_limit=time_limit, book=default_book() if use_book else None, patterns="auto")
    else:
        return RandomAI(color)
