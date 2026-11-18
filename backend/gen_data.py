"""Generate pattern-evaluation training data by self-play (requires the Rust engine).

See backend_rust/src/selfplay.rs for how games are played and labeled.
The file is a header (the settings as JSON) followed by 22-byte records, one per position.
If interrupted, running the same command again continues where it stopped (the last, partially
written game is regenerated).

By default both sides search with the linear evaluation. --patterns auto (the bundled weights) or
--patterns <file> makes them search with pattern evaluation instead, as Lv.5 does; the header then
records the SHA-256 of the weights file, so resuming with other weights is refused.

Usage:
    python gen_data.py --games 50000 --out ../data/selfplay.bin
    python gen_data.py --games 200000 --patterns auto --seed 1 --out ../data/selfplay-gen2.bin
"""

import argparse
import hashlib
import json
import os
import struct
import time

from strong_ai import DEFAULT_PATTERNS, _native
from weights import POSITION_WEIGHTS, STRONG_EVAL_COEFFS

MAGIC = b"RVDAT\x01"
RECORD_SIZE = 22
RECORD = struct.Struct("<QQbBI")  # player, opponent, final disc difference, ply, game number
assert RECORD.size == RECORD_SIZE


def write_header(f, params):
    body = json.dumps(params, sort_keys=True).encode()
    f.write(MAGIC + struct.pack("<I", len(body)) + body)


def read_header(f):
    """Return (settings, header length)."""
    if f.read(len(MAGIC)) != MAGIC:
        raise ValueError("not a self-play data file")
    (n,) = struct.unpack("<I", f.read(4))
    return json.loads(f.read(n)), len(MAGIC) + 4 + n


def read_records(path):
    """Return (settings, [(player, opponent, final disc difference, ply, game), ...])."""
    with open(path, "rb") as f:
        params, _ = read_header(f)
        data = f.read()
    if len(data) % RECORD_SIZE:
        raise ValueError(f"{path}: truncated record")
    return params, list(RECORD.iter_unpack(data))


def _resume_point(path, params):
    """Find where to resume an existing file, dropping a partially written game; return the next game number."""
    with open(path, "rb") as f:
        old, header_len = read_header(f)
    if old != params:
        raise SystemExit(f"{path} was generated with different settings; choose another file name:\n  {old}")
    size = os.path.getsize(path)
    n = (size - header_len) // RECORD_SIZE
    if n == 0:
        os.truncate(path, header_len)
        return 0
    with open(path, "rb") as f:
        f.seek(header_len + (n - 1) * RECORD_SIZE)
        last_game = RECORD.unpack(f.read(RECORD_SIZE))[4]
        # the last game may be incomplete, so go back to its first record
        lo, hi = 0, n - 1
        while lo < hi:
            mid = (lo + hi) // 2
            f.seek(header_len + mid * RECORD_SIZE)
            if RECORD.unpack(f.read(RECORD_SIZE))[4] < last_game:
                lo = mid + 1
            else:
                hi = mid
    os.truncate(path, header_len + lo * RECORD_SIZE)
    return last_game


def generate(
    out, games, depth=6, random_min=8, random_max=20, solve_empties=14, seed=0, threads=None, batch=500, patterns=None, log=print
):
    """patterns: None (linear evaluation), "auto" (the bundled weights) or the path of a weights file."""
    if _native is None:
        raise SystemExit("the Rust engine is required: pip install ./backend_rust")
    if patterns == "auto":
        patterns = DEFAULT_PATTERNS
    params = {
        "games": games,
        "depth": depth,
        "random_min": random_min,
        "random_max": random_max,
        "solve_empties": solve_empties,
        "seed": seed,
        "eval_coeffs": list(STRONG_EVAL_COEFFS),
    }
    if patterns is not None:
        with open(patterns, "rb") as f:
            params["patterns_sha256"] = hashlib.sha256(f.read()).hexdigest()
    threads = threads or os.cpu_count() or 1
    start_game = 0
    if os.path.exists(out) and os.path.getsize(out) > 0:
        start_game = _resume_point(out, params)
        log(f"resuming {out} from game {start_game}")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "wb") as f:
            write_header(f, params)

    with open(out, "rb") as f:
        _, header_len = read_header(f)
    t0 = time.time()
    with open(out, "ab") as f:
        for first in range(start_game, games, batch):
            count = min(batch, games - first)
            data = _native.generate_games(
                first, count, seed, depth, random_min, random_max, solve_empties,
                list(STRONG_EVAL_COEFFS), list(POSITION_WEIGHTS), threads, patterns,
            )  # fmt: skip
            f.write(data)
            f.flush()
            done = first + count
            elapsed = time.time() - t0
            rate = (done - start_game) / elapsed
            log(
                f"{done}/{games} games ({(os.path.getsize(out) - header_len) // RECORD_SIZE:,} positions)"
                f" {rate:.1f} games/s, about {(games - done) / rate / 60:.1f} min left"
            )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=50_000)
    parser.add_argument("--depth", type=int, default=6, help="midgame search depth")
    parser.add_argument("--random-min", type=int, default=8, help="minimum number of random opening moves")
    parser.add_argument("--random-max", type=int, default=20, help="maximum number of random opening moves")
    parser.add_argument("--solve-empties", type=int, default=14, help="solve exactly from this many empty squares")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-j", "--threads", type=int, default=None)
    parser.add_argument("--batch", type=int, default=500, help="write to the file every this many games")
    parser.add_argument("--patterns", default=None, help="search with pattern evaluation: 'auto' (bundled weights) or a weights file")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "selfplay.bin"))
    a = parser.parse_args()
    generate(a.out, a.games, a.depth, a.random_min, a.random_max, a.solve_empties, a.seed, a.threads, a.batch, a.patterns)


if __name__ == "__main__":
    main()
