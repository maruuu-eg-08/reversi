"""Self-play data generation (needs the Rust engine; skipped without it)."""

import os

import pytest

pytest.importorskip("reversi_engine")

from gen_data import RECORD_SIZE, generate, read_records  # noqa: E402
from strong_ai import legal_moves  # noqa: E402

SMALL = dict(games=8, depth=2, random_min=4, random_max=10, solve_empties=8, seed=3, threads=4, batch=3)


def quiet(*_):
    pass


def test_generation_is_deterministic(tmp_path):
    a = generate(str(tmp_path / "a.bin"), log=quiet, **SMALL)
    b = generate(str(tmp_path / "b.bin"), log=quiet, **{**SMALL, "threads": 1, "batch": 8})
    assert open(a, "rb").read() == open(b, "rb").read()


def test_records_are_valid(tmp_path):
    params, records = read_records(generate(str(tmp_path / "d.bin"), log=quiet, **SMALL))
    assert params["games"] == SMALL["games"]
    assert {r[4] for r in records} == set(range(SMALL["games"]))
    # that labels are exact final disc differences is tested on the Rust side (selfplay.rs)
    for P, O, score, _, _ in records:
        assert P & O == 0 and legal_moves(P, O)
        assert -64 <= score <= 64


def test_resume_after_interruption(tmp_path):
    full = generate(str(tmp_path / "full.bin"), log=quiet, **SMALL)
    part = str(tmp_path / "part.bin")
    data = open(full, "rb").read()
    # simulate an interruption in the middle of a record
    with open(part, "wb") as f:
        f.write(data[: len(data) * 2 // 3 + 5])
    generate(part, log=quiet, **SMALL)
    assert open(part, "rb").read() == data


def test_resume_rejects_different_settings(tmp_path):
    path = generate(str(tmp_path / "x.bin"), log=quiet, **SMALL)
    with pytest.raises(SystemExit):
        generate(path, log=quiet, **{**SMALL, "depth": 3})
    assert os.path.getsize(path) > RECORD_SIZE


def test_training_produces_weights_that_python_and_rust_agree_on(tmp_path):
    import reversi_engine

    from patterns import PatternWeights
    from train_patterns import train

    data = generate(str(tmp_path / "d.bin"), log=quiet, **{**SMALL, "games": 40})
    out = str(tmp_path / "w.bin")
    reports = train(data, out, lam=1.0, max_iter=30, valid_every=4, threads=2)
    assert len(reports) == 15
    assert all(r["n_train"] + r["n_valid"] > 0 for r in reports[:12])
    assert os.path.exists(out + ".json")
    w = PatternWeights.load(out)
    rust = reversi_engine.PatternEval(out)
    _, records = read_records(data)
    for P, O, *_ in records[::7]:
        assert rust.evaluate(P, O) == w.evaluate(P, O, legal_moves(P, O), legal_moves(O, P))
