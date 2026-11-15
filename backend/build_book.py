"""Build the opening book (opening_book.txt).

Approach:
- Every position up to --full-plies is included (so random openings in arena.py and any human
  opening are covered).
- Beyond that the tree is expanded differently depending on who is to move:
    the AI to move       -> follow only the deeply searched best move (the AI plays by the book)
    the opponent to move -> follow the top --replies moves of a shallow search (any reply is possible)
  The tree is expanded for both roles, so the AI may play either color.
- Book moves come from a fixed-depth (--depth) search with no time limit, so the same settings
  always produce exactly the same file.

The computation can take hours, so finished positions are appended to a cache file and an
interrupted run resumes from where it stopped when the same command is run again.

Usage:
    python build_book.py --depth 10 --full-plies 6 --plies 10 --replies 3 -j 8
"""

import argparse
import os
import time
from dataclasses import dataclass
from multiprocessing import Pool

from opening_book import OpeningBook, canonical, parse_square, square_name
from strong_ai import StrongAI, flips, legal_moves

START = (0x0000000810000000, 0x0000001008000000)

# Role at a position. BOOK: the side to move is the AI using the book; ANY: it is the opponent (any move)
BOOK = 1
ANY = 2


@dataclass(frozen=True)
class Settings:
    depth: int = 10
    full_plies: int = 6
    plies: int = 10
    replies: int = 3
    rank_depth: int = 4
    # pattern-evaluation weights used at the leaves (None = linear evaluation)
    patterns: str | None = None


def _moves(m):
    out = []
    while m:
        x = m & -m
        m ^= x
        out.append(x)
    return out


def _deep_search(args):
    """Search (P, O) to a fixed depth and return (P, O, best move, score) (runs in a worker process)."""
    P, O, depth, patterns = args
    ai = StrongAI(1, time_limit=float("inf"), max_depth=depth, patterns=patterns)
    move, score, _ = ai.search(P, O)
    # Round to the precision written to the cache, so a run resumed from the cache produces
    # exactly the same output file as a run from scratch
    return P, O, move, round(score, 4)


def _rank_replies(args):
    """Shallow-search the moves of (P, O) and return them best first (runs in a worker process)."""
    P, O, depth, patterns = args
    ai = StrongAI(1, time_limit=float("inf"), max_depth=depth, patterns=patterns)
    return P, O, [x for x, _ in ai.score_moves(P, O, depth)]


class _Cache:
    """Append-only file of finished positions, read back when resuming."""

    def __init__(self, path):
        self.path = path
        self.results = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 5:  # drop a last line that was cut off mid-write
                        p, o, move, score, depth = parts
                        self.results[(int(p, 16), int(o, 16), int(depth))] = (parse_square(move), float(score))
        self._file = open(path, "a", encoding="utf-8") if path else None

    def get(self, P, O, depth):
        return self.results.get((P, O, depth))

    def put(self, P, O, depth, move, score):
        self.results[(P, O, depth)] = (move, score)
        if self._file:
            self._file.write(f"{P:016x} {O:016x} {square_name(move)} {score:.4f} {depth}\n")
            self._file.flush()

    def close(self):
        if self._file:
            self._file.close()


def _children(P, O, moves):
    """For each move x of (P, O), return (x, next side to move, its opponent)."""
    out = []
    for x in moves:
        f = flips(P, O, x)
        out.append((x, O ^ f, P | x | f))
    return out


def _expand(level, full, best, ranked, replies):
    """Compute the positions one ply further and their roles.

    level:  canonical position -> roles (bitwise OR of BOOK / ANY)
    best:   BOOK position -> (best move, score)
    ranked: ANY position -> moves best first (unused when `full`)
    """
    nxt = {}

    def add(P, O, roles):
        key = canonical(P, O)[:2]
        nxt[key] = nxt.get(key, 0) | roles

    for (P, O), roles in level.items():
        moves = legal_moves(P, O)
        if not moves:
            if legal_moves(O, P):
                # pass: only the side to move changes, so the roles swap
                add(O, P, (BOOK if roles & ANY else 0) | (ANY if roles & BOOK else 0))
            continue
        if full:
            for _, nP, nO in _children(P, O, _moves(moves)):
                add(nP, nO, BOOK | ANY)
            continue
        if roles & BOOK:
            move = best[(P, O)][0] if (P, O) in best else moves  # positions with a single legal move are not stored
            for _, nP, nO in _children(P, O, [move]):
                add(nP, nO, ANY)
        if roles & ANY:
            for _, nP, nO in _children(P, O, ranked[(P, O)][:replies]):
                add(nP, nO, BOOK)
    return nxt


def build(settings, processes=None, cache_path=None, log=print):
    """Build the book for the given settings and return an OpeningBook."""
    cache = _Cache(cache_path)
    book = OpeningBook()
    stats = {"searched": 0, "cached": 0}
    start = time.time()

    # level: canonical position -> roles (bitwise OR of BOOK / ANY)
    cP, cO, _ = canonical(*START)
    level = {(cP, cO): BOOK | ANY}
    try:
        with Pool(processes) as pool:
            for ply in range(settings.plies):
                full = ply < settings.full_plies
                need_search, need_rank = [], []
                for (P, O), roles in sorted(level.items()):
                    moves = legal_moves(P, O)
                    if not moves:
                        continue  # game over or pass
                    if roles & BOOK and moves & (moves - 1):  # no need to search a single legal move
                        need_search.append((P, O))
                    if roles & ANY and not full:
                        need_rank.append((P, O))

                best = {}
                todo = []
                for P, O in need_search:
                    hit = cache.get(P, O, settings.depth)
                    if hit:
                        best[(P, O)] = hit
                        stats["cached"] += 1
                    else:
                        todo.append((P, O, settings.depth, settings.patterns))
                for i, (P, O, move, score) in enumerate(pool.imap(_deep_search, todo, chunksize=1), 1):
                    cache.put(P, O, settings.depth, move, score)
                    best[(P, O)] = (move, score)
                    stats["searched"] += 1
                    if i % 200 == 0:
                        log(f"  ply {ply}: {i}/{len(todo)} positions searched ({time.time() - start:.0f}s)")
                for (P, O), (move, score) in best.items():
                    book.add(P, O, move, score, settings.depth)

                ranked = {}
                if need_rank:
                    jobs = [(P, O, settings.rank_depth, settings.patterns) for P, O in need_rank]
                    for P, O, order in pool.imap(_rank_replies, jobs, chunksize=4):
                        ranked[(P, O)] = order

                level = _expand(level, full, best, ranked, settings.replies)
                log(
                    f"ply {ply}: book {len(book)} positions (searched {stats['searched']}, cached {stats['cached']})"
                    f", next level {len(level)} ({time.time() - start:.0f}s)"
                )
    finally:
        cache.close()
    return book


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--depth", type=int, default=Settings.depth, help="search depth for book moves")
    parser.add_argument("--full-plies", type=int, default=Settings.full_plies, help="include every position up to this ply")
    parser.add_argument("--plies", type=int, default=Settings.plies, help="build the book up to this ply")
    parser.add_argument("--replies", type=int, default=Settings.replies, help="opponent replies to follow beyond --full-plies")
    parser.add_argument("--rank-depth", type=int, default=Settings.rank_depth, help="search depth for ranking opponent replies")
    parser.add_argument("--patterns", help="pattern-evaluation weights for the leaves (default: linear evaluation)")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "opening_book.txt"))
    parser.add_argument("--cache", help="file for partial results (default: <out>.cache)")
    parser.add_argument("-j", "--processes", type=int, default=None)
    args = parser.parse_args()

    settings = Settings(args.depth, args.full_plies, args.plies, args.replies, args.rank_depth, args.patterns)
    # keep partial results per evaluation function so results never mix
    tag = "" if not args.patterns else "." + os.path.splitext(os.path.basename(args.patterns))[0]
    t0 = time.time()
    book = build(settings, args.processes, args.cache or args.out + tag + ".cache")
    header = [
        "generated by build_book.py "
        f"--depth {settings.depth} --full-plies {settings.full_plies} --plies {settings.plies} "
        f"--replies {settings.replies} --rank-depth {settings.rank_depth}"
        + (f" --patterns {os.path.basename(settings.patterns)}" if settings.patterns else ""),
        f"{len(book)} positions",
    ]
    book.save(args.out, header)
    print(f"saved {args.out} ({len(book)} positions, {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
