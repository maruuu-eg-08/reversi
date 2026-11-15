"""パターン評価: 辺・隅・斜めなどの石の並びごとに点数を付ける評価関数。

盤面のいくつかの「形」（パターン）について、そのマスの石の並び（空き / 手番側 / 相手 の3通り）ごとに
点数の表を持ち、局面に現れた並びの点数を足し合わせて評価値にする。
同じ形を回転・反転したもの（インスタンス）は同じ表を使う。インスタンスは「見るマスとその順番」が
違うものをすべて含むので（左右対称な辺なら、左から読むものと右から読むもの）、どんな点数の表でも
評価値は盤面の回転・反転に対して完全に対称になる。
序盤と終盤では良い形が違うので、空きマスの数で段階（stage）に分け、段階ごとに別の表を持つ。

Rust 版（backend_rust/src/pattern.rs）と同じ定義・同じ計算をする。
点数はすべて整数（1/SCALE 石単位）なので、足す順番によらず Python 版と Rust 版で完全に同じ値になる。

盤面は (手番側 P, 相手側 O) の 64 ビット整数。マス i = 行 * 8 + 列（a1 = 0, h8 = 63）。
"""

import struct
import sys
from array import array

from opening_book import parse_square

# 点数の単位。表の値 64 が石1個分
SCALE = 64
# 段階の数。手数（60 - 空きマス）を4手ごとに区切る
N_STAGES = 15

# (名前, 基本の向きでのマス)。マスの順番が並びの番号の桁の順番になる
FAMILIES = (
    ("hv2", "a2 b2 c2 d2 e2 f2 g2 h2"),  # 2行目
    ("hv3", "a3 b3 c3 d3 e3 f3 g3 h3"),  # 3行目
    ("hv4", "a4 b4 c4 d4 e4 f4 g4 h4"),  # 4行目
    ("diag8", "a1 b2 c3 d4 e5 f6 g7 h8"),  # 対角線
    ("diag7", "b1 c2 d3 e4 f5 g6 h7"),
    ("diag6", "c1 d2 e3 f4 g5 h6"),
    ("diag5", "d1 e2 f3 g4 h5"),
    ("diag4", "e1 f2 g3 h4"),
    ("edge2x", "a1 b1 c1 d1 e1 f1 g1 h1 b2 g2"),  # 辺と、隅の斜め隣（X打ち）
    ("corner3x3", "a1 b1 c1 a2 b2 c2 a3 b3 c3"),
    ("corner2x5", "a1 b1 c1 d1 e1 a2 b2 c2 d2 e2"),
)
FAMILY_NAMES = tuple(name for name, _ in FAMILIES)
FAMILY_SIZES = tuple(3 ** len(squares.split()) for _, squares in FAMILIES)
# 1段階分の表の中で、各パターンの表が始まる位置
FAMILY_OFFSETS = tuple(sum(FAMILY_SIZES[:i]) for i in range(len(FAMILIES)))
TABLE_SIZE = sum(FAMILY_SIZES)


def _map_square(i, s):
    """マス i を対称変換 s で移す（opening_book.transform と同じ変換）。"""
    r, c = divmod(i, 8)
    if s & 4:
        r, c = c, r
    if s & 2:
        r = 7 - r
    if s & 1:
        c = 7 - c
    return r * 8 + c


def _build_instances():
    """各パターンを8通りに回転・反転した一覧 [(パターン番号, マスの並び)]。

    マスとその順番がまったく同じになるもの（対角線を転置したものなど）だけを除く。
    こうすると一覧が回転・反転について閉じるので、評価値が盤面の対称性を必ず保つ。
    """
    out = []
    for fam, (_, squares) in enumerate(FAMILIES):
        base = [parse_square(sq).bit_length() - 1 for sq in squares.split()]
        seen = set()
        for s in range(8):
            image = tuple(_map_square(i, s) for i in base)
            if image not in seen:
                seen.add(image)
                out.append((fam, image))
    return tuple(out)


INSTANCES = _build_instances()


def stage_of(n_empty):
    """空きマスの数から段階を求める（0: 序盤 〜 N_STAGES-1: 終盤）。"""
    return min((60 - n_empty) // 4, N_STAGES - 1)


def indices(P, O):
    """各インスタンスの並びの番号（Σ 桁 × 3^k、桁は 空き=0 / 手番側=1 / 相手=2）。"""
    out = []
    for _, squares in INSTANCES:
        idx = 0
        for i in reversed(squares):
            idx = idx * 3 + ((P >> i) & 1) + 2 * ((O >> i) & 1)
        out.append(idx)
    return out


class PatternWeights:
    """段階ごとの点数の表。値はすべて整数（1/SCALE 石単位）。

    stages[st] = (定数項, 着手可能数の差の係数, 全パターンの表を並べた array('h'))
    """

    MAGIC = b"RVPAT\x01"

    def __init__(self, stages=None):
        if stages is None:
            stages = [(0, 0, array("h", bytes(2 * TABLE_SIZE))) for _ in range(N_STAGES)]
        if len(stages) != N_STAGES or any(len(t) != TABLE_SIZE for _, _, t in stages):
            raise ValueError("段階の数か表の大きさが正しくありません")
        self.stages = stages

    def evaluate(self, P, O, my_moves, opp_moves):
        """手番側 P から見た評価値（石数の単位）。my_moves / opp_moves は両者の合法手。"""
        n_empty = 64 - (P | O).bit_count()
        bias, mobility, table = self.stages[stage_of(n_empty)]
        total = bias + mobility * (my_moves.bit_count() - opp_moves.bit_count())
        for (fam, _), idx in zip(INSTANCES, indices(P, O), strict=True):
            total += table[FAMILY_OFFSETS[fam] + idx]
        return total / SCALE

    # ---------- 保存・読み込み（Rust 版と同じ形式、リトルエンディアン） ----------
    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.MAGIC)
            f.write(struct.pack("<HH", N_STAGES, len(FAMILIES)))
            f.write(struct.pack(f"<{len(FAMILIES)}I", *FAMILY_SIZES))
            for bias, mobility, table in self.stages:
                f.write(struct.pack("<ii", bias, mobility))
                f.write(_little_endian(table).tobytes())

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            data = f.read()
        if not data.startswith(cls.MAGIC):
            raise ValueError(f"{path}: パターンの重みファイルではありません")
        pos = len(cls.MAGIC)
        n_stages, n_families = struct.unpack_from("<HH", data, pos)
        pos += 4
        sizes = struct.unpack_from(f"<{n_families}I", data, pos)
        pos += 4 * n_families
        if (n_stages, sizes) != (N_STAGES, FAMILY_SIZES):
            raise ValueError(f"{path}: パターンの定義がこのプログラムと違います")
        expected = pos + N_STAGES * (8 + 2 * TABLE_SIZE)
        if len(data) != expected:
            raise ValueError(f"{path}: ファイルの大きさが正しくありません（{len(data)} != {expected}）")
        stages = []
        for _ in range(N_STAGES):
            bias, mobility = struct.unpack_from("<ii", data, pos)
            pos += 8
            table = array("h")
            table.frombytes(data[pos : pos + 2 * TABLE_SIZE])
            pos += 2 * TABLE_SIZE
            stages.append((bias, mobility, _little_endian(table)))
        return cls(stages)


def _little_endian(table):
    """array をリトルエンディアンの並びにする（ビッグエンディアンの環境でも同じファイルになるように）。"""
    if sys.byteorder == "big":
        table = array("h", table)
        table.byteswap()
    return table
