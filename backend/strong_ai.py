"""Lv.5: a strong, time-limited AI.

Main improvements over Lv.4 (AlphaBetaAI):
- Works directly on the (player P, opponent O) integer pair, avoiding object creation and method calls
- Negamax + PVS (full window for the first candidate, null-window checks for the rest)
- Iterative deepening with a time limit: searches as deep as the time allows
- Transposition table stores the best move, which is tried first at the next depth (move ordering)
- Fastest-first ordering: moves that leave the opponent fewer replies are searched first
- Per-row weight tables are precomputed, so the positional score is 8 table lookups instead of a bit scan
- Endgame is solved exactly to the final disc difference
- The evaluation adds frontier discs (discs adjacent to an empty square)
- In the opening, positions found in the opening book (opening_book.py) are played without searching

Everything is pure Python, so it also runs in a browser via Pyodide.

The search also has a Rust implementation (backend_rust/, `import reversi_engine`). When it is installed it is
used by default (engine="auto"). At a fixed depth it returns the same move, score and node count as the
Python version; only the speed differs (checked by tests/test_rust_engine.py).
"""

import functools
import os
import time

from weights import POSITION_WEIGHTS, STRONG_EVAL_COEFFS, WIN_SCORE

try:
    import reversi_engine as _native
except ImportError:  # without the Rust build (e.g. the browser) the pure-Python search is used
    _native = None

ENGINES = ("auto", "rust", "python")

# Bundled pattern-evaluation weights (trained by train_patterns.py; settings and accuracy in pattern_weights.json)
DEFAULT_PATTERNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pattern_weights.bin")


@functools.lru_cache(maxsize=4)
def _load_patterns(path):
    """Load pattern-evaluation weights (each file only once)."""
    from patterns import PatternWeights  # imported here to avoid the patterns -> opening_book -> strong_ai cycle

    return PatternWeights.load(path)

MASK64 = 0xFFFFFFFFFFFFFFFF
NOT_EDGE_COLS = 0x7E7E7E7E7E7E7E7E  # excludes the a- and h-files
NOT_COL_A = 0xFEFEFEFEFEFEFEFE  # clears bits that wrapped onto the a-file after a left shift
NOT_COL_H = 0x7F7F7F7F7F7F7F7F  # clears bits that wrapped onto the h-file after a right shift
CORNERS = (1 << 0) | (1 << 7) | (1 << 56) | (1 << 63)

# Number of evaluation features (position, mobility, discs, frontier)
N_FEATURES = 4


class SearchTimeout(Exception):
    pass


def legal_moves(P, O):
    """Bitboard of the squares where the player to move (P) can play."""
    empty = ~(P | O) & MASK64
    oh = O & NOT_EDGE_COLS  # horizontal/diagonal runs may not pass through edge files (prevents row wrap-around)
    moves = 0
    for s, m in ((1, oh), (8, O), (7, oh), (9, oh)):
        t = (P << s) & m
        t |= (t << s) & m
        t |= (t << s) & m
        t |= (t << s) & m
        t |= (t << s) & m
        t |= (t << s) & m
        moves |= (t << s) & empty

        t = (P >> s) & m
        t |= (t >> s) & m
        t |= (t >> s) & m
        t |= (t >> s) & m
        t |= (t >> s) & m
        t |= (t >> s) & m
        moves |= (t >> s) & empty
    return moves


def flips(P, O, x):
    """Discs flipped when P plays on x (a single bit)."""
    oh = O & NOT_EDGE_COLS
    f = 0
    for s, m in ((1, oh), (8, O), (7, oh), (9, oh)):
        t = 0
        y = x << s
        while y & m:
            t |= y
            y <<= s
        if y & P:
            f |= t

        t = 0
        y = x >> s
        while y & m:
            t |= y
            y >>= s
        if y & P:
            f |= t
    return f


def neighbors(b):
    """The 8-neighborhood of b."""
    return (
        ((b << 1) & NOT_COL_A)
        | ((b >> 1) & NOT_COL_H)
        | (b << 8)
        | (b >> 8)
        | ((b << 9) & NOT_COL_A)
        | ((b >> 9) & NOT_COL_H)
        | ((b << 7) & NOT_COL_H)
        | ((b >> 7) & NOT_COL_A)
    ) & MASK64


def _row_tables(weights):
    """Precompute the summed weights for all 256 disc patterns of each 8-bit row."""
    tables = []
    for row in range(8):
        table = []
        for pattern in range(256):
            # Add column by column instead of using sum(): since Python 3.12 sum() uses compensated
            # summation for floats, which would differ in the last bit across Python versions and from Rust
            total = 0.0
            for c in range(8):
                if (pattern >> c) & 1:
                    total += weights[row * 8 + c]
            table.append(total)
        tables.append(table)
    return tables


class StrongAI:
    def __init__(
        self, color, time_limit=1.0, max_depth=60, eval_coeffs=None, weights=None, book=None, engine="auto", patterns=None
    ):
        """
        book:     object whose probe(P, O) returns an opening-book move (OpeningBook); None disables the book.
        engine:   search implementation: "auto" (Rust if available) / "rust" / "python".
        patterns: path to a pattern-evaluation weights file used at the leaves (move ordering still uses the
                  positional weights). None means the linear evaluation. "auto" uses the bundled weights only
                  when searching with Rust (pattern evaluation is too slow in pure Python).
        """
        if engine not in ENGINES:
            raise ValueError(f"engine must be one of {ENGINES}: {engine!r}")
        if engine == "rust" and _native is None:
            raise ImportError("Rust engine not installed; run `maturin develop --release` in backend_rust/")
        self.color = color
        self.time_limit = time_limit
        self.max_depth = max_depth
        self.coeffs = list(eval_coeffs) if eval_coeffs is not None else list(STRONG_EVAL_COEFFS)
        self.weights = list(weights) if weights is not None else list(POSITION_WEIGHTS)
        r = _row_tables(self.weights)
        self._t0, self._t1, self._t2, self._t3, self._t4, self._t5, self._t6, self._t7 = r
        self._order_weight = {1 << i: w for i, w in enumerate(self.weights)}
        self.tt = {}
        self.nodes = 0
        self.last_depth = 0
        self.last_score = 0
        self.solved = False  # whether the last move came from an exact endgame solve
        self.book = book
        self.from_book = False  # whether the last move came from the opening book
        self._deadline = float("inf")
        self._iter_best = None
        if patterns == "auto":
            use_rust = _native is not None and engine != "python"
            patterns = DEFAULT_PATTERNS if use_rust and os.path.exists(DEFAULT_PATTERNS) else None
        self.patterns_path = str(patterns) if patterns is not None else None
        self.patterns = _load_patterns(self.patterns_path) if self.patterns_path else None
        self._native = (
            _native.Searcher(self.coeffs, self.weights, self.patterns_path) if _native is not None and engine != "python" else None
        )

    @property
    def engine(self):
        """The search implementation actually in use ("rust" / "python")."""
        return "rust" if self._native is not None else "python"

    # ---------- evaluation ----------
    def _pos(self, b):
        return (
            self._t0[b & 255]
            + self._t1[(b >> 8) & 255]
            + self._t2[(b >> 16) & 255]
            + self._t3[(b >> 24) & 255]
            + self._t4[(b >> 32) & 255]
            + self._t5[(b >> 40) & 255]
            + self._t6[(b >> 48) & 255]
            + self._t7[(b >> 56) & 255]
        )

    def evaluate(self, P, O, my_moves=None):
        """Evaluation from the point of view of the player to move (P)."""
        if my_moves is None:
            my_moves = legal_moves(P, O)
        if self.patterns is not None:
            return self.patterns.evaluate(P, O, my_moves, legal_moves(O, P))
        empty = ~(P | O) & MASK64
        n_empty = empty.bit_count()
        if n_empty >= 45:
            base = 0
        elif n_empty >= 15:
            base = N_FEATURES
        else:
            base = 2 * N_FEATURES
        c = self.coeffs
        adj = neighbors(empty)
        return (
            c[base] * (self._pos(P) - self._pos(O))
            + c[base + 1] * (my_moves.bit_count() - legal_moves(O, P).bit_count())
            + c[base + 2] * (P.bit_count() - O.bit_count())
            + c[base + 3] * ((O & adj).bit_count() - (P & adj).bit_count())
        )

    @staticmethod
    def final_score(P, O):
        """Score of a finished game for P. Empty squares go to the winner (standard rule)."""
        p = P.bit_count()
        o = O.bit_count()
        empty = 64 - p - o
        if p > o:
            return WIN_SCORE + p - o + empty
        if p < o:
            return -WIN_SCORE + p - o - empty
        return 0

    # ---------- search ----------
    def _check_time(self):
        if time.perf_counter() > self._deadline:
            raise SearchTimeout

    def _ordered(self, P, O, moves, tt_move, depth):
        """Order the moves to search."""
        lst = []
        while moves:
            x = moves & -moves
            moves ^= x
            lst.append(x)
        if len(lst) > 1:
            if depth >= 3:
                # fastest-first: fewest opponent replies first (ties broken by the higher positional weight)
                keyed = []
                ow = self._order_weight
                for x in lst:
                    f = flips(P, O, x)
                    keyed.append((legal_moves(O ^ f, P | x | f).bit_count() * 1000 - ow[x], x))
                keyed.sort()
                lst = [x for _, x in keyed]
            else:
                ow = self._order_weight
                lst.sort(key=ow.__getitem__, reverse=True)
        if tt_move and tt_move in lst:
            lst.remove(tt_move)
            lst.insert(0, tt_move)
        return lst

    def _negamax(self, P, O, depth, alpha, beta):
        self.nodes += 1
        if self.nodes & 1023 == 0:
            self._check_time()

        moves = legal_moves(P, O)
        if not moves:
            if not legal_moves(O, P):
                return self.final_score(P, O)
            return -self._negamax(O, P, depth, -beta, -alpha)
        if depth <= 0:
            return self.evaluate(P, O, moves)

        key = (P, O)
        entry = self.tt.get(key)
        tt_move = 0
        if entry is not None:
            e_depth, e_flag, e_value, tt_move = entry
            if e_depth >= depth:
                if e_flag == 0:
                    return e_value
                if e_flag == 1 and e_value >= beta:
                    return e_value
                if e_flag == -1 and e_value <= alpha:
                    return e_value

        original_alpha = alpha
        best = -float("inf")
        best_move = 0
        first = True
        for x in self._ordered(P, O, moves, tt_move, depth):
            f = flips(P, O, x)
            nP = O ^ f
            nO = P | x | f
            if first:
                score = -self._negamax(nP, nO, depth - 1, -beta, -alpha)
                first = False
            else:
                # PVS: first test with a null window whether the move beats alpha; re-search if it does
                score = -self._negamax(nP, nO, depth - 1, -alpha - 1e-6, -alpha)
                if alpha < score < beta:
                    score = -self._negamax(nP, nO, depth - 1, -beta, -score)
            if score > best:
                best = score
                best_move = x
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        break

        if best <= original_alpha:
            flag = -1  # upper bound
        elif best >= beta:
            flag = 1  # lower bound
        else:
            flag = 0
        self.tt[key] = (depth, flag, best, best_move)
        return best

    def _root(self, P, O, depth, prev_best):
        """Search every root move and return (best move, score)."""
        moves = legal_moves(P, O)
        alpha = -float("inf")
        beta = float("inf")
        best_move = 0
        first = True
        for x in self._ordered(P, O, moves, prev_best, depth):
            f = flips(P, O, x)
            nP = O ^ f
            nO = P | x | f
            if first:
                score = -self._negamax(nP, nO, depth - 1, -beta, -alpha)
                first = False
            else:
                score = -self._negamax(nP, nO, depth - 1, -alpha - 1e-6, -alpha)
                if score > alpha:
                    score = -self._negamax(nP, nO, depth - 1, -beta, -score)
            if score > alpha:
                alpha = score
                best_move = x
                # remember the best move so far in case the time runs out mid-iteration
                self._iter_best = (best_move, alpha)
        return best_move, alpha

    def search(self, P, O):
        """Iterative deepening. On timeout, return the best move of the last completed depth."""
        self.tt = {}
        self.nodes = 0
        self.solved = False
        self.from_book = False
        start = time.perf_counter()
        self._deadline = start + self.time_limit

        moves = legal_moves(P, O)
        if not moves:
            return 0, 0, 0
        if moves & (moves - 1) == 0:  # only one legal move
            self.last_depth = 0
            return moves, 0, 0
        if self.book is not None:
            hit = self.book.probe(P, O)
            if hit is not None:
                self.from_book = True
                self.last_depth = hit.depth
                self.last_score = hit.score
                return hit.move, hit.score, hit.depth
        if self._native is not None:
            move, score, depth, self.nodes, self.solved = self._native.search(P, O, self.time_limit, self.max_depth)
            self.last_depth = depth
            self.last_score = score
            return move, score, depth

        n_empty = 64 - (P | O).bit_count()
        best_move, best_score, done_depth = 0, 0, 0
        for depth in range(1, min(self.max_depth, n_empty) + 1):
            self._iter_best = None
            try:
                move, score = self._root(P, O, depth, best_move)
            except SearchTimeout:
                # the previous best move is searched first, so any better move found so far is safe to use
                if self._iter_best is not None and depth > 1:
                    best_move, best_score = self._iter_best
                break
            best_move, best_score, done_depth = move, score, depth
            if depth >= n_empty:
                self.solved = True  # solved to the end of the game
                break
            # with little time left the next depth could not even finish its first move, so stop
            elapsed = time.perf_counter() - start
            if elapsed > self.time_limit * 0.7:
                break
        if best_move == 0:  # fallback if not even depth 1 finished
            best_move = self._ordered(P, O, moves, 0, 0)[0]
        self.last_depth = done_depth
        self.last_score = best_score
        return best_move, best_score, done_depth

    def score_moves(self, P, O, depth):
        """Score every legal move at `depth` (from P's point of view), best first, as [(move, score)].

        Each move is searched with a full window, so this is slower than search() but gives exact scores
        for all moves. Ties are ordered by square index so the result is deterministic.
        """
        if self._native is not None:
            results = self._native.score_moves(P, O, depth)
            self.nodes = self._native.nodes
            return results
        self.tt = {}
        self.nodes = 0
        self._deadline = float("inf")
        results = []
        for x in self._ordered(P, O, legal_moves(P, O), 0, depth):
            f = flips(P, O, x)
            score = -self._negamax(O ^ f, P | x | f, depth - 1, -float("inf"), float("inf"))
            results.append((x, score))
        results.sort(key=lambda t: (-t[1], t[0]))
        return results

    # ---------- same interface as the other AIs ----------
    def get_move(self, board):
        P = board.black if self.color == 1 else board.white
        O = board.white if self.color == 1 else board.black
        if not legal_moves(P, O):
            return None
        x, _, _ = self.search(P, O)
        i = x.bit_length() - 1
        return (i // 8, i % 8)
