"""Camera replayed from real-footage results instead of an emulated one.

The table (``scripts/build_replay.py``) holds, for frames of real traffic video, the human count,
the detector count and the reliability score of the monitor. During a degradation episode the
camera replays frames of a degraded stream (night, rain, ...) of one video, otherwise frames of
the undegraded stream of the same video; one frame per simulated second. The detector's
count ratio of a frame scales the true queue count, the monitor score is smoothed as before.

The degradations of the footage are applied to the images, not to the traffic: only the
native weather of each clip is real.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from pacc.perception import severity


@lru_cache(maxsize=4)
def load_table(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


@dataclass
class ReplayCamera:
    """Same interface as ``pacc.perception.Camera``."""

    rng: np.random.Generator
    path: str
    cond: str = "night"
    sev: float = 1.0
    lag_alpha: float = 0.15
    r: float = 1.0
    video: str = field(init=False)
    _clear: pd.DataFrame = field(init=False)
    _deg: pd.DataFrame = field(init=False)
    _offset: int = field(init=False)
    _row: pd.Series = field(init=False)

    def __post_init__(self) -> None:
        df = load_table(self.path)
        videos = sorted(set(df[(df.cond == self.cond) & (df.sev == self.sev)].video)
                        & set(df[df.cond == "clear"].video))
        if not videos:
            raise ValueError(f"no video with both clear and {self.cond} (sev {self.sev}) frames")
        self.video = videos[int(self.rng.integers(len(videos)))]
        v = df[df.video == self.video].sort_values(["seg", "frame"])
        self._clear = v[v.cond == "clear"].reset_index(drop=True)
        self._deg = v[(v.cond == self.cond) & (v.sev == self.sev)].reset_index(drop=True)
        self._offset = int(self.rng.integers(len(self._clear)))
        self._row = self._clear.iloc[0]

    def step(self, t: float, degraded: bool) -> float:
        """Advance one second: pick the frame, update and return the smoothed score."""
        src = self._deg if severity(t, degraded) > 0 else self._clear
        self._row = src.iloc[(self._offset + int(t)) % len(src)]
        self.r += self.lag_alpha * (float(self._row["p"]) - self.r)
        return self.r

    def count(self, n_true: int, t: float, degraded: bool) -> float:
        """Observed count: the true count scaled by the detector's count ratio of the frame."""
        if n_true <= 0:
            return 0.0
        gt = float(self._row["n_gt"])
        ratio = float(self._row["n_det"]) / gt if gt > 0 else 1.0
        if ratio <= 1.0:
            return float(self.rng.binomial(n_true, ratio))
        return float(n_true + self.rng.binomial(n_true, min(ratio - 1.0, 1.0)))
