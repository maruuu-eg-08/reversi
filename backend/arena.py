"""AI 同士の対戦で強さを測る（並列実行）。

同じ序盤（ランダムに数手進めた局面）から先手・後手を入れ替えて2局ずつ打つので、
先手有利や序盤の運の偏りが打ち消される。勝率には 95% 信頼区間を付ける。

例:
    python arena.py lv5:0.3 lv4 -n 100
    python arena.py lv5:0.3 lv5:0.3:coeffs=tuned.txt -n 200
    python arena.py lv5:0.3 lv5:0.3:book=off -n 200        # 定石あり vs なし
"""

import argparse
import math
import random
from multiprocessing import Pool

from ai_manager import create_ai
from bitboard import BitBoard


def make_player(spec, color):
    """'lv4', 'lv4:6'（深さ）, 'lv5:0.5'（秒）, 'lv5:0.5:coeffs=path' のような文字列から AI を作る。

    Lv.5 は既定で同梱の定石を使う。'book=off' で使わない、'book=path' で別の定石ファイルを使う。
    """
    parts = spec.split(":")
    level = parts[0].removeprefix("lv")
    opts = {}
    positional = []
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            opts[k] = v
        else:
            positional.append(p)
    if level == "5":
        from opening_book import OpeningBook, default_book
        from strong_ai import StrongAI

        coeffs = None
        if "coeffs" in opts:
            with open(opts["coeffs"]) as f:
                coeffs = [float(v) for v in f.read().split()]
        t = float(positional[0]) if positional else 1.0
        d = int(opts.get("depth", 60))
        book_opt = opts.get("book", "default")
        if book_opt == "off":
            book = None
        elif book_opt == "default":
            book = default_book()
        else:
            book = OpeningBook.load(book_opt)
        return StrongAI(color, time_limit=t, max_depth=d, eval_coeffs=coeffs, book=book)
    depth = int(positional[0]) if positional else 4
    return create_ai(level, color, depth=depth)


def random_opening(seed, n_moves):
    rng = random.Random(seed)
    b = BitBoard()
    color = 1
    for _ in range(n_moves):
        moves = b.listUp(color)
        if not moves:
            color = -color
            continue
        b.put_disc(*rng.choice(moves), color)
        color = -color
    return b.black, b.white, color


def play(spec_black, spec_white, opening):
    black, white, color = opening
    b = BitBoard()
    b.black, b.white = black, white
    players = {1: make_player(spec_black, 1), -1: make_player(spec_white, -1)}
    while b.has_valid_move(1) or b.has_valid_move(-1):
        if not b.has_valid_move(color):
            color = -color
            continue
        r, c = players[color].get_move(b)
        b.put_disc(r, c, color)
        color = -color
    return b.count_discs(1) - b.count_discs(-1)


def _job(args):
    spec_a, spec_b, opening, a_is_black = args
    if a_is_black:
        return play(spec_a, spec_b, opening)
    return -play(spec_b, spec_a, opening)


def run(spec_a, spec_b, n_openings=50, opening_moves=6, seed=0, processes=None):
    openings = [random_opening(seed * 100_000 + i, opening_moves) for i in range(n_openings)]
    jobs = [(spec_a, spec_b, op, a_black) for op in openings for a_black in (True, False)]
    with Pool(processes) as pool:
        diffs = pool.map(_job, jobs)
    wins = sum(d > 0 for d in diffs)
    losses = sum(d < 0 for d in diffs)
    draws = len(diffs) - wins - losses
    n = len(diffs)
    p = (wins + 0.5 * draws) / n
    se = math.sqrt(max(p * (1 - p), 1e-9) / n)
    return {
        "games": n,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "score": p,
        "ci95": (max(0.0, p - 1.96 * se), min(1.0, p + 1.96 * se)),
        "mean_diff": sum(diffs) / n,
        "elo": _elo(p),
    }


def _elo(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return -400 * math.log10(1 / p - 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("-n", "--openings", type=int, default=50, help="序盤の数（対局数はこの2倍）")
    parser.add_argument("--opening-moves", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-j", "--processes", type=int, default=None)
    args = parser.parse_args()
    r = run(args.a, args.b, args.openings, args.opening_moves, args.seed, args.processes)
    lo, hi = r["ci95"]
    print(f"{args.a} vs {args.b}: {r['games']}局  {r['wins']}勝 {r['losses']}敗 {r['draws']}分")
    print(f"  勝率 {r['score']:.1%} (95%CI {lo:.1%}–{hi:.1%})  平均石差 {r['mean_diff']:+.1f}  Elo差 {r['elo']:+.0f}")


if __name__ == "__main__":
    main()
