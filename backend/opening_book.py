"""序盤の定石（opening book）: 事前に深く読んでおいた局面と最善手の表。

リバーシの盤面は回転・反転（8通りの対称変換）で本質的に同じ局面になる。
そこで各局面を「8通りの変換のうち最小のもの」（正規形）に直して保存し、
引くときは同じ変換で正規形にしてから、見つかった手を逆変換して元の向きに戻す。
これで表の大きさは約1/8〜1/4になり、どの向きから打たれても同じ定石が使える。

盤面は (手番側 P, 相手側 O) の 64ビット整数ペア。マス i = 行 * 8 + 列（a1 = 0, h8 = 63）。

ファイル形式（1行1局面、`#` で始まる行はコメント）:
    <P 16桁hex> <O 16桁hex> <最善手 例: f5> <評価値> <読んだ深さ>
P, O, 手はすべて正規形の向き。
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from strong_ai import legal_moves

MASK64 = 0xFFFFFFFFFFFFFFFF
COLS = "abcdefgh"
DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opening_book.txt")


# ---------- 対称変換 ----------
def flip_vertical(b):
    """上下反転（1行目 ↔ 8行目）。8バイトの並びを逆にするだけ。"""
    return int.from_bytes(b.to_bytes(8, "little"), "big")


def mirror_horizontal(b):
    """左右反転（a列 ↔ h列）。各バイト内のビット順を逆にする。"""
    b = ((b >> 1) & 0x5555555555555555) | ((b & 0x5555555555555555) << 1)
    b = ((b >> 2) & 0x3333333333333333) | ((b & 0x3333333333333333) << 2)
    return ((b >> 4) & 0x0F0F0F0F0F0F0F0F) | ((b & 0x0F0F0F0F0F0F0F0F) << 4)


def transpose(b):
    """a1-h8 の対角線で折り返す（行と列を入れ替える）。"""
    t = 0x0F0F0F0F00000000 & (b ^ (b << 28))
    b ^= t ^ (t >> 28)
    t = 0x3333000033330000 & (b ^ (b << 14))
    b ^= t ^ (t >> 14)
    t = 0x5500550055005500 & (b ^ (b << 7))
    b ^= t ^ (t >> 7)
    return b & MASK64


N_SYMMETRIES = 8


def transform(b, s):
    """対称変換 s（0〜7）を適用する。bit 2: 転置, bit 1: 上下反転, bit 0: 左右反転 の順に行う。"""
    if s & 4:
        b = transpose(b)
    if s & 2:
        b = flip_vertical(b)
    if s & 1:
        b = mirror_horizontal(b)
    return b


def inverse_transform(b, s):
    """transform(b, s) を元に戻す。各変換は2回で元に戻るので、逆順に適用すればよい。"""
    if s & 1:
        b = mirror_horizontal(b)
    if s & 2:
        b = flip_vertical(b)
    if s & 4:
        b = transpose(b)
    return b


def canonical(P, O):
    """(P, O) の8通りの変換のうち最小のものと、そこへ移す変換番号を返す。"""
    best = None
    best_s = 0
    for s in range(N_SYMMETRIES):
        key = (transform(P, s), transform(O, s))
        if best is None or key < best:
            best, best_s = key, s
    return best[0], best[1], best_s


# ---------- マスの表記 ----------
def square_name(bit):
    i = bit.bit_length() - 1
    return f"{COLS[i % 8]}{i // 8 + 1}"


def parse_square(name):
    """'f5' → 1ビットだけ立った整数。"""
    name = name.strip().lower()
    if len(name) != 2 or name[0] not in COLS or name[1] not in "12345678":
        raise ValueError(f"マスの表記が正しくありません: {name!r}")
    return 1 << ((int(name[1]) - 1) * 8 + COLS.index(name[0]))


# ---------- 定石の表 ----------
@dataclass(frozen=True)
class BookEntry:
    move: int  # 正規形の向きでの最善手（1ビット）
    score: float  # 手番側から見た評価値
    depth: int  # 何手先まで読んだ結果か


@dataclass(frozen=True)
class BookHit:
    move: int  # 問い合わせた局面の向きに戻した最善手（1ビット）
    score: float
    depth: int


class OpeningBook:
    def __init__(self):
        self._entries = {}

    def __len__(self):
        return len(self._entries)

    def __contains__(self, position):
        P, O = position
        cP, cO, _ = canonical(P, O)
        return (cP, cO) in self._entries

    def add(self, P, O, move, score, depth):
        """局面 (P, O) の最善手 move（1ビット、P, O と同じ向き）を登録する。"""
        if not move & legal_moves(P, O) or move & (move - 1):
            raise ValueError(f"{square_name(move)} はこの局面の合法手ではありません")
        cP, cO, s = canonical(P, O)
        self._entries[(cP, cO)] = BookEntry(transform(move, s), float(score), int(depth))

    def probe(self, P, O):
        """局面が表にあれば BookHit を、なければ None を返す。"""
        cP, cO, s = canonical(P, O)
        entry = self._entries.get((cP, cO))
        if entry is None:
            return None
        move = inverse_transform(entry.move, s)
        # 壊れたファイルなどで合法手でない手が入っていても、それを打たないようにする
        if not move & legal_moves(P, O):
            return None
        return BookHit(move, entry.score, entry.depth)

    def items(self):
        """(正規形の P, O, BookEntry) を決まった順番で返す。"""
        for (P, O), entry in sorted(self._entries.items()):
            yield P, O, entry

    # ---------- 保存・読み込み ----------
    def save(self, path, header=()):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Reversi opening book\n")
            for line in header:
                f.write(f"# {line}\n")
            f.write("# columns: player(hex) opponent(hex) best_move score depth  (canonical orientation)\n")
            for P, O, e in self.items():
                f.write(f"{P:016x} {O:016x} {square_name(e.move)} {e.score:.2f} {e.depth}\n")

    @classmethod
    def load(cls, path):
        book = cls()
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    p, o, move, score, depth = line.split()
                    book._entries[(int(p, 16), int(o, 16))] = BookEntry(parse_square(move), float(score), int(depth))
                except ValueError as e:
                    raise ValueError(f"{path}:{lineno}: 定石ファイルの形式が正しくありません ({e})") from e
        return book


@lru_cache(maxsize=1)
def default_book():
    """同梱の定石ファイルを読み込む（1回だけ）。ファイルがなければ空の表を返す。"""
    if not os.path.exists(DEFAULT_PATH):
        return OpeningBook()
    return OpeningBook.load(DEFAULT_PATH)
