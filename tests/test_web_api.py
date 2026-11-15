import json

from alphabeta_ai import AlphaBetaAI
from bitboard import BitBoard
from web_api import ai_move, analyze, get_state, new_game, play


def test_new_game_state():
    s = json.loads(new_game())
    assert s["color"] == 1
    assert (s["blackCount"], s["whiteCount"]) == (2, 2)
    assert sorted(map(tuple, s["legal"])) == [(2, 3), (3, 2), (4, 5), (5, 4)]
    assert isinstance(s["black"], str)  # 64ビット値は文字列で受け渡す


def test_play_switches_turn_and_reports_flips():
    s = json.loads(new_game())
    s2 = json.loads(play(s["black"], s["white"], 1, 2, 3))
    assert s2["color"] == -1
    assert s2["flipped"] == [[3, 3]]
    assert (s2["blackCount"], s2["whiteCount"]) == (4, 1)


def test_play_rejects_illegal_move():
    s = json.loads(new_game())
    assert "error" in json.loads(play(s["black"], s["white"], 1, 0, 0))


def test_large_bitboards_roundtrip():
    b = BitBoard()
    b.black = (1 << 63) | (1 << 62)
    b.white = 1 << 61
    s = json.loads(get_state(str(b.black), str(b.white), -1))
    assert int(s["black"]) == b.black
    assert s["legal"] == []


def test_ai_move_is_legal():
    s = json.loads(new_game())
    r = json.loads(ai_move(s["black"], s["white"], 1, "4", 3))
    assert r["move"] in s["legal"]
    assert r["nodes"] > 0


def test_analyze_best_move_matches_get_move_score():
    s = json.loads(new_game())
    s = json.loads(play(s["black"], s["white"], 1, 2, 3))
    res = json.loads(analyze(s["black"], s["white"], -1, 3))
    assert {(m["row"], m["col"]) for m in res["moves"]} == set(map(tuple, s["legal"]))
    scores = [m["score"] for m in res["moves"]]
    assert scores == sorted(scores, reverse=True)

    # analyze の最高点の手は、get_move が選ぶ手と同じ点数になる
    b = BitBoard()
    b.black, b.white = int(s["black"]), int(s["white"])
    ai = AlphaBetaAI(-1, max_depth=3)
    best = ai.get_move(b)
    best_score = next(m["score"] for m in res["moves"] if (m["row"], m["col"]) == best)
    assert best_score == scores[0]


def test_analyze_reports_forced_win():
    b = BitBoard()
    b.black, b.white = 1 << 1, 1 << 0  # 白(0,0) 黒(0,1): 白が(0,2)に打てば全滅で勝ち
    res = json.loads(analyze(str(b.black), str(b.white), -1, 2))
    assert res["moves"][0]["outcome"] == "win"
    assert res["moves"][0]["discDiff"] == 3


def test_ai_move_level5_reports_depth():
    s = json.loads(new_game())
    r = json.loads(ai_move(s["black"], s["white"], 1, "5", 4, 0.2))
    assert r["move"] in s["legal"]
    assert r["depth"] >= 2
    assert r["solved"] is False


def test_opening_names():
    from web_api import opening

    assert json.loads(opening("f5d6c3d3c4"))["name"] == "虎（Tiger）"
    assert json.loads(opening("f5d6"))["name"] == "縦取り（Perpendicular Opening）"
    assert json.loads(opening(""))["name"] is None
    assert json.loads(opening("a1"))["name"] is None  # 不正な初手
    assert json.loads(opening("zz"))["name"] is None  # 不正な表記


def test_ai_move_reports_book_flag():
    s = json.loads(new_game())
    r = json.loads(ai_move(s["black"], s["white"], 1, "4", 2))
    assert r["book"] is False  # Lv.4 は定石を使わない
