"""Pattern evaluation: scores for the disc configurations of edges, corners, diagonals and lines.

For several board shapes (patterns) there is a table with a score for every configuration of their
squares (each square empty / player / opponent), and the evaluation is the sum of the scores of the
configurations present. Rotated and reflected copies of a shape (instances) share one table. The
instances include every distinct (squares, reading order) pair, so a symmetric edge is read from both
ends; this makes the evaluation exactly symmetric under rotation and reflection for any table.
Good shapes differ between the opening and the endgame, so the game is split into stages by the
number of empty squares, each with its own tables.

Same definitions and arithmetic as the Rust version (backend_rust/src/pattern.rs). All scores are
integers (1/SCALE of a disc), so Python and Rust agree exactly regardless of summation order.

Boards are (player P, opponent O) 64-bit integers; square i = row * 8 + col (a1 = 0, h8 = 63).
"""

import struct
import sys
from array import array

from opening_book import parse_square

# Score unit: a table value of 64 is one disc
SCALE = 64
# Number of stages: the move number (60 - empties) in steps of 4
N_STAGES = 15

# (name, squares in the base orientation). The square order is the digit order of the index
FAMILIES = (
    ("hv2", "a2 b2 c2 d2 e2 f2 g2 h2"),  # 2nd row
    ("hv3", "a3 b3 c3 d3 e3 f3 g3 h3"),  # 3rd row
    ("hv4", "a4 b4 c4 d4 e4 f4 g4 h4"),  # 4th row
    ("diag8", "a1 b2 c3 d4 e5 f6 g7 h8"),  # main diagonal
    ("diag7", "b1 c2 d3 e4 f5 g6 h7"),
    ("diag6", "c1 d2 e3 f4 g5 h6"),
    ("diag5", "d1 e2 f3 g4 h5"),
    ("diag4", "e1 f2 g3 h4"),
    ("edge2x", "a1 b1 c1 d1 e1 f1 g1 h1 b2 g2"),  # edge plus the two X-squares
    ("corner3x3", "a1 b1 c1 a2 b2 c2 a3 b3 c3"),
    ("corner2x5", "a1 b1 c1 d1 e1 a2 b2 c2 d2 e2"),
)
FAMILY_NAMES = tuple(name for name, _ in FAMILIES)
FAMILY_SIZES = tuple(3 ** len(squares.split()) for _, squares in FAMILIES)
# Offset of each pattern's table within one stage
FAMILY_OFFSETS = tuple(sum(FAMILY_SIZES[:i]) for i in range(len(FAMILIES)))
TABLE_SIZE = sum(FAMILY_SIZES)


def _map_square(i, s):
    """Map square i by symmetry s (the same transform as opening_book.transform)."""
    r, c = divmod(i, 8)
    if s & 4:
        r, c = c, r
    if s & 2:
        r = 7 - r
    if s & 1:
        c = 7 - c
    return r * 8 + c


def _build_instances():
    """All 8 rotations/reflections of every pattern, as [(pattern index, squares)].

    Only exact duplicates (same squares in the same order, e.g. a transposed main diagonal) are removed.
    The list is then closed under the symmetries, so the evaluation always respects them.
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
    """Stage for a number of empty squares (0: opening ... N_STAGES-1: endgame)."""
    return min((60 - n_empty) // 4, N_STAGES - 1)


def indices(P, O):
    """Configuration index of every instance (sum of digit * 3^k; digit 0 empty / 1 player / 2 opponent)."""
    out = []
    for _, squares in INSTANCES:
        idx = 0
        for i in reversed(squares):
            idx = idx * 3 + ((P >> i) & 1) + 2 * ((O >> i) & 1)
        out.append(idx)
    return out


class PatternWeights:
    """Score tables per stage. All values are integers (1/SCALE of a disc).

    stages[st] = (bias, mobility-difference coefficient, all pattern tables concatenated as array('h'))
    """

    MAGIC = b"RVPAT\x01"

    def __init__(self, stages=None):
        if stages is None:
            stages = [(0, 0, array("h", bytes(2 * TABLE_SIZE))) for _ in range(N_STAGES)]
        if len(stages) != N_STAGES or any(len(t) != TABLE_SIZE for _, _, t in stages):
            raise ValueError("wrong number of stages or table size")
        self.stages = stages

    def evaluate(self, P, O, my_moves, opp_moves):
        """Evaluation for the player to move P, in discs. my_moves / opp_moves are both sides' legal moves."""
        n_empty = 64 - (P | O).bit_count()
        bias, mobility, table = self.stages[stage_of(n_empty)]
        total = bias + mobility * (my_moves.bit_count() - opp_moves.bit_count())
        for (fam, _), idx in zip(INSTANCES, indices(P, O), strict=True):
            total += table[FAMILY_OFFSETS[fam] + idx]
        return total / SCALE

    # ---------- save / load (same little-endian format as the Rust version) ----------
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
            raise ValueError(f"{path}: not a pattern weights file")
        pos = len(cls.MAGIC)
        n_stages, n_families = struct.unpack_from("<HH", data, pos)
        pos += 4
        sizes = struct.unpack_from(f"<{n_families}I", data, pos)
        pos += 4 * n_families
        if (n_stages, sizes) != (N_STAGES, FAMILY_SIZES):
            raise ValueError(f"{path}: pattern definitions do not match this program")
        expected = pos + N_STAGES * (8 + 2 * TABLE_SIZE)
        if len(data) != expected:
            raise ValueError(f"{path}: unexpected file size ({len(data)} != {expected})")
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
    """Put the array in little-endian order (so big-endian machines write the same file)."""
    if sys.byteorder == "big":
        table = array("h", table)
        table.byteswap()
    return table
