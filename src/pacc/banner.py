"""Write the headline numbers of docs/assets/banner.svg from the recorded baseline summaries.

python -m pacc.banner            # rewrite docs/assets/banner.svg
python -m pacc.banner --check    # exit 1 if the banner differs from the recorded data
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

from pacc.render_readme import FLOWS, ROOT, get, load

BANNER = ROOT / "docs" / "assets" / "banner.svg"
TEXT = re.compile(r"(<text[^>]*>)([^<]*)(</text>)")
PRIMARY = ("mp_aware_degraded", "mp_naive_degraded", "corridor_loss_s")


def signed(x: float) -> str:
    return f"{x:+.1f}".replace("-", "\u2212")


def recovered(d: dict[str, Any]) -> float:
    """Share of the time loss that degradation adds to camera-based max-pressure which the
    reliability weighting removes."""
    m = d["means"]["corridor_loss_s"]
    return (
        100
        * (m["mp_naive_degraded"] - m["mp_aware_degraded"])
        / (m["mp_naive_degraded"] - m["maxpressure_clear"])
    )


def texts(data: dict[int, dict[str, Any]]) -> list[str]:
    lo, hi = FLOWS
    c_lo = get(data[lo], *PRIMARY)["mean_diff"]
    c_hi = get(data[hi], *PRIMARY)["mean_diff"]
    return [
        "perception-aware-corridor-control",
        "Does a max-pressure controller lose less when it knows how far to trust the camera?",
        f"{signed(c_lo)} s",
        "time loss, aware vs naive",
        f"max-pressure, degraded, {lo} veh/h",
        f"{signed(c_hi)} s",
        "time loss, aware vs naive",
        f"max-pressure, degraded, {hi} veh/h",
        f"{recovered(data[lo]):.0f} % / {recovered(data[hi]):.0f} %",
        "degradation loss recovered",
        f"{lo} / {hi} veh/h, max-pressure",
    ]


def render(svg: str, data: dict[int, dict[str, Any]] | None = None) -> str:
    data = data or {f: load(f) for f in FLOWS}
    new = iter(texts(data))
    out = TEXT.sub(lambda m: m.group(1) + next(new) + m.group(3), svg)
    if next(new, None) is not None:
        sys.exit("banner template has fewer text nodes than values")
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    current = BANNER.read_text(encoding="utf-8")
    rendered = render(current)
    if args.check:
        if rendered != current:
            print("banner.svg differs from the recorded data; run: python -m pacc.banner")
            sys.exit(1)
        print("banner.svg matches the recorded data.")
        return
    BANNER.write_text(rendered, encoding="utf-8")
    print("banner.svg rendered from the recorded data")


if __name__ == "__main__":
    main()
