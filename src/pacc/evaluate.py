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
from pacc.sim import Job, make_routes, run_one

SCENARIOS = (("fixed", False), ("oracle", False), ("naive", False), ("aware", False),
             ("naive", True), ("aware", True))


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
    ap.add_argument("--trace", action="store_true",
                    help="also write the time, stopped time and queue ahead per edge of the EV")
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
        jobs = [Job(args.net, routes[s], args.add, s, c, d, ev_edges, controlled, args.trace)
                for s in seeds for c, d in SCENARIOS]
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
    summary["backbone"] = report
    summary["route_mode"] = args.route_mode
    summary["route_junctions"] = list(path)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
