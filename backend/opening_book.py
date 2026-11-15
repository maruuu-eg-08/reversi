"""Opening book: precomputed best moves for opening positions, searched deeply in advance.

A reversi position is essentially the same under its 8 rotations and reflections, so each position is
stored in canonical form (the smallest of its 8 images). A lookup canonicalizes the query the same
way and maps the stored move back to the original orientation. This shrinks the table to about
1/8-1/4 and makes the book work whichever way round the game is played.

Boards are (player P, opponent O) 64-bit integers; square i = row * 8 + col (a1 = 0, h8 = 63).

File format (one position per line; lines starting with `#` are comments):
    <P as 16 hex digits> <O as 16 hex digits> <best move, e.g. f5> <score> <search depth>
P, O and the move are all in the canonical orientation.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from strong_ai import legal_moves

MASK64 = 0xFFFFFFFFFFFFFFFF
COLS = "abcdefgh"
DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opening_book.txt")


# ---------- symmetries ----------
def flip_vertical(b):
    """Flip vertically (row 1 <-> row 8): just reverse the 8 bytes."""
    return int.from_bytes(b.to_bytes(8, "little"), "big")


def mirror_horizontal(b):
    """Mirror horizontally (a-file <-> h-file): reverse the bits within each byte."""
    b = ((b >> 1) & 0x5555555555555555) | ((b & 0x5555555555555555) << 1)
    b = ((b >> 2) & 0x3333333333333333) | ((b & 0x3333333333333333) << 2)
    return ((b >> 4) & 0x0F0F0F0F0F0F0F0F) | ((b & 0x0F0F0F0F0F0F0F0F) << 4)


def transpose(b):
    """Reflect in the a1-h8 diagonal (swap rows and columns)."""
    t = 0x0F0F0F0F00000000 & (b ^ (b << 28))
    b ^= t ^ (t >> 28)
    t = 0x3333000033330000 & (b ^ (b << 14))
    b ^= t ^ (t >> 14)
    t = 0x5500550055005500 & (b ^ (b << 7))
    b ^= t ^ (t >> 7)
    return b & MASK64


N_SYMMETRIES = 8


def transform(b, s):
    """Apply symmetry s (0-7): bit 2 transpose, then bit 1 vertical flip, then bit 0 horizontal mirror."""
    if s & 4:
        b = transpose(b)
    if s & 2:
        b = flip_vertical(b)
    if s & 1:
        b = mirror_horizontal(b)
    return b


def inverse_transform(b, s):
    """Undo transform(b, s). Each step is its own inverse, so apply them in reverse order."""
    if s & 1:
        b = mirror_horizontal(b)
    if s & 2:
        b = flip_vertical(b)
    if s & 4:
        b = transpose(b)
    return b


def canonical(P, O):
    """Return the smallest of the 8 images of (P, O) and the symmetry that produces it."""
    best = None
    best_s = 0
    for s in range(N_SYMMETRIES):
        key = (transform(P, s), transform(O, s))
        if best is None or key < best:
            best, best_s = key, s
    return best[0], best[1], best_s


# ---------- square names ----------
def square_name(bit):
    i = bit.bit_length() - 1
    return f"{COLS[i % 8]}{i // 8 + 1}"


def parse_square(name):
    """'f5' -> an integer with a single bit set."""
    name = name.strip().lower()
    if len(name) != 2 or name[0] not in COLS or name[1] not in "12345678":
        raise ValueError(f"invalid square name: {name!r}")
    return 1 << ((int(name[1]) - 1) * 8 + COLS.index(name[0]))


# ---------- the book ----------
@dataclass(frozen=True)
class BookEntry:
    move: int  # best move in canonical orientation (single bit)
    score: float  # score for the side to move
    depth: int  # search depth that produced it


@dataclass(frozen=True)
class BookHit:
    move: int  # best move in the queried orientation (single bit)
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
        """Store `move` (single bit, same orientation as P, O) as the best move of (P, O)."""
        if not move & legal_moves(P, O) or move & (move - 1):
            raise ValueError(f"{square_name(move)} is not a legal move in this position")
        cP, cO, s = canonical(P, O)
        self._entries[(cP, cO)] = BookEntry(transform(move, s), float(score), int(depth))

    def probe(self, P, O):
        """Return a BookHit if the position is in the book, otherwise None."""
        cP, cO, s = canonical(P, O)
        entry = self._entries.get((cP, cO))
        if entry is None:
            return None
        move = inverse_transform(entry.move, s)
        # never return an illegal move, even from a corrupt file
        if not move & legal_moves(P, O):
            return None
        return BookHit(move, entry.score, entry.depth)

    def items(self):
        """Yield (canonical P, O, BookEntry) in a fixed order."""
        for (P, O), entry in sorted(self._entries.items()):
            yield P, O, entry

    # ---------- save / load ----------
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
                    raise ValueError(f"{path}:{lineno}: invalid opening book line ({e})") from e
        return book


@lru_cache(maxsize=1)
def default_book():
    """Load the bundled opening book (once). Returns an empty book if the file is missing."""
    if not os.path.exists(DEFAULT_PATH):
        return OpeningBook()
    return OpeningBook.load(DEFAULT_PATH)
