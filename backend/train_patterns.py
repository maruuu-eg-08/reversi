"""Train pattern-evaluation weights from self-play data (requires the Rust engine).

See backend_rust/src/train.rs for the method (per-stage L2-regularized least squares solved with
conjugate gradients). One game in --valid-every is held out to measure prediction accuracy, shown next
to the accuracy of the current linear evaluation. Several data files can be combined (game numbers may
overlap between files; the validation split uses the game number within each file). The weights are saved in patterns.PatternWeights
format and the per-stage results are written to <out>.json.

Usage:
    python train_patterns.py --data ../data/selfplay-200k.bin --out ../data/pattern_weights.bin
    python train_patterns.py --data ../data/selfplay-200k.bin ../data/selfplay-gen2-200k.bin --out ../data/w.bin
"""

import argparse
import json
import os
import time

from strong_ai import _native
from weights import POSITION_WEIGHTS, STRONG_EVAL_COEFFS

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def train(data, out, lam=30.0, max_iter=300, tol=1e-6, valid_every=10, threads=None):
    """data: the path of a self-play data file, or a list of paths."""
    if _native is None:
        raise SystemExit("the Rust engine is required: pip install ./backend_rust")
    data = [data] if isinstance(data, str) else list(data)
    reports = _native.train_patterns(
        data, out, lam, max_iter, tol, valid_every, threads or os.cpu_count() or 1,
        list(STRONG_EVAL_COEFFS), list(POSITION_WEIGHTS),
    )  # fmt: skip
    reports = [{k: (int(v) if k in ("stage", "n_train", "n_valid", "iterations", "clamped") else v) for k, v in r.items()} for r in reports]
    with open(out + ".json", "w") as f:
        settings = {"data": [os.path.abspath(d) for d in data], "lambda": lam, "max_iter": max_iter, "tol": tol, "valid_every": valid_every}
        json.dump({"settings": settings, "stages": reports}, f, indent=2)
    return reports


def print_table(reports):
    print("stage | empties | train positions | valid RMSE (pattern / linear) | valid R² (pattern / linear)")
    for r in reports:
        hi = 60 - 4 * r["stage"]
        lo = max(hi - 3, 0) if r["stage"] < 14 else 0
        print(
            f"{r['stage']:5d} | {lo:2d}-{hi:2d}   | {r['n_train']:15,d} |"
            f" {r['valid_rmse']:6.2f} / {r['linear_rmse']:6.2f}            |"
            f" {r['valid_r2']:5.3f} / {r['linear_r2']:5.3f}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", nargs="+", default=[os.path.join(DATA_DIR, "selfplay-200k.bin")], help="one or more data files")
    parser.add_argument("--out", default=os.path.join(DATA_DIR, "pattern_weights.bin"))
    parser.add_argument("--lambda", dest="lam", type=float, default=30.0, help="L2 regularization strength")
    parser.add_argument("--iters", type=int, default=300, help="maximum conjugate-gradient iterations")
    parser.add_argument("--tol", type=float, default=1e-6)
    parser.add_argument("--valid-every", type=int, default=10, help="hold out one game in this many for validation")
    parser.add_argument("-j", "--threads", type=int, default=None)
    a = parser.parse_args()
    t0 = time.time()
    reports = train(a.data, a.out, a.lam, a.iters, a.tol, a.valid_every, a.threads)
    print_table(reports)
    print(f"saved {a.out} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
