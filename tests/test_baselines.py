"""Tests of the paired statistics and of the baseline controllers' registration."""

import itertools

import numpy as np
import pandas as pd
import pytest

from pacc.evaluate import (
    BASELINES,
    SCENARIOS,
    holm,
    paired_ci,
    sign_flip_p,
    summarise_baselines,
)
from pacc.sim import CONTROLLERS


def test_controllers_and_scenarios_are_registered():
    assert {
        "fixed",
        "oracle",
        "naive",
        "aware",
        "actuated",
        "maxpressure",
        "mp_naive",
        "mp_aware",
    } == set(CONTROLLERS)
    assert {c for c, _ in BASELINES} == {"actuated", "maxpressure", "mp_naive", "mp_aware"}
    assert dict(BASELINES)["mp_naive"] is True and dict(BASELINES)["mp_aware"] is True
    assert not set(BASELINES) & set(SCENARIOS)  # the original study is unchanged


def test_sign_flip_is_exact_for_small_samples():
    d = np.array([1.0, 2.0, 3.0, 4.0])
    # every sign pattern is enumerated: only +,+,+,+ and -,-,-,- reach |mean| = 2.5
    assert sign_flip_p(d) == pytest.approx(2 / 16)
    brute = np.mean(
        [abs(np.dot(s, d) / 4) >= 2.5 - 1e-12 for s in itertools.product([-1, 1], repeat=4)]
    )
    assert sign_flip_p(d) == pytest.approx(brute)


def test_sign_flip_edge_cases_and_monte_carlo_agreement():
    assert np.isnan(sign_flip_p(np.array([1.0, 2.0])))
    assert sign_flip_p(np.zeros(8)) == 1.0
    assert sign_flip_p(np.array([np.nan, 1.0, -1.0, 2.0, -2.0])) == pytest.approx(1.0)
    rng = np.random.default_rng(0)
    big = rng.normal(0.9, 1.0, 40)  # 40 > 16: Monte Carlo branch
    assert sign_flip_p(big) < 0.001
    assert sign_flip_p(big, seed=1) == pytest.approx(sign_flip_p(big, seed=2), abs=2e-4)
    null = rng.normal(0.0, 1.0, 40)
    assert 0.05 < sign_flip_p(null) <= 1.0


def test_holm_adjustment():
    adj = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert holm({"x": 0.9}) == {"x": 0.9}
    assert all(0.0 <= v <= 1.0 for v in holm({"a": 0.5, "b": 0.7, "c": 0.99}).values())


def _runs(n_seeds=20):
    rng = np.random.default_rng(3)
    rows = []
    cell = {
        ("fixed", False): 130,
        ("oracle", False): 138,
        ("naive", True): 140,
        ("aware", True): 120,
        ("actuated", False): 66,
        ("maxpressure", False): 45,
        ("mp_naive", True): 60,
        ("mp_aware", True): 48,
    }
    for seed in range(200, 200 + n_seeds):
        noise = rng.normal(0, 3)
        for (c, dg), base in cell.items():
            rows.append(
                dict(
                    seed=seed,
                    controller=c,
                    degraded=dg,
                    ev_time_s=130 + noise,
                    corridor_loss_s=base + noise + rng.normal(0, 2),
                    other_loss_s=60 + rng.normal(0, 2),
                )
            )
    return pd.DataFrame(rows)


def test_summarise_baselines_signs_and_correction():
    out = summarise_baselines(_runs())
    assert out["n_seeds"] == 20
    assert out["n_comparisons"] == 48  # 3 metrics x (5 camera-based x 3 baselines + 1 pair)
    pair = out["comparisons"]["mp_aware_degraded - mp_naive_degraded | corridor_loss_s"]
    assert pair["mean_diff"] == pytest.approx(-12, abs=3) and pair["ci95"][1] < 0
    key = "aware_degraded - actuated_clear | corridor_loss_s"
    c = out["comparisons"][key]
    assert c["mean_diff"] == pytest.approx(54, abs=3) and c["ci95"][0] > 0 and c["p"] < 0.001
    assert c["p_holm"] >= c["p"] and c["dz"] > 3
    low = out["comparisons"]["aware_degraded - fixed_clear | corridor_loss_s"]
    assert low["mean_diff"] == pytest.approx(-10, abs=3) and low["ci95"][1] < 0
    for v in out["comparisons"].values():
        assert 0.0 <= v["p_holm"] <= 1.0 and v["p_holm"] >= v["p"] - 1e-12


def test_paired_ci_brackets_the_mean():
    d = np.random.default_rng(1).normal(5, 2, 30)
    lo, hi = paired_ci(d)
    assert lo < d.mean() < hi
