"""定石の手と、定石なしで短時間読んだ手を比べる。

arena.py と同じ「ランダムに数手進めた序盤局面」を作り、
  - Lv.5 が time_limit 秒で選ぶ手（定石なし）
  - 定石の手（深さ10で読んだ最善手）
が一致する割合と、違う場合に深く読むとどれだけ損な手か（評価値の差）を測る。
対局の勝敗より少ない計算で、定石が手の選び方をどれだけ変えるかが分かる。

使い方:
    python evaluate_book.py -n 400 --time-limit 0.3
"""

import argparse
from multiprocessing import Pool

from arena import random_opening
from opening_book import default_book
from strong_ai import StrongAI, flips, legal_moves


def _compare(args):
    seed, opening_moves, time_limit = args
    black, white, color = random_opening(seed, opening_moves)
    P, O = (black, white) if color == 1 else (white, black)
    moves = legal_moves(P, O)
    if not moves & (moves - 1):  # 合法手が0か1つなら比べる意味がない
        return None
    hit = default_book().probe(P, O)
    if hit is None:
        return None
    fast, _, depth = StrongAI(1, time_limit=time_limit).search(P, O)
    if fast == hit.move:
        return True, 0.0, depth
    # 短時間の手を、定石と同じ深さになるよう1手進めた局面から読み直す
    f = flips(P, O, fast)
    _, child, _ = StrongAI(1, time_limit=float("inf"), max_depth=hit.depth - 1).search(O ^ f, P | fast | f)
    return False, hit.score + child, depth


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--positions", type=int, default=400)
    parser.add_argument("--opening-moves", type=int, default=6)
    parser.add_argument("--time-limit", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-j", "--processes", type=int, default=None)
    args = parser.parse_args()

    jobs = [(args.seed * 100_000 + i, args.opening_moves, args.time_limit) for i in range(args.positions)]
    with Pool(args.processes) as pool:
        results = [r for r in pool.map(_compare, jobs) if r is not None]
    agree = sum(r[0] for r in results)
    losses = [r[1] for r in results if not r[0]]
    depth = sum(r[2] for r in results) / len(results)
    print(f"{len(results)} 局面  一致 {agree} ({agree / len(results):.1%})  {args.time_limit}秒探索の平均の深さ {depth:.1f}")
    if losses:
        print(f"違う手 {len(losses)} 局面  深く読んだ評価での損失: 平均 {sum(losses) / len(losses):.2f}, 最大 {max(losses):.2f}")


if __name__ == "__main__":
    main()
