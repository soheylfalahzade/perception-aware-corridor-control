"""Build ``docs/data/perception_replay.csv`` from per-frame results of a real-footage run.

Input: ``frames_detrac_yolov8.csv`` (human-labelled boxes, detector counts and ten monitor
features per frame). Output: per frame the human count, the detector count and the monitor's
reliability score, obtained by leave-one-video-out (the model never sees the video it scores).

Needs the packages ``relmon`` and ``rfv`` (``--rfv-src`` is the ``src`` folder of the latter).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from relmon.monitor import ReliabilityModel


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--rfv-src", required=True)
    ap.add_argument("--out", default="docs/data/perception_replay.csv")
    args = ap.parse_args()
    sys.path.insert(0, args.rfv_src)
    import rfv.analysis as an

    df = an.prepare(pd.read_csv(args.frames))
    fcols = [f"f{c}" for c in an.FEATURE_SETS["combined"]]
    parts = []
    for v in sorted(df["video"].unique()):
        tr, te = df[df.video != v], df[df.video == v]
        model = ReliabilityModel().fit(tr[fcols].to_numpy(), tr["label"].to_numpy())
        parts.append(te.assign(p=[model.predict(r) for r in te[fcols].to_numpy()]))
    out = pd.concat(parts)[["video", "seg", "cond", "sev", "frame", "n_gt", "n_det", "label", "p"]]
    out["p"] = out["p"].round(4)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.sort_values(["video", "seg", "cond", "sev", "frame"]).to_csv(args.out, index=False)
    print(f"{len(out)} frames, {out.video.nunique()} videos -> {args.out}")


if __name__ == "__main__":
    main()
