"""Compare opening-book moves with moves from a short search without the book.

On the same random openings as arena.py, compare
  - the move Lv.5 picks in time_limit seconds (without the book), and
  - the book move (best move of a depth-10 search),
measuring how often they agree and, when they differ, how much worse the short-search move is
according to a deep search. This shows how much the book changes move choice, more cheaply than games.

Usage:
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
    if not moves & (moves - 1):  # nothing to compare with zero or one legal move
        return None
    hit = default_book().probe(P, O)
    if hit is None:
        return None
    fast, _, depth = StrongAI(1, time_limit=time_limit).search(P, O)
    if fast == hit.move:
        return True, 0.0, depth
    # re-search the short-search move one ply deeper so both use the same depth
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
    print(f"{len(results)} positions  agree {agree} ({agree / len(results):.1%})  mean depth of the {args.time_limit}s search {depth:.1f}")
    if losses:
        print(f"different move in {len(losses)} positions; loss by deep search: mean {sum(losses) / len(losses):.2f}, max {max(losses):.2f}")


if __name__ == "__main__":
    main()
