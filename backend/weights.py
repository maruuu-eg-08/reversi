"""Evaluation parameters used by the AIs (the single source of truth)."""

# Per-square weights (64 values, index row * 8 + col).
# The same table that was used when ga_trainer.py learned the evaluation coefficients.
POSITION_WEIGHTS = [
    27.87, 10.59, 27.35, 15.77, 15.77, 27.35, 10.59, 27.87,
    10.59,  4.51, 33.77, -25.49, -25.49, 33.77,  4.51, 10.59,
    27.35, 33.77,  0.61, -6.42, -6.42,  0.61, 33.77, 27.35,
    15.77, -25.49, -6.42, 25.08, 25.08, -6.42, -25.49, 15.77,
    15.77, -25.49, -6.42, 25.08, 25.08, -6.42, -25.49, 15.77,
    27.35, 33.77,  0.61, -6.42, -6.42,  0.61, 33.77, 27.35,
    10.59,  4.51, 33.77, -25.49, -25.49, 33.77,  4.51, 10.59,
    27.87, 10.59, 27.35, 15.77, 15.77, 27.35, 10.59, 27.87,
]

# Evaluation coefficients per game phase (ga_trainer.py result, best_eval_coeffs.txt).
# [opening pos, mob, disc, midgame pos, mob, disc, endgame pos, mob, disc]
EVAL_COEFFS = [
    1.11265999, 0.73565285, 0.34340917,
    1.05687437, 0.65200396, 0.43294245,
    -0.0449974, 0.53306816, 1.0032734,
]

# Weights for Level 2 (WeightedAI): an earlier GA result (best_final.txt) expanded to 64 squares.
WEIGHTED_AI_WEIGHTS = [
    50.0, 17.29, 6.81, 11.32, 11.32, 6.81, 17.29, 50.0,
    17.29, 18.43, 38.49, -28.38, -28.38, 38.49, 18.43, 17.29,
    6.81, 38.49, -17.33, -11.03, -11.03, -17.33, 38.49, 6.81,
    11.32, -28.38, -11.03, 18.70, 18.70, -11.03, -28.38, 11.32,
    11.32, -28.38, -11.03, 18.70, 18.70, -11.03, -28.38, 11.32,
    6.81, 38.49, -17.33, -11.03, -11.03, -17.33, 38.49, 6.81,
    17.29, 18.43, 38.49, -28.38, -28.38, 38.49, 18.43, 17.29,
    50.0, 17.29, 6.81, 11.32, 11.32, 6.81, 17.29, 50.0,
]

# Score given to a won/lost finished game (larger than any positional evaluation)
WIN_SCORE = 10_000

# Linear-evaluation coefficients for Lv.5 (StrongAI): [position, mobility, discs, frontier] x opening/midgame/endgame.
# Learned by tune_eval.py from 4000 self-play games, 2 iterations (the score is roughly in final-disc-difference units).
# Clearly stronger than the starting point (Lv.4 coefficients + zero frontier); see the README benchmarks.
STRONG_EVAL_COEFFS = [
    -0.0148403, -0.0521191, 4.72193, 5.18808,
    0.0284557, 1.34012, 1.2702, 1.5966,
    0.0176706, 2.25813, 0.871555, 0.799645,
]

# Starting point before training (for comparison and retraining)
STRONG_EVAL_COEFFS_INITIAL = [
    1.11265999, 0.73565285, 0.34340917, 0.0,
    1.05687437, 0.65200396, 0.43294245, 0.0,
    -0.0449974, 0.53306816, 1.0032734, 0.0,
]
