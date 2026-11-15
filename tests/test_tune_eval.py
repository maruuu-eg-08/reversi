import random

import pytest

from strong_ai import N_FEATURES, StrongAI, legal_moves
from tune_eval import features, fit, phase_of, self_play


@pytest.mark.parametrize("seed", range(5))
def test_features_match_evaluate(seed):
    """Features dotted with coefficients equal the search evaluation (so learned values can be used as is)."""
    rng = random.Random(seed)
    coeffs = [rng.uniform(-2, 2) for _ in range(3 * N_FEATURES)]
    ai = StrongAI(1, eval_coeffs=coeffs)
    for P, O in _random_positions(seed):
        n_empty = 64 - (P | O).bit_count()
        base = phase_of(n_empty) * N_FEATURES
        expected = sum(c * f for c, f in zip(coeffs[base:base + N_FEATURES], features(ai, P, O), strict=True))
        assert ai.evaluate(P, O) == pytest.approx(expected)


def _random_positions(seed):
    from strong_ai import flips

    rng = random.Random(seed)
    P, O = 0x0000000810000000, 0x0000001008000000
    out = []
    for _ in range(50):
        moves = legal_moves(P, O)
        if not moves:
            P, O = O, P
            if not legal_moves(P, O):
                break
            continue
        out.append((P, O))
        lst = [1 << i for i in range(64) if (moves >> i) & 1]
        x = rng.choice(lst)
        f = flips(P, O, x)
        P, O = O ^ f, P | x | f
    return out


def test_self_play_labels_are_consistent():
    """Every label from one game is that game's final disc difference (signed for the side to move)."""
    records = self_play((0, 1, 4, 0.0, None))
    assert records
    finals = {abs(t) for _, _, t in records}
    assert len(finals) == 1  # all from the same final result
    assert all(len(f) == N_FEATURES for _, f, _ in records)


def test_fit_recovers_linear_relationship():
    rng = random.Random(0)
    true = [0.5, -1.0, 2.0, 0.25]
    samples = []
    for ph in range(3):
        for _ in range(200):
            f = tuple(rng.uniform(-10, 10) for _ in range(N_FEATURES))
            samples.append((ph, f, sum(a * b for a, b in zip(true, f, strict=True))))
    coeffs = fit(samples)
    for ph in range(3):
        assert coeffs[ph * N_FEATURES:(ph + 1) * N_FEATURES] == pytest.approx(true, abs=1e-6)
