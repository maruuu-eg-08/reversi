import random
from array import array

import pytest

from opening_book import N_SYMMETRIES, transform
from patterns import (
    FAMILIES,
    FAMILY_OFFSETS,
    FAMILY_SIZES,
    INSTANCES,
    N_STAGES,
    SCALE,
    TABLE_SIZE,
    PatternWeights,
    indices,
    stage_of,
)
from strong_ai import flips, legal_moves

START = (0x0000000810000000, 0x0000001008000000)


def random_position(rng, plies):
    P, O = START
    for _ in range(plies):
        moves = legal_moves(P, O)
        if not moves:
            if not legal_moves(O, P):
                break
            P, O = O, P
            continue
        x = rng.choice([1 << i for i in range(64) if moves >> i & 1])
        f = flips(P, O, x)
        P, O = O ^ f, P | x | f
    return P, O


def random_weights(rng):
    stages = []
    for _ in range(N_STAGES):
        table = array("h", (rng.randint(-2000, 2000) for _ in range(TABLE_SIZE)))
        stages.append((rng.randint(-500, 500), rng.randint(-100, 100), table))
    return PatternWeights(stages)


def evaluate(w, P, O):
    return w.evaluate(P, O, legal_moves(P, O), legal_moves(O, P))


def test_layout():
    assert len(INSTANCES) == 84  # 対角線は4通り、ほかの10種類は8通り
    assert TABLE_SIZE == 167_265
    assert FAMILY_OFFSETS[-1] + FAMILY_SIZES[-1] == TABLE_SIZE
    for fam, squares in INSTANCES:
        assert len(set(squares)) == len(squares) == len(FAMILIES[fam][1].split())


def test_stage_boundaries():
    assert [stage_of(n) for n in (60, 57, 56, 53, 52, 4, 0)] == [0, 0, 1, 1, 2, 14, 14]


def test_index_digits():
    # 盤面が空なら全インスタンスの番号は 0、全部手番側なら Σ 3^k、全部相手なら 2 × Σ 3^k
    assert indices(0, 0) == [0] * len(INSTANCES)
    full = 0xFFFFFFFFFFFFFFFF
    assert indices(full, 0) == [(3 ** len(sq) - 1) // 2 for _, sq in INSTANCES]
    assert indices(0, full) == [3 ** len(sq) - 1 for _, sq in INSTANCES]


def test_instances_are_closed_under_symmetry():
    """盤面を回転・反転すると、(パターン, 並びの番号) の多重集合がそのまま入れ替わるだけになる。"""
    rng = random.Random(0)
    for _ in range(50):
        P, O = random_position(rng, rng.randint(0, 55))
        base = sorted(zip((f for f, _ in INSTANCES), indices(P, O), strict=True))
        for s in range(N_SYMMETRIES):
            tP, tO = transform(P, s), transform(O, s)
            assert sorted(zip((f for f, _ in INSTANCES), indices(tP, tO), strict=True)) == base


def test_evaluation_is_exactly_symmetric_for_any_weights():
    rng = random.Random(1)
    w = random_weights(rng)
    for _ in range(30):
        P, O = random_position(rng, rng.randint(0, 55))
        v = evaluate(w, P, O)
        for s in range(N_SYMMETRIES):
            assert evaluate(w, transform(P, s), transform(O, s)) == v


def test_evaluation_is_sum_of_parts():
    rng = random.Random(2)
    w = random_weights(rng)
    P, O = random_position(rng, 20)
    bias, mobility, table = w.stages[stage_of(64 - (P | O).bit_count())]
    expected = bias + mobility * (legal_moves(P, O).bit_count() - legal_moves(O, P).bit_count())
    expected += sum(table[FAMILY_OFFSETS[f] + i] for (f, _), i in zip(INSTANCES, indices(P, O), strict=True))
    assert evaluate(w, P, O) == expected / SCALE


def test_save_and_load_round_trip(tmp_path):
    w = random_weights(random.Random(3))
    path = tmp_path / "w.bin"
    w.save(path)
    loaded = PatternWeights.load(path)
    for (b1, m1, t1), (b2, m2, t2) in zip(w.stages, loaded.stages, strict=True):
        assert (b1, m1) == (b2, m2)
        assert t1 == t2


def test_load_rejects_bad_files(tmp_path):
    good = tmp_path / "w.bin"
    PatternWeights().save(good)
    data = good.read_bytes()
    for name, content in [("magic", b"XXXXXX" + data[6:]), ("short", data[:-2]), ("long", data + b"\0\0")]:
        bad = tmp_path / f"{name}.bin"
        bad.write_bytes(content)
        with pytest.raises(ValueError):
            PatternWeights.load(bad)


def test_constructor_validates_shape():
    with pytest.raises(ValueError):
        PatternWeights([(0, 0, array("h", [0]))] * N_STAGES)
