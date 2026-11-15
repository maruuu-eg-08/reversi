"""Learn the Lv.5 linear-evaluation coefficients from self-play games by linear regression.

The evaluation is a linear sum of features times coefficients, so fitting
  features of each position -> final disc difference of that game (for the side to move)
with least squares gives the coefficients for the opening, midgame and endgame directly.
Cheaper and more stable than the GA (ga_trainer.py).

Usage:
    python tune_eval.py --games 3000 --out tuned_coeffs.txt
    python arena.py lv5:0.1:coeffs=tuned_coeffs.txt lv5:0.1 -n 100   # check that it got stronger
"""

import argparse
import random
import time
from multiprocessing import Pool

import numpy as np

from strong_ai import MASK64, N_FEATURES, StrongAI, flips, legal_moves, neighbors

PHASES = ("opening", "midgame", "endgame")


def phase_of(n_empty):
    if n_empty >= 45:
        return 0
    if n_empty >= 15:
        return 1
    return 2


def features(ai, P, O):
    """The same features as StrongAI.evaluate (from the point of view of P)."""
    empty = ~(P | O) & MASK64
    adj = neighbors(empty)
    return (
        ai._pos(P) - ai._pos(O),
        legal_moves(P, O).bit_count() - legal_moves(O, P).bit_count(),
        P.bit_count() - O.bit_count(),
        (O & adj).bit_count() - (P & adj).bit_count(),
    )


def self_play(args):
    """Play one game and return [(phase, features, final disc difference for the side to move)]."""
    seed, depth, random_moves, epsilon, coeffs = args
    rng = random.Random(seed)
    ai = StrongAI(1, time_limit=1e9, max_depth=depth, eval_coeffs=coeffs)
    P, O = 0x0000000810000000, 0x0000001008000000  # black (to move), white
    sign = 1  # 1 if P is black
    records = []
    ply = 0
    while True:
        moves = legal_moves(P, O)
        if not moves:
            if not legal_moves(O, P):
                break
            P, O, sign = O, P, -sign
            continue
        n_empty = 64 - (P | O).bit_count()
        if ply >= random_moves:
            records.append((phase_of(n_empty), features(ai, P, O), sign))
        if ply < random_moves or rng.random() < epsilon:
            # random opening moves plus occasional random moves keep the positions diverse
            lst = []
            m = moves
            while m:
                x = m & -m
                m ^= x
                lst.append(x)
            x = rng.choice(lst)
        else:
            x, _, _ = ai.search(P, O)
        f = flips(P, O, x)
        P, O = O ^ f, P | x | f
        sign = -sign
        ply += 1
    # final disc difference for black, depending on whether P is black when the loop ends
    black_diff = (P.bit_count() - O.bit_count()) * sign
    return [(ph, feat, black_diff * s) for ph, feat, s in records]


def fit(samples):
    """Fit coefficients per phase by least squares."""
    coeffs = []
    for ph in range(3):
        X = np.array([f for p, f, _ in samples if p == ph], dtype=float)
        y = np.array([t for p, _, t in samples if p == ph], dtype=float)
        w, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ w
        r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
        print(f"  {PHASES[ph]}: {len(y):6d} positions  R^2={r2:.3f}  coefficients={np.round(w, 4).tolist()}")
        coeffs.extend(w.tolist())
    assert len(coeffs) == 3 * N_FEATURES
    return coeffs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=3000)
    parser.add_argument("--depth", type=int, default=4, help="search depth in self-play")
    parser.add_argument("--random-moves", type=int, default=6, help="number of random opening moves")
    parser.add_argument("--epsilon", type=float, default=0.05, help="probability of a random move later in the game")
    parser.add_argument("--coeffs", help="coefficients file for self-play (default: current coefficients)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="tuned_coeffs.txt")
    parser.add_argument("-j", "--processes", type=int, default=None)
    args = parser.parse_args()

    coeffs = None
    if args.coeffs:
        with open(args.coeffs) as f:
            coeffs = [float(v) for v in f.read().split()]

    start = time.time()
    jobs = [(args.seed * 1_000_000 + i, args.depth, args.random_moves, args.epsilon, coeffs) for i in range(args.games)]
    samples = []
    with Pool(args.processes) as pool:
        for i, recs in enumerate(pool.imap_unordered(self_play, jobs, chunksize=8), 1):
            samples.extend(recs)
            if i % 500 == 0:
                print(f"{i}/{args.games} games ({time.time() - start:.0f}s)")
    print(f"self-play: {args.games} games, {len(samples)} positions ({time.time() - start:.0f}s)")

    tuned = fit(samples)
    np.savetxt(args.out, tuned)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
