"""パターン評価の学習データを自己対戦で作る（Rust 版エンジンが必要）。

対局の進め方とラベルの付け方は backend_rust/src/selfplay.rs を参照。
ファイルは「ヘッダー（設定の JSON）＋ 1局面 22 バイトのレコードの並び」。
途中で止めても、同じコマンドをもう一度実行すれば続きから作る（最後の書きかけの対局は作り直す）。

使い方:
    python gen_data.py --games 50000 --out ../data/selfplay.bin
"""

import argparse
import json
import os
import struct
import time

from strong_ai import _native
from weights import POSITION_WEIGHTS, STRONG_EVAL_COEFFS

MAGIC = b"RVDAT\x01"
RECORD_SIZE = 22
RECORD = struct.Struct("<QQbBI")  # 手番側, 相手, 最終石差, 手数, ゲーム番号
assert RECORD.size == RECORD_SIZE


def write_header(f, params):
    body = json.dumps(params, sort_keys=True).encode()
    f.write(MAGIC + struct.pack("<I", len(body)) + body)


def read_header(f):
    """(設定, ヘッダーの長さ) を返す。"""
    if f.read(len(MAGIC)) != MAGIC:
        raise ValueError("自己対戦データのファイルではありません")
    (n,) = struct.unpack("<I", f.read(4))
    return json.loads(f.read(n)), len(MAGIC) + 4 + n


def read_records(path):
    """(設定, [(手番側, 相手, 最終石差, 手数, ゲーム番号), ...]) を返す。"""
    with open(path, "rb") as f:
        params, _ = read_header(f)
        data = f.read()
    if len(data) % RECORD_SIZE:
        raise ValueError(f"{path}: レコードが途中で切れています")
    return params, list(RECORD.iter_unpack(data))


def _resume_point(path, params):
    """既存のファイルから再開する位置を求め、書きかけの対局を切り捨てる。次に作るゲーム番号を返す。"""
    with open(path, "rb") as f:
        old, header_len = read_header(f)
    if old != params:
        raise SystemExit(f"{path} は別の設定で作られています。別のファイル名を指定してください:\n  {old}")
    size = os.path.getsize(path)
    n = (size - header_len) // RECORD_SIZE
    if n == 0:
        os.truncate(path, header_len)
        return 0
    with open(path, "rb") as f:
        f.seek(header_len + (n - 1) * RECORD_SIZE)
        last_game = RECORD.unpack(f.read(RECORD_SIZE))[4]
        # 最後の対局は途中までしか書かれていないかもしれないので、その対局の最初のレコードまで戻る
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


def generate(out, games, depth=6, random_min=8, random_max=20, solve_empties=14, seed=0, threads=None, batch=500, log=print):
    if _native is None:
        raise SystemExit("Rust 版エンジンが必要です: pip install ./backend_rust")
    params = {
        "games": games,
        "depth": depth,
        "random_min": random_min,
        "random_max": random_max,
        "solve_empties": solve_empties,
        "seed": seed,
        "eval_coeffs": list(STRONG_EVAL_COEFFS),
    }
    threads = threads or os.cpu_count() or 1
    start_game = 0
    if os.path.exists(out) and os.path.getsize(out) > 0:
        start_game = _resume_point(out, params)
        log(f"{out} の続きから作ります（ゲーム {start_game} から）")
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
                list(STRONG_EVAL_COEFFS), list(POSITION_WEIGHTS), threads,
            )  # fmt: skip
            f.write(data)
            f.flush()
            done = first + count
            elapsed = time.time() - t0
            rate = (done - start_game) / elapsed
            log(
                f"{done}/{games} 局（{(os.path.getsize(out) - header_len) // RECORD_SIZE:,} 局面）"
                f" {rate:.1f} 局/秒, 残り約 {(games - done) / rate / 60:.1f} 分"
            )
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--games", type=int, default=50_000)
    parser.add_argument("--depth", type=int, default=6, help="中盤の読みの深さ")
    parser.add_argument("--random-min", type=int, default=8, help="序盤のランダムな手の数（最小）")
    parser.add_argument("--random-max", type=int, default=20, help="序盤のランダムな手の数（最大）")
    parser.add_argument("--solve-empties", type=int, default=14, help="この空きマス数から終局まで読み切る")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-j", "--threads", type=int, default=None)
    parser.add_argument("--batch", type=int, default=500, help="この局数ごとにファイルへ書き出す")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "selfplay.bin"))
    a = parser.parse_args()
    generate(a.out, a.games, a.depth, a.random_min, a.random_max, a.solve_empties, a.seed, a.threads, a.batch)


if __name__ == "__main__":
    main()
