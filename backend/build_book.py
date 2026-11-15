"""序盤の定石ファイル（opening_book.txt）を作る。

方針:
- 開始局面から --full-plies 手目までは、あり得るすべての局面を登録する
  （arena.py のランダムな序盤や、人間のどんな序盤にも対応できるように）。
- それより先は「AI が打つ局面」と「相手が打つ局面」で分けて木を広げる。
    AI が打つ局面   → 深く読んだ最善手だけを先に進める（AI は定石どおりに打つので）
    相手が打つ局面 → 浅く読んで有力な上位 --replies 手を先に進める（相手は何を打つか分からないので）
  AI が黒でも白でもよいよう、両方の立場で木を広げる。
- 登録する最善手は、固定の深さ --depth で読んだ結果。時間制限を使わないので、
  同じ設定なら毎回まったく同じファイルができる。

計算は数時間かかることがあるため、読み終えた局面は随時キャッシュファイルに追記し、
中断しても同じコマンドで続きから再開できる。

使い方:
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

# 局面での立場。BOOK: 手番側が定石を使う AI、ANY: 手番側が（何を打つか分からない）相手
BOOK = 1
ANY = 2


@dataclass(frozen=True)
class Settings:
    depth: int = 10
    full_plies: int = 6
    plies: int = 10
    replies: int = 3
    rank_depth: int = 4
    # 葉の評価に使うパターン評価の重みファイル（None なら線形評価）
    patterns: str | None = None


def _moves(m):
    out = []
    while m:
        x = m & -m
        m ^= x
        out.append(x)
    return out


def _deep_search(args):
    """(P, O) を固定の深さで読み、(P, O, 最善手, 評価値) を返す（ワーカープロセスで実行）。"""
    P, O, depth, patterns = args
    ai = StrongAI(1, time_limit=float("inf"), max_depth=depth, patterns=patterns)
    move, score, _ = ai.search(P, O)
    # キャッシュに書く桁数で丸めておく。こうすると、キャッシュから再開した場合と
    # 最初から計算した場合で、出力ファイルが1文字も違わない
    return P, O, move, round(score, 4)


def _rank_replies(args):
    """(P, O) の手を浅く読み、良い順の手のリストを返す（ワーカープロセスで実行）。"""
    P, O, depth, patterns = args
    ai = StrongAI(1, time_limit=float("inf"), max_depth=depth, patterns=patterns)
    return P, O, [x for x, _ in ai.score_moves(P, O, depth)]


class _Cache:
    """読み終えた局面を1行ずつ追記するファイル。再開時に読み込む。"""

    def __init__(self, path):
        self.path = path
        self.results = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) == 5:  # 書き込み途中で中断された最後の行は捨てる
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
    """(P, O) の各手 x の後の局面 (x, 次の手番側, その相手) を返す。"""
    out = []
    for x in moves:
        f = flips(P, O, x)
        out.append((x, O ^ f, P | x | f))
    return out


def _expand(level, full, best, ranked, replies):
    """1手先の局面と、そこでの立場を求める。

    level:  正規形の局面 → 立場（BOOK / ANY のビット和）
    best:   BOOK の局面 → (最善手, 評価値)
    ranked: ANY の局面 → 良い順の手のリスト（full のときは使わない）
    """
    nxt = {}

    def add(P, O, roles):
        key = canonical(P, O)[:2]
        nxt[key] = nxt.get(key, 0) | roles

    for (P, O), roles in level.items():
        moves = legal_moves(P, O)
        if not moves:
            if legal_moves(O, P):
                # パス: 手番だけが入れ替わるので、立場も入れ替わる
                add(O, P, (BOOK if roles & ANY else 0) | (ANY if roles & BOOK else 0))
            continue
        if full:
            for _, nP, nO in _children(P, O, _moves(moves)):
                add(nP, nO, BOOK | ANY)
            continue
        if roles & BOOK:
            move = best[(P, O)][0] if (P, O) in best else moves  # 登録していないのは合法手が1つの局面
            for _, nP, nO in _children(P, O, [move]):
                add(nP, nO, ANY)
        if roles & ANY:
            for _, nP, nO in _children(P, O, ranked[(P, O)][:replies]):
                add(nP, nO, BOOK)
    return nxt


def build(settings, processes=None, cache_path=None, log=print):
    """設定に従って定石を作り、OpeningBook を返す。"""
    cache = _Cache(cache_path)
    book = OpeningBook()
    stats = {"searched": 0, "cached": 0}
    start = time.time()

    # level: 正規形の局面 → 立場（BOOK / ANY のビット和）
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
                        continue  # 終局またはパス
                    if roles & BOOK and moves & (moves - 1):  # 打てる手が1つなら読むまでもない
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
                        log(f"  ply {ply}: {i}/{len(todo)} 局面を読了 ({time.time() - start:.0f}s)")
                for (P, O), (move, score) in best.items():
                    book.add(P, O, move, score, settings.depth)

                ranked = {}
                if need_rank:
                    jobs = [(P, O, settings.rank_depth, settings.patterns) for P, O in need_rank]
                    for P, O, order in pool.imap(_rank_replies, jobs, chunksize=4):
                        ranked[(P, O)] = order

                level = _expand(level, full, best, ranked, settings.replies)
                log(
                    f"ply {ply}: 定石 {len(book)} 局面（新たに読んだ {stats['searched']}, キャッシュ {stats['cached']}）"
                    f" 次の局面 {len(level)} ({time.time() - start:.0f}s)"
                )
    finally:
        cache.close()
    return book


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--depth", type=int, default=Settings.depth, help="最善手を決める読みの深さ")
    parser.add_argument("--full-plies", type=int, default=Settings.full_plies, help="すべての局面を登録する手数")
    parser.add_argument("--plies", type=int, default=Settings.plies, help="定石を作る手数")
    parser.add_argument("--replies", type=int, default=Settings.replies, help="--full-plies より先で考える相手の手の数")
    parser.add_argument("--rank-depth", type=int, default=Settings.rank_depth, help="相手の手を選ぶときの読みの深さ")
    parser.add_argument("--patterns", help="葉の評価に使うパターン評価の重みファイル（省略時は線形評価）")
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "opening_book.txt"))
    parser.add_argument("--cache", help="途中結果のファイル（省略時は <out>.cache）")
    parser.add_argument("-j", "--processes", type=int, default=None)
    args = parser.parse_args()

    settings = Settings(args.depth, args.full_plies, args.plies, args.replies, args.rank_depth, args.patterns)
    # 途中結果は評価関数ごとに別のファイルにする（違う評価関数の結果が混ざらないように）
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
    print(f"保存: {args.out}（{len(book)} 局面, {time.time() - t0:.0f}s）")


if __name__ == "__main__":
    main()
