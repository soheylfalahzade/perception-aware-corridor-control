"""Figure of the corridor study (``pacc-figures``)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ORDER = (("oracle_clear", "true counts"), ("naive_clear", "camera, clear"),
         ("aware_clear", "camera + reliability, clear"), ("naive_degraded", "camera, degraded"),
         ("aware_degraded", "camera + reliability, degraded"))
COL = {"oracle": "#7a8ba0", "naive": "#e15759", "aware": "#4c78a8"}


def plot_summary(summaries: dict[str, dict], out: str | Path) -> None:
    """Change against fixed-time control (paired, 95% interval) for each demand level."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metrics = (("corridor_loss_s", "corridor vehicles: time loss (s)"),
               ("ev_time_s", "emergency vehicle: travel time (s)"))
    fig, axes = plt.subplots(len(summaries), len(metrics), figsize=(11, 3.1 * len(summaries)),
                             squeeze=False)
    for i, (label, summ) in enumerate(summaries.items()):
        for j, (m, title) in enumerate(metrics):
            ax = axes[i][j]
            for k, (key, _) in enumerate(ORDER):
                row = summ["scenarios"][key][m]
                lo, hi = row["delta_ci95"]
                col = COL[key.split("_")[0]]
                ax.barh(k, row["delta_vs_fixed"], color=col,
                        alpha=0.55 if key.endswith("degraded") else 1.0)
                ax.plot([lo, hi], [k, k], color="black", lw=1.2)
            ax.axvline(0, color="#444", lw=0.8)
            ax.set_yticks(range(len(ORDER)))
            ax.set_yticklabels([n for _, n in ORDER] if j == 0 else [], fontsize=8)
            ax.invert_yaxis()
            ax.set_title(f"{label}: {title}", fontsize=9)
            ax.set_xlabel("change against fixed-time (s)", fontsize=8)
            ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def plot_network(net: str, out: str | Path, origin: str = "A0", dest: str = "E4",
                 stretch: float = 3.0) -> None:
    """Grid with the backbone, the emergency-vehicle route and the controlled junctions."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import sumolib

    from pacc.graph import greedy_spanner, load_grid, route

    weights, _ = load_grid(net)
    keep = greedy_spanner(weights, stretch)
    _, path = route({e: weights[e] for e in keep}, origin, dest)
    on_route = {tuple(sorted(p)) for p in zip(path, path[1:], strict=False)}
    nets = sumolib.net.readNet(net)
    xy = {n.getID(): n.getCoord() for n in nets.getNodes()}
    fig, ax = plt.subplots(figsize=(5.4, 5.0))
    for (u, v) in weights:
        a, b = xy[u], xy[v]
        key = tuple(sorted((u, v)))
        if key in on_route:
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#e15759", lw=3.4, zorder=3)
        elif (u, v) in keep or (v, u) in keep:
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#4c78a8", lw=1.8, zorder=2)
        else:
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#b8c2cc", lw=1.0, ls=(0, (3, 3)), zorder=1)
    for n, c in xy.items():
        ctl = n in path[1:-1]
        ax.plot(c[0], c[1], "o", ms=9 if ctl else 5, color="#f28e2b" if ctl else "#555",
                zorder=4, mec="white")
    for n in (origin, dest):
        ax.annotate(n, xy[n], textcoords="offset points", xytext=(6, 6), fontsize=9)
    ax.plot([], [], color="#e15759", lw=3.4, label="emergency-vehicle route")
    ax.plot([], [], color="#4c78a8", lw=1.8, label="backbone")
    ax.plot([], [], color="#b8c2cc", lw=1.0, ls=(0, (3, 3)), label="removed from the backbone")
    ax.plot([], [], "o", color="#f28e2b", label="controlled junction")
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"t = {stretch:g} backbone: {len(keep)} of {len(weights)} edges", fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", nargs="+", help="summary.json files")
    ap.add_argument("--labels", nargs="+")
    ap.add_argument("--out", default="docs/assets/corridor_results.png")
    ap.add_argument("--network", default=None, help="draw the backbone of this .net.xml instead")
    args = ap.parse_args(argv)
    if args.network:
        plot_network(args.network, args.out)
        print(f"wrote {args.out}")
        return 0
    if not args.summary or not args.labels:
        ap.error("--summary and --labels are required without --network")
    runs = {lab: json.loads(Path(f).read_text(encoding="utf-8"))
            for lab, f in zip(args.labels, args.summary, strict=True)}
    plot_summary(runs, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
