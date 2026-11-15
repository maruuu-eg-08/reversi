"""自己対戦の棋譜から、Lv.5 の評価関数の係数を線形回帰で学習する。

評価関数は「特徴量 × 係数」の線形和なので、
  各局面の特徴量 → その対局の最終石差（手番側から見た値）
を最小二乗法で当てはめれば、序盤・中盤・終盤それぞれの係数が直接求まる。
GA（ga_trainer.py）より計算量が少なく、結果も安定する。

使い方:
    python tune_eval.py --games 3000 --out tuned_coeffs.txt
    python arena.py lv5:0.1:coeffs=tuned_coeffs.txt lv5:0.1 -n 100   # 強くなったか検証
"""

import argparse
import random
import time
from multiprocessing import Pool

import numpy as np

from strong_ai import MASK64, N_FEATURES, StrongAI, flips, legal_moves, neighbors

PHASES = ("序盤", "中盤", "終盤")


def phase_of(n_empty):
    if n_empty >= 45:
        return 0
    if n_empty >= 15:
        return 1
    return 2


def features(ai, P, O):
    """StrongAI.evaluate と同じ特徴量（手番側 P から見た値）。"""
    empty = ~(P | O) & MASK64
    adj = neighbors(empty)
    return (
        ai._pos(P) - ai._pos(O),
        legal_moves(P, O).bit_count() - legal_moves(O, P).bit_count(),
        P.bit_count() - O.bit_count(),
        (O & adj).bit_count() - (P & adj).bit_count(),
    )


def self_play(args):
    """1局打ち、(局面の進行度, 特徴量, 手番側から見た最終石差) のリストを返す。"""
    seed, depth, random_moves, epsilon, coeffs = args
    rng = random.Random(seed)
    ai = StrongAI(1, time_limit=1e9, max_depth=depth, eval_coeffs=coeffs)
    P, O = 0x0000000810000000, 0x0000001008000000  # 黒(手番), 白
    sign = 1  # P が黒なら 1
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
            # 序盤のランダム手と、たまに混ぜるランダム手で局面の多様性を確保する
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
    # ループを抜けた時点の P が黒か白かで、黒から見た最終石差を求める
    black_diff = (P.bit_count() - O.bit_count()) * sign
    return [(ph, feat, black_diff * s) for ph, feat, s in records]


def fit(samples):
    """進行度ごとに最小二乗法で係数を求める。"""
    coeffs = []
    for ph in range(3):
        X = np.array([f for p, f, _ in samples if p == ph], dtype=float)
        y = np.array([t for p, _, t in samples if p == ph], dtype=float)
        w, *_ = np.linalg.lstsq(X, y, rcond=None)
        pred = X @ w
        r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
        print(f"  {PHASES[ph]}: {len(y):6d}局面  R^2={r2:.3f}  係数={np.round(w, 4).tolist()}")
        coeffs.extend(w.tolist())
    assert len(coeffs) == 3 * N_FEATURES
    return coeffs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=3000)
    parser.add_argument("--depth", type=int, default=4, help="自己対戦での読みの深さ")
    parser.add_argument("--random-moves", type=int, default=6, help="序盤にランダムに打つ手数")
    parser.add_argument("--epsilon", type=float, default=0.05, help="途中でランダム手を混ぜる確率")
    parser.add_argument("--coeffs", help="自己対戦に使う係数ファイル（省略時は現在の既定値）")
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
                print(f"{i}/{args.games} 局 ({time.time() - start:.0f}s)")
    print(f"自己対戦 {args.games} 局, {len(samples)} 局面 ({time.time() - start:.0f}s)")

    tuned = fit(samples)
    np.savetxt(args.out, tuned)
    print(f"保存: {args.out}")


if __name__ == "__main__":
    main()
