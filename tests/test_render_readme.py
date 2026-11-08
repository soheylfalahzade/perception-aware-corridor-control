"""README baseline tables are generated from recorded summaries; these tests pin the generator."""

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from pacc import render_readme as rr

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("corridor_loss_s", "ev_time_s", "other_loss_s")


def _cmp(diff, lo, hi, p_holm):
    return {"mean_diff": diff, "ci95": [lo, hi], "p": p_holm / 2, "p_holm": p_holm, "dz": 1.0}


def _fake(better=("mp_aware_degraded - mp_naive_degraded",), worse=()):
    comps = {}
    pairs = [(c, b) for c in rr.CAMERA for b in rr.BASES]
    pairs.append(("mp_aware_degraded", "mp_naive_degraded"))
    for m in METRICS:
        for cam, base in pairs:
            key = f"{cam} - {base}"
            if key in better:
                c = _cmp(-10.0, -15.0, -5.0, 0.01)
            elif key in worse:
                c = _cmp(+20.0, +15.0, +25.0, 0.01)
            else:
                c = _cmp(+1.0, -2.0, +4.0, 0.9)
            comps[f"{key} | {m}"] = c
    means = {m: {k: 100.0 + i for i, k in enumerate(rr.ORDER)} for m in METRICS}
    return {"n_seeds": 30, "n_comparisons": len(comps), "comparisons": comps, "means": means}


def _data(**kw):
    d = _fake(**kw)
    return {700: d, 900: copy.deepcopy(d)}


def test_classification_and_verdict_rules():
    assert rr.classify(_cmp(-3, -5, -1, 0.01)) == "better"
    assert rr.classify(_cmp(+3, 1, 5, 0.01)) == "worse"
    assert rr.classify(_cmp(-3, -5, -1, 0.05)) == "indistinguishable"  # not below 0.05
    assert rr.classify(_cmp(-3, -5, -1, 0.049)) == "better"
    assert rr.verdict(["better", "better"]) == "supported"
    assert rr.verdict(["worse", "worse"]) == "not supported"
    assert rr.verdict(["indistinguishable", "worse"]) == "not supported"
    assert rr.verdict(["better", "worse"]) == "partially supported"
    assert rr.verdict(["better", "indistinguishable"]) == "partially supported"


def test_claims_block_follows_the_data():
    key = "mp_aware_degraded - mp_naive_degraded"
    claims = rr.block_claims(_data(better=(key,)))
    first = claims.splitlines()[2]
    assert "reliability-aware weighting helps camera-based max-pressure" in first
    assert (
        "**supported**" in first
        and "700 veh/h: -10.0 [-15.0, -5.0] (Holm 0.010) s, better" in first
    )
    mixed = _data(better=(key,))
    mixed[900]["comparisons"][f"{key} | corridor_loss_s"] = _cmp(+2.0, -1.0, +5.0, 0.8)
    assert "**partially supported**" in rr.block_claims(mixed).splitlines()[2]
    bad = rr.block_claims(_data(worse=("aware_degraded - actuated_clear",)))
    row = next(r for r in bad.splitlines() if r.startswith("| ... beat actuated control"))
    assert "**not supported**" in row and "worse" in row


def test_tables_and_reading():
    data = _data()
    means = rr.block_means(data)
    assert "**Corridor flow of 700 vehicles per hour** (mean over 30 seeds)" in means
    assert "| max-pressure, camera + reliability, degraded | 107.0 | 107.0 | 107.0 |" in means
    tests = rr.block_tests(data)
    assert (
        tests.count("| max-pressure, camera + reliability, degraded minus max-pressure, camera,")
        == 2
    )
    assert "(Holm-adjusted p over the 48 comparisons of this level)" in tests
    reading = rr.block_reading(_data(better=("aware_degraded - fixed_clear",)))
    assert "of the 15 comparisons of a camera-based controller with a baseline, 1 favour" in reading
    assert "Primary endpoint (fixed before the confirmatory runs)" in reading
    assert (
        "max-pressure, camera + reliability, degraded minus max-pressure, camera, degraded"
        in reading
    )


def test_render_replaces_every_block_and_is_idempotent():
    text = "".join(f"<!-- BEGIN:{n} -->\nPLACEHOLDER\n<!-- END:{n} -->\n" for n in rr.BLOCKS)
    once = rr.render(text, _data())
    assert "PLACEHOLDER" not in once and rr.render(once, _data()) == once


def test_readme_matches_the_recorded_summaries():
    out = subprocess.run(
        [sys.executable, "-m", "pacc.render_readme", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_readme_documents_blocks_and_confirmatory_seeds():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for n in rr.BLOCKS:
        assert f"<!-- BEGIN:{n} -->" in text and f"<!-- END:{n} -->" in text
    assert "seeds 300 to 329" in text and "--seed0 300" in text


@pytest.mark.parametrize("name", list(rr.BLOCKS))
def test_each_block_renders_from_the_fake_data(name):
    assert rr.BLOCKS[name](_data()).strip()
