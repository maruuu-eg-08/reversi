"""自己対戦データからパターン評価の重みを学習する（Rust 版エンジンが必要）。

学習の方法は backend_rust/src/train.rs を参照（段階ごとの L2 正則化つき最小二乗法を共役勾配法で解く）。
--valid-every 局に1局を学習に使わず、検証用にして予測の精度を測る。今の線形評価関数の精度も並べて表示する。
結果の重みは patterns.PatternWeights の形式で保存し、段階ごとの結果を <out>.json に書く。

使い方:
    python train_patterns.py --data ../data/selfplay-200k.bin --out ../data/pattern_weights.bin
"""

import argparse
import json
import os
import time

from strong_ai import _native
from weights import POSITION_WEIGHTS, STRONG_EVAL_COEFFS

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def train(data, out, lam=30.0, max_iter=300, tol=1e-6, valid_every=10, threads=None):
    if _native is None:
        raise SystemExit("Rust 版エンジンが必要です: pip install ./backend_rust")
    reports = _native.train_patterns(
        data, out, lam, max_iter, tol, valid_every, threads or os.cpu_count() or 1,
        list(STRONG_EVAL_COEFFS), list(POSITION_WEIGHTS),
    )  # fmt: skip
    reports = [{k: (int(v) if k in ("stage", "n_train", "n_valid", "iterations", "clamped") else v) for k, v in r.items()} for r in reports]
    with open(out + ".json", "w") as f:
        settings = {"data": os.path.abspath(data), "lambda": lam, "max_iter": max_iter, "tol": tol, "valid_every": valid_every}
        json.dump({"settings": settings, "stages": reports}, f, indent=2)
    return reports


def print_table(reports):
    print("段階 | 空きマス | 学習局面 | 検証 RMSE（パターン / 線形） | 検証 R²（パターン / 線形）")
    for r in reports:
        hi = 60 - 4 * r["stage"]
        lo = max(hi - 3, 0) if r["stage"] < 14 else 0
        print(
            f"{r['stage']:4d} | {lo:2d}〜{hi:2d}    | {r['n_train']:8,d} |"
            f" {r['valid_rmse']:6.2f} / {r['linear_rmse']:6.2f}            |"
            f" {r['valid_r2']:5.3f} / {r['linear_r2']:5.3f}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=os.path.join(DATA_DIR, "selfplay-200k.bin"))
    parser.add_argument("--out", default=os.path.join(DATA_DIR, "pattern_weights.bin"))
    parser.add_argument("--lambda", dest="lam", type=float, default=30.0, help="L2 正則化の強さ")
    parser.add_argument("--iters", type=int, default=300, help="共役勾配法の最大反復回数")
    parser.add_argument("--tol", type=float, default=1e-6)
    parser.add_argument("--valid-every", type=int, default=10, help="この局数に1局を検証用にする")
    parser.add_argument("-j", "--threads", type=int, default=None)
    a = parser.parse_args()
    t0 = time.time()
    reports = train(a.data, a.out, a.lam, a.iters, a.tol, a.valid_every, a.threads)
    print_table(reports)
    print(f"保存: {a.out}（{time.time() - t0:.0f}秒）")


if __name__ == "__main__":
    main()
