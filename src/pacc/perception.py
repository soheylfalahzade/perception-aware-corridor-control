"""Emulated camera counts and an emulated reliability signal.

Perception is abstracted to two things a controller sees: a queue count that misses vehicles
under degradation, and a reliability score in [0, 1] that follows the true degradation with a lag
(the monitor in ``perception-reliability-monitor`` reports alarms within 3 to 8 s).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MISS_AT_FULL = 0.8       # fraction of vehicles missed at severity 1
EPISODE = (300.0, 750.0)  # degradation episode (s)
SEVERITY = 0.7


def severity(t: float, degraded: bool) -> float:
    """True degradation severity at time ``t``."""
    return SEVERITY if degraded and EPISODE[0] <= t <= EPISODE[1] else 0.0


@dataclass
class Camera:
    """Count emulator with a lagged reliability score."""

    rng: np.random.Generator
    lag_alpha: float = 0.15
    r: float = 1.0

    def step(self, t: float, degraded: bool) -> float:
        """Advance the reliability score by one second and return it."""
        raw = 1.0 - 1.15 * severity(t, degraded) + self.rng.normal(0.0, 0.07)
        self.r += self.lag_alpha * (min(max(raw, 0.0), 1.0) - self.r)
        return self.r

    def count(self, n_true: int, t: float, degraded: bool) -> float:
        """Observed vehicle count: each vehicle is missed with probability 0.8 * severity."""
        miss = MISS_AT_FULL * severity(t, degraded)
        return float(self.rng.binomial(n_true, 1.0 - miss)) if n_true > 0 else 0.0
