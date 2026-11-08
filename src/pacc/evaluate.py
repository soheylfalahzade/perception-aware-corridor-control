"""Run the corridor study over seeds and summarise it with paired bootstrap intervals."""
from __future__ import annotations

import argparse
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from pacc.graph import edge_ids, greedy_spanner, load_grid, route, route_comparison
from pacc.sim import PREEMPT_M, Job, make_routes, run_one

SCENARIOS = (("fixed", False), ("oracle", False), ("naive", False), ("aware", False),
             ("naive", True), ("aware", True))
BASELINES = (("actuated", False), ("maxpressure", False), ("mp_naive", True), ("mp_aware", True))
METRICS = ("ev_time_s", "corridor_loss_s", "other_loss_s")


def paired_ci(diff: np.ndarray, n_boot: int = 2000, seed: int = 0) -> list[float]:
    """Percentile bootstrap 95% interval of the mean of paired differences."""
    d = diff[~np.isnan(diff)]
    if len(d) < 3:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    m = rng.choice(d, size=(n_boot, len(d)), replace=True).mean(axis=1)
    return [float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))]


def summarise(df: pd.DataFrame) -> dict:
    """Means per scenario, differences against fixed-time, and aware against naive."""
    df = df.assign(key=df.controller + np.where(df.degraded, "_degraded", "_clear"))
    out: dict = {"n_seeds": int(df.seed.nunique()), "scenarios": {}}
    metrics = ("ev_time_s", "corridor_loss_s", "other_loss_s")
    piv = {m: df.pivot(index="seed", columns="key", values=m) for m in metrics}
    base = df[df.controller == "fixed"].set_index("seed")
    for key in piv["ev_time_s"].columns:
        row: dict = {}
        for m in metrics:
            v = piv[m][key]
            d = (v - base[m]).to_numpy()
            row[m] = {"mean": float(v.mean()), "delta_vs_fixed": float(np.nanmean(d)),
                      "delta_ci95": paired_ci(d)}
        out["scenarios"][key] = row
    for cond in ("clear", "degraded"):
        a, n = f"aware_{cond}", f"naive_{cond}"
        if a in piv["ev_time_s"] and n in piv["ev_time_s"]:
            out[f"aware_minus_naive_{cond}"] = {
                m: {"mean": float(np.nanmean((piv[m][a] - piv[m][n]).to_numpy())),
                    "ci95": paired_ci((piv[m][a] - piv[m][n]).to_numpy())} for m in metrics}
    return out


def sign_flip_p(diff: np.ndarray, n_mc: int = 200_000, seed: int = 0) -> float:
    """Two-sided paired sign-flip permutation test of a zero mean difference.

    Exact (all 2^n sign patterns) for n <= 16, otherwise ``n_mc`` random patterns with a fixed seed.
    """
    d = diff[~np.isnan(diff)]
    n = len(d)
    if n < 3 or not np.any(d):
        return float("nan") if n < 3 else 1.0
    obs = abs(d.mean())
    if n <= 16:
        signs = (((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1) * 2 - 1).astype(float)
        flips = np.abs((signs * d).mean(axis=1))
        return float(np.mean(flips >= obs - 1e-12))
    rng = np.random.default_rng(seed)
    flips = np.abs((rng.choice([-1.0, 1.0], size=(n_mc, n)) * d).mean(axis=1))
    return float((1 + np.sum(flips >= obs - 1e-12)) / (1 + n_mc))


def holm(p: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjustment of a dictionary of p-values."""
    order = sorted(p, key=lambda k: p[k])
    adj: dict[str, float] = {}
    run = 0.0
    for i, k in enumerate(order):
        run = max(run, min(1.0, (len(order) - i) * p[k]))
        adj[k] = run
    return adj


CAMERA_KEYS = ("oracle_clear", "naive_degraded", "aware_degraded", "mp_naive_degraded",
               "mp_aware_degraded")
SPECIAL_PAIRS = (("mp_aware_degraded", "mp_naive_degraded"),)
BASELINE_KEYS = ("fixed_clear", "actuated_clear", "maxpressure_clear")


def summarise_baselines(df: pd.DataFrame) -> dict:
    """Camera-based fuzzy controllers against fixed-time, actuated and max-pressure control.

    Each comparison is the paired difference (camera-based minus baseline) over seeds, with a
    percentile bootstrap interval, a paired sign-flip p-value, Cohen's dz, and the Holm-adjusted
    p-value over all comparisons and metrics of this study.
    """
    df = df.assign(key=df.controller + np.where(df.degraded, "_degraded", "_clear"))
    piv = {m: df.pivot(index="seed", columns="key", values=m) for m in METRICS}
    rows: dict[str, dict] = {}
    pairs = [(c, b) for c in CAMERA_KEYS for b in BASELINE_KEYS] + list(SPECIAL_PAIRS)
    for m in METRICS:
        for cam, base in pairs:
            if cam not in piv[m] or base not in piv[m]:
                continue
            d = (piv[m][cam] - piv[m][base]).to_numpy()
            sd = float(np.nanstd(d, ddof=1))
            rows[f"{cam} - {base} | {m}"] = {
                "mean_diff": float(np.nanmean(d)), "ci95": paired_ci(d), "p": sign_flip_p(d),
                "dz": float(np.nanmean(d) / sd) if sd > 0 else float("nan")}
    adj = holm({k: v["p"] for k, v in rows.items()})
    for k in rows:
        rows[k]["p_holm"] = adj[k]
    return {"n_seeds": int(df.seed.nunique()), "n_comparisons": len(rows), "comparisons": rows,
            "means": {m: {k: float(piv[m][k].mean()) for k in piv[m].columns} for m in METRICS}}


def summarise_trace(tr: pd.DataFrame) -> pd.DataFrame:
    """Mean time, stopped time and vehicles ahead per edge of the emergency vehicle's route,
    for each controller and perception condition, in route order."""
    key = tr.controller + np.where(tr.degraded, "_degraded", "_clear")
    g = tr.assign(key=key).groupby(["edge", "key"]).agg(
        entry_s=("entry_s", "mean"), time_s=("time_s", "mean"),
        stopped_s=("stopped_s", "mean"), mean_ahead=("mean_ahead", "mean"),
        n=("seed", "nunique")).reset_index()
    order = g.groupby("edge").entry_s.mean().sort_values().index
    g["edge"] = pd.Categorical(g.edge, categories=order, ordered=True)
    return g.sort_values(["edge", "key"]).drop(columns="entry_s").reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (``pacc-eval``)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--net", default="examples/grid5.net.xml")
    ap.add_argument("--add", default="examples/ev.add.xml")
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--seed0", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--origin", default="A0")
    ap.add_argument("--dest", default="E4")
    ap.add_argument("--stretch", type=float, default=3.0, help="spanner stretch t")
    ap.add_argument("--route-mode", choices=("backbone", "shortest"), default="backbone",
                    help="route of the emergency vehicle and the corridor flow")
    ap.add_argument("--preempt-m", type=float, default=PREEMPT_M,
                    help="distance before the stop line at which the signal turns green for the EV")
    ap.add_argument("--replay", default="",
                    help="perception table of real footage (scripts/build_replay.py); "
                         "empty keeps the emulated camera")
    ap.add_argument("--replay-cond", default="night", help="degradation replayed in the episode")
    ap.add_argument("--trace", action="store_true",
                    help="also write the time, stopped time and queue ahead per edge of the EV")
    ap.add_argument("--baselines", action="store_true",
                    help="also run actuated and max-pressure control (true detector counts) and "
                         "compare the camera-based controllers with them")
    ap.add_argument("--corridor-vph", type=float, default=700.0,
                    help="demand along the corridor route (vehicles per hour)")
    ap.add_argument("--out", default="results/eval")
    args = ap.parse_args(argv)
    weights, directed = load_grid(args.net)
    keep = greedy_spanner(weights, args.stretch)
    report = route_comparison(weights, args.origin, args.dest, args.stretch)
    if args.route_mode == "backbone":
        _, path = route({e: weights[e] for e in keep}, args.origin, args.dest)
    else:
        _, path = route(weights, args.origin, args.dest)
    ev_edges = tuple(edge_ids(path, directed))
    controlled = tuple(path[1:-1])
    with tempfile.TemporaryDirectory() as tmp:
        seeds = range(args.seed0, args.seed0 + args.seeds)
        routes = {s: make_routes(args.net, s, Path(tmp) / f"s{s}.rou.xml", ev_edges,
                                corridor_vph=args.corridor_vph) for s in seeds}
        jobs = [Job(args.net, routes[s], args.add, s, c, d, ev_edges, controlled, args.trace,
                    args.preempt_m, args.replay, args.replay_cond)
                for s in seeds for c, d in SCENARIOS + (BASELINES if args.baselines else ())]
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(run_one, jobs))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.trace:
        tr = pd.DataFrame([r for row in rows for r in row["trace"]])
        tr.to_csv(out / "edge_trace.csv", index=False)
        summarise_trace(tr).to_csv(out / "edge_summary.csv", index=False)
    df = pd.DataFrame([{k: v for k, v in row.items() if k != "trace"} for row in rows])
    df.to_csv(out / "runs.csv", index=False)
    summary = summarise(df)
    if args.baselines:
        summary["against_baselines"] = summarise_baselines(df)
    summary["backbone"] = report
    summary["route_mode"] = args.route_mode
    summary["perception"] = ({"replay": args.replay, "cond": args.replay_cond} if args.replay
                             else "emulated")
    summary["route_junctions"] = list(path)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
