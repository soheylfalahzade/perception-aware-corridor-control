"""Render the baseline tables of README.md from docs/results/baselines_*.json.

Tables sit between ``<!-- BEGIN:name -->`` and ``<!-- END:name -->`` markers and are generated here,
so no number inside them is typed by hand.

    python -m pacc.render_readme            # rewrite the tables in README.md
    python -m pacc.render_readme --check    # exit 1 if README.md differs from the recorded data

Verdict rules of the claims table (fixed here, not tuned to the result). A comparison on the mean
corridor time loss is *better* when the paired difference (camera-based minus baseline) is negative
and its Holm-adjusted p-value is below 0.05, *worse* when positive and below 0.05, otherwise
*indistinguishable*. A claim is "supported" when the comparison is better at every demand level,
"not supported" when it is worse at every demand level or indistinguishable at every level, and
"partially supported" otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
FLOWS = (700, 900)
ALPHA = 0.05
LABEL = {
    "fixed_clear": "fixed-time",
    "actuated_clear": "actuated",
    "maxpressure_clear": "max-pressure",
    "oracle_clear": "fuzzy, true counts",
    "naive_degraded": "fuzzy, camera, degraded",
    "aware_degraded": "fuzzy, camera + reliability, degraded",
    "mp_naive_degraded": "max-pressure, camera, degraded",
    "mp_aware_degraded": "max-pressure, camera + reliability, degraded",
}
ORDER = (
    "fixed_clear",
    "actuated_clear",
    "maxpressure_clear",
    "oracle_clear",
    "naive_degraded",
    "aware_degraded",
    "mp_naive_degraded",
    "mp_aware_degraded",
)
CAMERA = (
    "oracle_clear",
    "naive_degraded",
    "aware_degraded",
    "mp_naive_degraded",
    "mp_aware_degraded",
)
BASES = ("fixed_clear", "actuated_clear", "maxpressure_clear")
PRIMARY = ("mp_aware_degraded", "mp_naive_degraded", "corridor_loss_s")
METRIC = {
    "corridor_loss_s": "corridor time loss [s]",
    "ev_time_s": "EV travel time [s]",
    "other_loss_s": "other time loss [s]",
}


def load(flow: int) -> dict[str, Any]:
    path = ROOT / "docs" / "results" / f"baselines_{flow}.json"
    return json.loads(path.read_text(encoding="utf-8"))["against_baselines"]


def md(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    return "\n".join(out + ["| " + " | ".join(r) + " |" for r in rows])


def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def cell(c: dict[str, Any], nd: int = 1) -> str:
    lo, hi = c["ci95"]
    return f"{c['mean_diff']:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}] (Holm {fmt_p(c['p_holm'])})"


def classify(c: dict[str, Any]) -> str:
    if c["p_holm"] < ALPHA:
        return "better" if c["mean_diff"] < 0 else "worse"
    return "indistinguishable"


def get(d: dict[str, Any], cam: str, base: str, metric: str) -> dict[str, Any]:
    return d["comparisons"][f"{cam} - {base} | {metric}"]


def block_means(data: dict[int, dict[str, Any]]) -> str:
    out = []
    for flow, d in data.items():
        rows = []
        for key in ORDER:
            rows.append([LABEL[key]] + [f"{d['means'][m][key]:.1f}" for m in METRIC])
        out += [
            f"**Corridor flow of {flow} vehicles per hour** (mean over {d['n_seeds']} seeds)",
            "",
            md(["controller"] + list(METRIC.values()), rows),
            "",
        ]
    return "\n".join(out).rstrip()


def block_tests(data: dict[int, dict[str, Any]]) -> str:
    out = []
    for flow, d in data.items():
        rows = []
        for cam in CAMERA:
            for base in BASES:
                rows.append(
                    [f"{LABEL[cam]} minus {LABEL[base]}"]
                    + [cell(get(d, cam, base, m)) for m in METRIC]
                )
        rows.append(
            [f"{LABEL['mp_aware_degraded']} minus {LABEL['mp_naive_degraded']}"]
            + [cell(get(d, "mp_aware_degraded", "mp_naive_degraded", m)) for m in METRIC]
        )
        out += [
            f"**{flow} vehicles per hour**: paired difference [95% bootstrap interval] "
            f"(Holm-adjusted p over the {d['n_comparisons']} comparisons of this level)",
            "",
            md(["comparison"] + list(METRIC.values()), rows),
            "",
        ]
    return "\n".join(out).rstrip()


CLAIMS = (
    (
        "reliability-aware weighting helps camera-based max-pressure under a degraded camera",
        "mp_aware_degraded",
        "mp_naive_degraded",
    ),
    (
        "camera-based max-pressure with reliability weighting beats actuated control",
        "mp_aware_degraded",
        "actuated_clear",
    ),
    (
        "fuzzy green splits with a degraded camera and reliability score beat fixed-time control",
        "aware_degraded",
        "fixed_clear",
    ),
    ("... beat actuated control", "aware_degraded", "actuated_clear"),
    ("... beat max-pressure control with true counts", "aware_degraded", "maxpressure_clear"),
)


def verdict(labels: list[str]) -> str:
    if all(x == "better" for x in labels):
        return "supported"
    if all(x in ("worse", "indistinguishable") for x in labels):
        return "not supported"
    return "partially supported"


def block_claims(data: dict[int, dict[str, Any]]) -> str:
    rows = []
    for text, cam, base in CLAIMS:
        cs = {flow: get(d, cam, base, "corridor_loss_s") for flow, d in data.items()}
        v = verdict([classify(c) for c in cs.values()])
        ev = "; ".join(f"{flow} veh/h: {cell(c)} s, {classify(c)}" for flow, c in cs.items())
        rows.append([text, f"**{v}**: corridor time loss, {ev}", "`docs/results/baselines_*.json`"])
    return md(["claim", "evidence", "file"], rows)


def block_reading(data: dict[int, dict[str, Any]]) -> str:
    lines = ["Reading, generated from the tables above (corridor time loss, Holm-adjusted):", ""]
    for flow, d in data.items():
        counts = {"better": 0, "worse": 0, "indistinguishable": 0}
        for cam in CAMERA:
            for base in BASES:
                counts[classify(get(d, cam, base, "corridor_loss_s"))] += 1
        total = sum(counts.values())
        lines.append(
            f"- {flow} veh/h: of the {total} comparisons of a camera-based controller with "
            f"a baseline, {counts['better']} favour the camera-based controller, "
            f"{counts['worse']} favour the baseline and {counts['indistinguishable']} "
            "are indistinguishable."
        )
    cam, base, metric = PRIMARY
    p = get(data[FLOWS[0]], cam, base, metric)
    lines += [
        "",
        f"Primary endpoint (fixed before the confirmatory runs): corridor time loss at "
        f"{FLOWS[0]} veh/h, {LABEL[cam]} minus {LABEL[base]}: {cell(p)} s, {classify(p)}.",
    ]
    return "\n".join(lines)


def block_scope(data: dict[int, dict[str, Any]]) -> str:
    def word(base: str) -> str:
        labels = [
            classify(get(d, "aware_degraded", base, "corridor_loss_s")) for d in data.values()
        ]
        if all(x == "worse" for x in labels):
            return "worse than"
        if all(x == "better" for x in labels):
            return "better than"
        return "mixed against"

    return (
        "**Scope of the comparison.** The first results below compare the fuzzy corridor "
        "controller with fixed-time control. On corridor time loss at every tested demand level, "
        "the fuzzy controller with a degraded camera and the reliability score is "
        f"{word('actuated_clear')} actuated control and {word('maxpressure_clear')} max-pressure "
        "on true counts (section *Against standard controllers and a competitive base "
        "controller*), which also tests the reliability score on a competitive base controller, "
        "max-pressure on camera counts."
    )


BLOCKS = {
    "baselines_scope": block_scope,
    "baselines_means": block_means,
    "baselines_tests": block_tests,
    "baselines_claims": block_claims,
    "baselines_reading": block_reading,
}


def render(text: str, data: dict[int, dict[str, Any]] | None = None) -> str:
    data = data or {f: load(f) for f in FLOWS}
    for name, fn in BLOCKS.items():
        pat = re.compile(rf"(<!-- BEGIN:{name} -->)\n.*?(<!-- END:{name} -->)", re.S)
        if not pat.search(text):
            sys.exit(f"README.md has no marker block for '{name}'")
        body = fn(data)

        def fill(m: re.Match[str], body: str = body) -> str:
            return m.group(1) + "\n" + body + "\n" + m.group(2)

        text = pat.sub(fill, text)
    return text


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    current = README.read_text(encoding="utf-8")
    rendered = render(current)
    if args.check:
        if rendered != current:
            print(
                "README.md tables differ from the recorded data; run: python -m pacc.render_readme"
            )
            sys.exit(1)
        print("README.md tables match the recorded data.")
        return
    README.write_text(rendered, encoding="utf-8")
    print("README.md tables rendered from the recorded data")


if __name__ == "__main__":
    main()
