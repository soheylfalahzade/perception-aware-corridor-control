import numpy as np
import pandas as pd
import pytest

from pacc.evaluate import paired_ci, summarise
from pacc.fuzzy import G_MAX, G_MIN, green_duration
from pacc.graph import adjacency, backbone_report, dijkstra, greedy_spanner, route
from pacc.perception import EPISODE, Camera, severity


def _grid(n: int) -> dict[tuple[str, str], float]:
    w: dict[tuple[str, str], float] = {}
    for i in range(n):
        for j in range(n):
            if i + 1 < n:
                w[(f"{i}_{j}", f"{i + 1}_{j}")] = 1.0
            if j + 1 < n:
                w[(f"{i}_{j}", f"{i}_{j + 1}")] = 1.0
    return w


def test_dijkstra_finds_shortest_and_reports_unreachable():
    adj = adjacency({("a", "b"): 1.0, ("b", "c"): 1.0, ("a", "c"): 5.0, ("x", "y"): 1.0})
    assert dijkstra(adj, "a", "c") == (2.0, ["a", "b", "c"])
    assert dijkstra(adj, "a", "y")[0] == float("inf")


def test_greedy_spanner_respects_stretch_and_prunes():
    w = _grid(4)
    keep = greedy_spanner(w, 3.0)
    assert len(keep) < len(w)
    sub = {e: w[e] for e in keep}
    for (u, v), wt in w.items():
        assert route(sub, u, v)[0] <= 3.0 * wt + 1e-9
    assert len(greedy_spanner(w, 1.5)) == len(w)          # a grid has no 1.5-spanner shortcut


def test_backbone_report_fields():
    rep = backbone_report(_grid(4), "0_0", "3_3", 3.0)
    assert rep["route_stretch"] >= 1.0 and rep["edges_backbone"] <= rep["edges_full"]


def test_fuzzy_green_follows_the_queue_and_stays_in_bounds():
    assert green_duration(20, 0) > green_duration(0, 20)
    assert green_duration(20, 0) == G_MAX and green_duration(0, 20) == 24.0
    for qs in (0, 5, 30):
        for qc in (0, 5, 30):
            assert G_MIN <= green_duration(qs, qc) <= G_MAX


def test_perception_degrades_inside_the_episode_only():
    mid = sum(EPISODE) / 2
    assert severity(mid, True) > 0 and severity(mid, False) == 0 and severity(0, True) == 0
    rng = np.random.default_rng(0)
    clear = np.mean([Camera(rng).count(20, mid, False) for _ in range(300)])
    bad = np.mean([Camera(rng).count(20, mid, True) for _ in range(300)])
    assert clear == 20 and bad < 14
    cam = Camera(np.random.default_rng(1))
    r = [cam.step(float(t), True) for t in range(300, 400)]
    assert r[-1] < 0.5 < r[0] + 0.5 and r[-1] < r[0]


def test_paired_ci_needs_three_pairs():
    assert np.isnan(paired_ci(np.array([1.0, 2.0]))[0])
    lo, hi = paired_ci(np.array([1.0, 2.0, 3.0, 2.5]))
    assert lo <= 2.125 <= hi


def test_summarise_pairs_each_scenario_with_fixed_time():
    rows = []
    for s in range(5):
        for c, d, loss in (("fixed", False, 100.0), ("oracle", False, 60.0),
                           ("naive", False, 62.0), ("aware", False, 64.0),
                           ("naive", True, 90.0), ("aware", True, 80.0)):
            rows.append({"seed": s, "controller": c, "degraded": d, "ev_time_s": 50.0 + s,
                         "corridor_loss_s": loss + s, "other_loss_s": 30.0})
    out = summarise(pd.DataFrame(rows))
    oracle = out["scenarios"]["oracle_clear"]["corridor_loss_s"]
    assert oracle["delta_vs_fixed"] == pytest.approx(-40)
    assert out["aware_minus_naive_degraded"]["corridor_loss_s"]["mean"] == pytest.approx(-10)
