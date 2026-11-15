import random

import pytest

from build_book import START, Settings, build
from opening_book import N_SYMMETRIES, canonical, inverse_transform, transform
from strong_ai import StrongAI, flips, legal_moves

# 小さな設定で、テストが数秒で終わるようにする
SMALL = Settings(depth=3, full_plies=3, plies=6, replies=2, rank_depth=2)


@pytest.fixture(scope="module")
def small_book():
    return build(SMALL, processes=2, log=lambda *_: None)


def _play(P, O, x):
    f = flips(P, O, x)
    return O ^ f, P | x | f


def _all_moves(m):
    return [1 << i for i in range(64) if m >> i & 1]


def _positions_up_to(plies):
    """開始局面から plies 手以内に現れるすべての局面。"""
    level = {START}
    out = set(level)
    for _ in range(plies):
        nxt = set()
        for P, O in level:
            for x in _all_moves(legal_moves(P, O)):
                nxt.add(_play(P, O, x))
        out |= nxt
        level = nxt
    return out


def test_every_position_within_full_plies_is_in_book(small_book):
    for P, O in _positions_up_to(SMALL.full_plies):
        if legal_moves(P, O) & (legal_moves(P, O) - 1):  # 合法手が2つ以上ある局面
            assert small_book.probe(P, O) is not None


def test_book_moves_match_a_fixed_depth_search(small_book):
    """定石の手は、同じ深さで読んだ最善手と一致する（どの向きの局面でも）。"""
    rng = random.Random(0)
    positions = sorted(_positions_up_to(SMALL.full_plies))
    for P, O in rng.sample(positions, 15):
        if not legal_moves(P, O) & (legal_moves(P, O) - 1):
            continue
        s = rng.randrange(N_SYMMETRIES)
        tP, tO = transform(P, s), transform(O, s)
        hit = small_book.probe(tP, tO)
        move, _, _ = StrongAI(1, time_limit=float("inf"), max_depth=SMALL.depth).search(tP, tO)
        # 対称な局面では同じ価値の手が複数あり得るので、評価値が等しいことを確かめる
        scores = dict(StrongAI(1, time_limit=float("inf"), max_depth=SMALL.depth).score_moves(tP, tO, SMALL.depth))
        assert scores[hit.move] == pytest.approx(scores[move])


@pytest.mark.parametrize("ai_is_black", [True, False])
def test_book_covers_games_where_ai_follows_book(small_book, ai_is_black):
    """AI が定石どおりに打ち、相手が有力な手を打つ限り、AI の番の局面は定石に載っている。"""
    rng = random.Random(1 if ai_is_black else 2)
    for _ in range(20):
        P, O = START
        ai_to_move = ai_is_black
        for ply in range(SMALL.plies):
            moves = legal_moves(P, O)
            if not moves:
                break
            if ai_to_move:
                hit = small_book.probe(P, O)
                if moves & (moves - 1):
                    assert hit is not None, f"ply {ply} で定石が見つからない"
                x = hit.move if hit else moves
            elif ply < SMALL.full_plies:
                x = rng.choice(_all_moves(moves))  # 序盤は相手がどんな手を打ってもよい
            else:
                # 生成時と同じく正規形の向きで順位を付ける（同点の手の並びが向きに左右されないように）
                cP, cO, s = canonical(P, O)
                ranked = StrongAI(1, time_limit=float("inf")).score_moves(cP, cO, SMALL.rank_depth)
                x = inverse_transform(rng.choice([m for m, _ in ranked[: SMALL.replies]]), s)
            P, O = _play(P, O, x)
            ai_to_move = not ai_to_move


def test_build_is_deterministic_and_resumable(tmp_path):
    settings = Settings(depth=2, full_plies=2, plies=4, replies=2, rank_depth=1)
    cache = tmp_path / "cache.txt"
    a = build(settings, processes=1, cache_path=str(cache), log=lambda *_: None)
    lines = cache.read_text().splitlines()
    assert lines  # 読んだ結果がキャッシュに書かれている
    # 途中で中断した状態（キャッシュの後半がない、最後の行が書きかけ）から再開しても同じ結果になる
    cache.write_text("\n".join(lines[: len(lines) // 2]) + "\n" + lines[-1][:10])
    b = build(settings, processes=1, cache_path=str(cache), log=lambda *_: None)
    c = build(settings, processes=2, log=lambda *_: None)
    pa, pb, pc = tmp_path / "a.txt", tmp_path / "b.txt", tmp_path / "c.txt"
    a.save(pa)
    b.save(pb)
    c.save(pc)
    assert pa.read_text() == pb.read_text() == pc.read_text()
