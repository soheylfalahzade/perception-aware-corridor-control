"""Sugeno-type fuzzy green-split rule base."""
from __future__ import annotations

LOW_Q, HIGH_Q = 3.0, 14.0           # vehicles on a lane group: "low" below, "high" above
G_MIN, G_MAX = 20.0, 60.0           # green duration limits (s)
OUT = {("high", "low"): 60.0, ("high", "high"): 48.0, ("low", "low"): 36.0, ("low", "high"): 24.0}


def high(q: float) -> float:
    """Membership of ``q`` in the fuzzy set "high"; "low" is its complement."""
    return min(max((q - LOW_Q) / (HIGH_Q - LOW_Q), 0.0), 1.0)


def green_duration(q_serve: float, q_comp: float) -> float:
    """Green time for the served movement from the queue on the served and competing lanes.

    Four rules, product t-norm, weighted-average defuzzification: a high queue on the served
    approach lengthens the green, a high queue on the competing approach shortens it.
    """
    hs, hc = high(q_serve), high(q_comp)
    w = {("high", "low"): hs * (1 - hc), ("high", "high"): hs * hc,
         ("low", "low"): (1 - hs) * (1 - hc), ("low", "high"): (1 - hs) * hc}
    total = sum(w.values())
    out = sum(w[k] * OUT[k] for k in w) / total if total > 0 else 42.0
    return float(min(max(out, G_MIN), G_MAX))
