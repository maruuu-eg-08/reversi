"""名前の付いた定石（虎・牛・ローズなど）を棋譜から判定する。

手順は Robert Gatliff の定石リスト（77種）による:
    https://www.samsoft.org.uk/reversi/openings.htm
リストは初手を c4 で書いているが、初手 f5 / d3 / e6 の対局も盤面を回転・反転すれば同じなので、
判定時に棋譜の向きをリストに合わせてから比較する。

日本語名は、日本で一般に使われている呼び名が確かなものだけ付けている（それ以外は英語名で表示）。
"""

from dataclasses import dataclass

from opening_book import N_SYMMETRIES, parse_square, square_name, transform
from strong_ai import flips, legal_moves

START_BLACK = 0x0000000810000000
START_WHITE = 0x0000001008000000

# (手順, 英語名)。手順は Gatliff のリストの表記をそのまま小文字にしたもの
_GATLIFF = [
    ("c4c3", "Diagonal Opening"),
    ("c4c3d3c5b2", "X-square Opening"),
    ("c4c3d3c5b3", "Snake/Peasant"),
    ("c4c3d3c5b3f3", "Lysons"),
    ("c4c3d3c5b3f4b5b4c6d6f5", "Pyramid/Checkerboarding Peasant"),
    ("c4c3d3c5b4", "Heath/Tobidashi"),
    ("c4c3d3c5b4d2c2f4d6c6f5e6f7", "Mimura Variation II"),
    ("c4c3d3c5b4d2d6", "Heath-Bat"),
    ("c4c3d3c5b4d2e2", "Iwasaki Variation"),
    ("c4c3d3c5b4e3", "Heath-Chimney"),
    ("c4c3d3c5b5", "Raccoon Dog"),
    ("c4c3d3c5b6", "Rocket"),
    ("c4c3d3c5b6c6b5", "Hamilton"),
    ("c4c3d3c5b6e3", "Lollipop"),
    ("c4c3d3c5d6", "Cow"),
    ("c4c3d3c5d6e3", "Chimney"),
    ("c4c3d3c5d6f4b4", "Cow Bat/Bat/Cambridge"),
    ("c4c3d3c5d6f4b4b6b5c6b3", "Bat (Piau Continuation 2)"),
    ("c4c3d3c5d6f4b4b6b5c6f5", "Melnikov/Bat (Piau Continuation 1)"),
    ("c4c3d3c5d6f4b4c6b5b3b6e3c2a4a5a6d2", "Bat (Kling Continuation)"),
    ("c4c3d3c5d6f4b4e3b3", "Bat (Kling Alternative)"),
    ("c4c3d3c5d6f4f5", "Rose-v-Toth"),
    ("c4c3d3c5d6f4f5d2", "Tanida"),
    ("c4c3d3c5d6f4f5d2b5", "Aircraft/Feldborg"),
    ("c4c3d3c5d6f4f5d2g4d7", "Sailboat"),
    ("c4c3d3c5d6f4f5e6c6d7", "Maruoka"),
    ("c4c3d3c5d6f4f5e6f6", "Landau"),
    ("c4c3d3c5f6", "Buffalo/Kenichi Variation"),
    ("c4c3d3c5f6e2c6", "Maruoka Buffalo"),
    ("c4c3d3c5f6e3c6f5f4g5", "Tanida Buffalo"),
    ("c4c3d3c5f6f5", "Hokuriku Buffalo"),
    ("c4c3e6c5", "Wing Variation"),
    ("c4c3f5c5", "Semi-Wing Variation"),
    ("c4c5", "Parallel Opening"),
    ("c4e3", "Perpendicular Opening"),
    ("c4e3f4c5d6e6", "Mimura"),
    ("c4e3f4c5d6f3c6", "Shaman/Danish"),
    ("c4e3f4c5d6f3d3", "Inoue"),
    ("c4e3f4c5d6f3d3c3", "Iago"),
    ("c4e3f4c5d6f3e2", "Bhagat"),
    ("c4e3f4c5d6f3e6c3d3e2", "Rose"),
    ("c4e3f4c5d6f3e6c3d3e2b5", "Flat"),
    ("c4e3f4c5d6f3e6c3d3e2b5f5", "Rotating Flat"),
    ("c4e3f4c5d6f3e6c3d3e2b5f5b3", "Murakami Variation"),
    ("c4e3f4c5d6f3e6c3d3e2b5f5b4f6c2e7d2c7", "Rotating Flat (Kling Continuation)"),
    ("c4e3f4c5d6f3e6c3d3e2b6f5", "Rose-Birth"),
    ("c4e3f4c5d6f3e6c3d3e2b6f5b4f6g5d7", "Brightstein"),
    ("c4e3f4c5d6f3e6c3d3e2b6f5g5", "Rose-Birdie/Rose-Tamenori"),
    ("c4e3f4c5d6f3e6c3d3e2b6f5g5f6", "Rose-Tamenori-Kling"),
    ("c4e3f4c5d6f3e6c3d3e2d2", "Greenberg/Dawg"),
    ("c4e3f4c5d6f3e6c6", "Ralle"),
    ("c4e3f4c5e6", "Horse"),
    ("c4e3f5b4", "Ganglion/No-Cat"),
    ("c4e3f5b4f3", "Swallow"),
    ("c4e3f5b4f3f4e2e6g5f6d6c6", "No-Cat (Continuation)"),
    ("c4e3f5e6d3", "Italian"),
    ("c4e3f5e6f4", "Cat"),
    ("c4e3f5e6f4c5d6c6f7f3", "Sakaguchi"),
    ("c4e3f5e6f4c5d6c6f7g5g6", "Berner"),
    ("c4e3f6b4", "Bent Ganglion"),
    ("c4e3f6e6f5", "Tiger"),
    ("c4e3f6e6f5c5c3", "Stephenson"),
    ("c4e3f6e6f5c5c3b4", "No-Kung"),
    ("c4e3f6e6f5c5c3b4d6c6b5a6b6c7", "No-Kung (Continuation)"),
    ("c4e3f6e6f5c5c3c6", "Comp'Oth"),
    ("c4e3f6e6f5c5c3c6d3d2e2b3c1c2b4a3a5b5a6a4a2", "F.A.T. Draw"),
    ("c4e3f6e6f5c5c3c6d6", "Lightning Bolt"),
    ("c4e3f6e6f5c5c3g5", "Kung"),
    ("c4e3f6e6f5c5d3", "Leader's Tiger"),
    ("c4e3f6e6f5c5d6", "Brightwell"),
    ("c4e3f6e6f5c5f4g5g4f3c6d3d6", "Ishii"),
    ("c4e3f6e6f5c5f4g5g4f3c6d3d6b3c3b4e2b6", "Mainline Tiger"),
    ("c4e3f6e6f5c5f4g6f7", "Rose-Bill"),
    ("c4e3f6e6f5c5f4g6f7d3", "Tamenori"),
    ("c4e3f6e6f5c5f4g6f7g5", "Central Rose-Bill/Dead Draw"),
    ("c4e3f6e6f5g6", "Aubrey/Tanaka"),
    ("c4e3f6e6f5g6e7c5", "Aubrey (Feldborg Continuation)"),
]

# 日本で一般に使われている呼び名
_JAPANESE = {
    "Diagonal Opening": "斜め取り",
    "Parallel Opening": "並び取り",
    "Perpendicular Opening": "縦取り",
    "Tiger": "虎",
    "Cow": "牛",
    "Cat": "猫",
    "Rose": "ローズ",
    "Buffalo/Kenichi Variation": "バッファロー",
    "Heath/Tobidashi": "ヒース（飛び出し）",
}


@dataclass(frozen=True)
class Opening:
    moves: tuple  # リストの向きでの手順（1ビットの整数の並び）
    name: str  # 英語名
    japanese: str | None = None

    @property
    def display_name(self):
        return f"{self.japanese}（{self.name}）" if self.japanese else self.name


def _split(seq):
    return tuple(parse_square(seq[i : i + 2]) for i in range(0, len(seq), 2))


OPENINGS = tuple(Opening(_split(seq), name, _JAPANESE.get(name)) for seq, name in _GATLIFF)

# 開始局面を変えない対称変換（4通り）。棋譜の向きをリストに合わせるのに使う
_START_SYMMETRIES = tuple(
    s for s in range(N_SYMMETRIES) if transform(START_BLACK, s) == START_BLACK and transform(START_WHITE, s) == START_WHITE
)
_FIRST_MOVE = OPENINGS[0].moves[0]  # c4


def _normalize(moves):
    """初手が c4 になるように棋譜を回転・反転する。初手が不正なら None。"""
    if not moves:
        return ()
    for s in _START_SYMMETRIES:
        if transform(moves[0], s) == _FIRST_MOVE:
            return tuple(transform(m, s) for m in moves)
    return None


def identify(moves):
    """棋譜（1ビットの整数またはマス名の並び、パスは含めない）に一致する、いちばん長い定石を返す。

    対局が定石から外れた後も、外れる前に通った最も長い定石を返す。どれにも当てはまらなければ None。
    """
    moves = tuple(parse_square(m) if isinstance(m, str) else m for m in moves)
    normalized = _normalize(moves)
    if not normalized:
        return None
    best = None
    for op in OPENINGS:
        n = len(op.moves)
        if n <= len(normalized) and normalized[:n] == op.moves and (best is None or n > len(best.moves)):
            best = op
    return best


def replay(moves):
    """手順を開始局面から打ち、(黒, 白) を返す。不正な手があれば ValueError（テスト用）。"""
    P, O = START_BLACK, START_WHITE
    black_to_move = True
    for x in moves:
        if not legal_moves(P, O):
            P, O = O, P
            black_to_move = not black_to_move
        if not x & legal_moves(P, O):
            raise ValueError(f"{square_name(x)} は打てません")
        f = flips(P, O, x)
        P, O = O ^ f, P | x | f
        black_to_move = not black_to_move
    return (P, O) if black_to_move else (O, P)
