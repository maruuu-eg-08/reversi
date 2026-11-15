"""Lv.5: 時間制限つきの強い AI。

Lv.4（AlphaBetaAI）からの主な改良点:
- 盤面を (手番側 P, 相手側 O) の整数ペアで直接扱い、オブジェクトの生成やメソッド呼び出しを減らして高速化
- negamax + PVS（最善候補だけ全幅窓、残りはヌルウィンドウで確認）
- 反復深化 + 時間制限: 制限時間内に読めるところまで読む
- 置換表に最善手を記録し、次の深さの探索で最初に試す（手の並べ替え）
- 速さ優先の並べ替え: 相手の着手可能数が少なくなる手から読む
- 行ごとの重み表を前計算し、位置評価をビットの走査なしで8回の表引きで計算
- 終盤は残りマスまで読み切り、石差を正確に求める（完全読み）
- 評価関数に「開放度（空きマスに接する石の数）」を追加
- 序盤は定石（opening_book.py、事前に深く読んだ手の表）にある局面なら、読まずにその手を打つ

すべて純粋な Python なので、Pyodide（ブラウザ）でもそのまま動く。

探索の部分には Rust 版（backend_rust/、`import reversi_engine`）もある。インストールされていれば
既定で Rust 版を使う（engine="auto"）。固定の深さで読めば Python 版と同じ手・評価値・探索局面数になり、
速さだけが違う（tests/test_rust_engine.py で確認）。
"""

import functools
import os
import time

from weights import POSITION_WEIGHTS, STRONG_EVAL_COEFFS, WIN_SCORE

try:
    import reversi_engine as _native
except ImportError:  # Rust 版をビルドしていない環境（ブラウザ版など）では Python 版だけで動く
    _native = None

ENGINES = ("auto", "rust", "python")

# 同梱のパターン評価の重み（train_patterns.py で学習、設定と精度は pattern_weights.json）
DEFAULT_PATTERNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pattern_weights.bin")


@functools.lru_cache(maxsize=4)
def _load_patterns(path):
    """パターン評価の重みを読み込む（同じファイルは1回だけ）。"""
    from patterns import PatternWeights  # patterns → opening_book → strong_ai の循環を避けるためここで読む

    return PatternWeights.load(path)

MASK64 = 0xFFFFFFFFFFFFFFFF
NOT_EDGE_COLS = 0x7E7E7E7E7E7E7E7E  # a列・h列を除く
NOT_COL_A = 0xFEFEFEFEFEFEFEFE  # 左シフト後に a列へ回り込んだビットを消す
NOT_COL_H = 0x7F7F7F7F7F7F7F7F  # 右シフト後に h列へ回り込んだビットを消す
CORNERS = (1 << 0) | (1 << 7) | (1 << 56) | (1 << 63)

# 評価関数の特徴量の数（位置, 着手可能数, 石数, 開放度）
N_FEATURES = 4


class SearchTimeout(Exception):
    pass


def legal_moves(P, O):
    """手番側 P が打てるマスのビットボード。"""
    empty = ~(P | O) & MASK64
    oh = O & NOT_EDGE_COLS  # 横・斜め方向は端の列の相手石を経由できない（行の回り込み防止）
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
    """P が x（1ビット）に打ったときに裏返る石。"""
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
    """b の8近傍のマス。"""
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
    """各行（8ビット）の石の並び 256 通りについて、重みの合計を前計算する。"""
    tables = []
    for row in range(8):
        table = []
        for pattern in range(256):
            # sum() は使わず、列の小さい順に1つずつ足す。Python 3.12 以降の sum() は誤差を補正する
            # 足し方に変わったため、sum() だと Python のバージョンや Rust 版と最後の桁がずれる
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
        book:     probe(P, O) で定石の手を返すオブジェクト（OpeningBook）。None なら定石を使わない。
        engine:   探索に使う実装。"auto"（Rust 版があれば使う）/ "rust" / "python"
        patterns: パターン評価の重みファイルのパス。指定すると葉の評価にパターン評価を使う
                  （手の並べ替えには引き続き位置の重み weights を使う）。None なら線形評価。
                  "auto" なら、Rust 版で探索する場合だけ同梱の重みを使う（Python 版ではパターン評価が
                  遅すぎるため。ブラウザ版はこれで線形評価のままになる）
        """
        if engine not in ENGINES:
            raise ValueError(f"engine は {ENGINES} のどれかです: {engine!r}")
        if engine == "rust" and _native is None:
            raise ImportError("Rust 版がありません。backend_rust/ で `maturin develop --release` を実行してください")
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
        self.solved = False  # 直前の手が終局まで読み切った結果かどうか
        self.book = book
        self.from_book = False  # 直前の手が定石から選んだものかどうか
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
        """実際に使っている探索の実装（"rust" / "python"）。"""
        return "rust" if self._native is not None else "python"

    # ---------- 評価 ----------
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
        """手番側 P から見た評価値。"""
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
        """終局時の評価（P から見て）。空きマスは勝った側に加える（一般的なルール）。"""
        p = P.bit_count()
        o = O.bit_count()
        empty = 64 - p - o
        if p > o:
            return WIN_SCORE + p - o + empty
        if p < o:
            return -WIN_SCORE + p - o - empty
        return 0

    # ---------- 探索 ----------
    def _check_time(self):
        if time.perf_counter() > self._deadline:
            raise SearchTimeout

    def _ordered(self, P, O, moves, tt_move, depth):
        """探索する手の順番を決める。"""
        lst = []
        while moves:
            x = moves & -moves
            moves ^= x
            lst.append(x)
        if len(lst) > 1:
            if depth >= 3:
                # 速さ優先: 打った後の相手の着手可能数が少ない手から（同数なら重みの高い手）
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
                # PVS: まずヌルウィンドウで「alpha を超えるか」だけ調べ、超えたら読み直す
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
            flag = -1  # 上限値
        elif best >= beta:
            flag = 1  # 下限値
        else:
            flag = 0
        self.tt[key] = (depth, flag, best, best_move)
        return best

    def _root(self, P, O, depth, prev_best):
        """ルートで全手を読み、(最善手, 評価値) を返す。"""
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
                # 途中で時間切れになっても、ここまでに見つけた最善手を使えるよう記録しておく
                self._iter_best = (best_move, alpha)
        return best_move, alpha

    def search(self, P, O):
        """反復深化。時間切れになったら、最後に読み終えた深さの最善手を返す。"""
        self.tt = {}
        self.nodes = 0
        self.solved = False
        self.from_book = False
        start = time.perf_counter()
        self._deadline = start + self.time_limit

        moves = legal_moves(P, O)
        if not moves:
            return 0, 0, 0
        if moves & (moves - 1) == 0:  # 打てる手が1つだけ
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
                # 前回の最善手を最初に読むので、それより良い手が見つかっていれば採用する
                if self._iter_best is not None and depth > 1:
                    best_move, best_score = self._iter_best
                break
            best_move, best_score, done_depth = move, score, depth
            if depth >= n_empty:
                self.solved = True  # 終局まで読み切った
                break
            # 残り時間がわずかなら、次の深さで最初の手すら読み終わらないので始めない
            elapsed = time.perf_counter() - start
            if elapsed > self.time_limit * 0.7:
                break
        if best_move == 0:  # 深さ1すら読み終わらなかった場合の保険
            best_move = self._ordered(P, O, moves, 0, 0)[0]
        self.last_depth = done_depth
        self.last_score = best_score
        return best_move, best_score, done_depth

    def score_moves(self, P, O, depth):
        """全合法手を depth 手先まで読んだ評価値（手番側 P から見た値）を、良い順に [(手, 評価値)] で返す。

        各手を全幅窓で読むので search より遅いが、最善手以外の評価値も正確に分かる。
        同じ評価値の手はマスの番号順に並べ、結果が毎回同じになるようにしている。
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

    # ---------- 他の AI と同じインターフェース ----------
    def get_move(self, board):
        P = board.black if self.color == 1 else board.white
        O = board.white if self.color == 1 else board.black
        if not legal_moves(P, O):
            return None
        x, _, _ = self.search(P, O)
        i = x.bit_length() - 1
        return (i // 8, i % 8)
