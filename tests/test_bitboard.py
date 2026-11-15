import random

import pytest

from bitboard import BitBoard

DIRECTIONS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def make_board(black=(), white=()):
    b = BitBoard()
    b.black = sum(1 << (r * 8 + c) for r, c in black)
    b.white = sum(1 << (r * 8 + c) for r, c in white)
    return b


# ---- ビット演算を使わない素朴な参照実装（正解データ用） ----
def naive_flips(grid, row, col, color):
    if grid[row][col] != 0:
        return []
    flips = []
    for dr, dc in DIRECTIONS:
        r, c = row + dr, col + dc
        line = []
        while 0 <= r < 8 and 0 <= c < 8 and grid[r][c] == -color:
            line.append((r, c))
            r, c = r + dr, c + dc
        if line and 0 <= r < 8 and 0 <= c < 8 and grid[r][c] == color:
            flips.extend(line)
    return flips


def naive_moves(grid, color):
    return sorted((r, c) for r in range(8) for c in range(8) if naive_flips(grid, r, c, color))


def perft(board, color, depth, passed=False):
    """depth 手先までの局面数を数える（パスも1手として数える）。"""
    if depth == 0:
        return 1
    moves = board.listUp(color)
    if not moves:
        return 1 if passed else perft(board, -color, depth - 1, True)
    total = 0
    for r, c in moves:
        ob, ow = board.black, board.white
        board.put_disc(r, c, color)
        total += perft(board, -color, depth - 1)
        board.black, board.white = ob, ow
    return total


def test_initial_position():
    b = BitBoard()
    assert b.count_discs(1) == 2
    assert b.count_discs(-1) == 2
    assert b.grid[3, 3] == -1 and b.grid[4, 4] == -1
    assert b.grid[3, 4] == 1 and b.grid[4, 3] == 1
    assert sorted(b.listUp(1)) == [(2, 3), (3, 2), (4, 5), (5, 4)]


def test_put_disc_flips_stones():
    b = BitBoard()
    assert b.put_disc(2, 3, 1)
    assert b.grid[3, 3] == 1
    assert b.count_discs(1) == 4
    assert b.count_discs(-1) == 1


@pytest.mark.parametrize("row,col", [(0, 0), (3, 3), (2, 2)])
def test_illegal_move_leaves_board_unchanged(row, col):
    b = BitBoard()
    before = (b.black, b.white)
    assert b.put_disc(row, col, 1) is False
    assert (b.black, b.white) == before


def test_no_wraparound_between_rows():
    # 黒(0,7)の右隣はビット上は(1,0)。行をまたいで挟めてはいけない
    b = make_board(black=[(0, 7)], white=[(1, 0)])
    assert (1, 1) not in b.listUp(1)
    assert b.get_flip_mask(1, 1, 1) == 0


def test_both_players_pass_means_game_over():
    b = make_board(black=[(0, 0), (0, 1)])
    assert not b.has_valid_move(1)
    assert not b.has_valid_move(-1)


def test_pass_when_only_opponent_can_move():
    # 白は (0,2) に打って黒(0,1)を挟めるが、黒はどこにも打てない
    b = make_board(black=[(0, 1)], white=[(0, 0)])
    assert not b.has_valid_move(1)
    assert b.listUp(-1) == [(0, 2)]


# 既知の perft 値（オセロ初期局面から）
@pytest.mark.parametrize(
    "depth,expected",
    [(1, 4), (2, 12), (3, 56), (4, 244), (5, 1396), (6, 8200)],
)
def test_perft(depth, expected):
    assert perft(BitBoard(), 1, depth) == expected


def test_matches_naive_implementation_on_random_games():
    """ランダム対局 200 局で、合法手と反転結果が素朴な実装と一致することを確認する。"""
    rng = random.Random(42)
    for _ in range(200):
        b = BitBoard()
        color = 1
        while True:
            grid = b.grid.tolist()
            moves = naive_moves(grid, color)
            assert sorted(b.listUp(color)) == moves
            if not moves:
                if not naive_moves(grid, -color):
                    break
                color = -color
                continue
            r, c = rng.choice(moves)
            flips = naive_flips(grid, r, c, color)
            b.put_disc(r, c, color)
            after = b.grid
            assert after[r, c] == color
            for fr, fc in flips:
                assert after[fr, fc] == color
            assert b.count_discs(1) + b.count_discs(-1) == sum(cell != 0 for row in grid for cell in row) + 1
            color = -color
