"""Closed-loop corridor study in SUMO.

A 5 x 5 signalised grid carries random demand. An emergency vehicle drives a route chosen on the
spanner backbone and is preempted at every junction of that route. The junctions of the route are
the only ones controlled; each green split is set by the fuzzy rule base from queue counts that are
either true (oracle), emulated and degraded (naive), or emulated and weighted by the reliability
score (aware). Every controller replays the same demand seed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pacc.fuzzy import green_duration
from pacc.perception import Camera

END_DEMAND, MAX_T, T_EV, PREEMPT_M = 900.0, 1800.0, 450.0, 80.0
CONTROLLERS = ("fixed", "oracle", "naive", "aware")
GREEN_PHASES = (0, 2)
PRIOR0, R_TRUST = 8.0, 0.8


def sumo_home() -> str:
    """Location of the SUMO installation (``SUMO_HOME`` or the ``eclipse-sumo`` wheel)."""
    if os.environ.get("SUMO_HOME"):
        return os.environ["SUMO_HOME"]
    try:
        import sumo
        return str(sumo.SUMO_HOME)
    except ImportError:
        return "/usr/share/sumo"


def make_routes(net: str, seed: int, out: str | Path, corridor: tuple[str, ...] = (),
                period: float = 3.5, corridor_vph: float = 900.0) -> str:
    """Demand for one seed: random background trips plus a heavy flow along the corridor.

    Returns the ``-r`` argument (background file, then the corridor file when given).
    """
    out = Path(out)
    tool = Path(sumo_home()) / "tools" / "randomTrips.py"
    subprocess.run([sys.executable, str(tool), "-n", net, "-e", str(END_DEMAND), "-p", str(period),
                    "--seed", str(seed), "--fringe-factor", "10", "-r", str(out),
                    "-o", str(out.with_suffix(".trips.xml"))],
                   check=True, capture_output=True)
    if not corridor:
        return str(out)
    cor = out.with_name(out.stem + ".corridor.xml")
    cor.write_text(
        '<routes>\n <route id="corr" edges="' + " ".join(corridor) + '"/>\n'
        f' <flow id="cor" route="corr" begin="0" end="{END_DEMAND:g}"'
        f' vehsPerHour="{corridor_vph:g}"'
        ' departLane="best" departSpeed="max" departPos="free" type="DEFAULT_VEHTYPE"'
        ' insertionChecks="all"/>\n</routes>\n', encoding="utf-8")
    return f"{out},{cor}"


@dataclass(frozen=True)
class Job:
    """One simulation: a demand seed, a controller and a perception condition."""

    net: str
    routes: str
    add: str
    seed: int
    controller: str
    degraded: bool
    ev_edges: tuple[str, ...]
    controlled: tuple[str, ...]


def _preempt(conn: Any, tl: str, road: str, lane_edge: list[str]) -> None:
    state = "".join("G" if e == road else "r" for e in lane_edge)
    conn.trafficlight.setRedYellowGreenState(tl, state)


def run_one(job: Job) -> dict[str, float | int | str | bool]:
    """Simulate one job and return the emergency-vehicle time and the mean time loss."""
    import traci

    label = f"{job.controller}_{int(job.degraded)}_{job.seed}"
    tmp = tempfile.mkdtemp()
    tripinfo = Path(tmp) / "tripinfo.xml"
    traci.start(["sumo", "-n", job.net, "-r", job.routes, "--additional-files", job.add,
                 "--seed", str(job.seed), "--no-step-log", "true", "--no-warnings", "true",
                 "--duration-log.disable", "true", "--tripinfo-output", str(tripinfo)],
                label=label)
    conn = traci.getConnection(label)
    cam = Camera(np.random.default_rng(job.seed))
    tls = [t for t in job.controlled if t in conn.trafficlight.getIDList()]
    lane_of: dict[str, list[str]] = {}
    for tl in tls:
        links = conn.trafficlight.getControlledLinks(tl)
        lane_of[tl] = [grp[0][0] for grp in links]
    last = dict.fromkeys(tls, -1)
    pre_since: dict[str, float] = {}
    prior: dict[tuple[str, int], float] = {}
    inserted = False
    try:
        while conn.simulation.getMinExpectedNumber() > 0 and conn.simulation.getTime() < MAX_T:
            conn.simulationStep()
            t = conn.simulation.getTime()
            r = cam.step(t, job.degraded)
            if not inserted and t >= T_EV:
                try:
                    conn.route.add("ev_route", list(job.ev_edges))
                    conn.vehicle.add("ev", "ev_route", typeID="ev", departSpeed="max")
                except traci.TraCIException:
                    pass
                inserted = True
            ev_road = conn.vehicle.getRoadID("ev") if "ev" in conn.vehicle.getIDList() else None
            for tl in tls:
                lanes = lane_of[tl]
                edges = [ln.rsplit("_", 1)[0] for ln in lanes]
                if tl in pre_since:                       # preempting: release after the EV passed
                    if (ev_road is None or not (ev_road.startswith(":") or ev_road in edges)
                            or t - pre_since[tl] > 60.0):
                        conn.trafficlight.setProgram(tl, "0")
                        del pre_since[tl]
                        last[tl] = -1
                    continue
                if ev_road in edges and ev_road is not None:
                    length = conn.lane.getLength(ev_road + "_0")
                    if conn.vehicle.getLanePosition("ev") >= length - PREEMPT_M:
                        _preempt(conn, tl, ev_road, edges)
                        pre_since[tl] = t
                        continue
                ph = conn.trafficlight.getPhase(tl)
                if ph == last[tl] or ph not in GREEN_PHASES:
                    last[tl] = ph
                    continue
                last[tl] = ph
                if job.controller == "fixed":
                    continue
                state = conn.trafficlight.getRedYellowGreenState(tl)
                served = {lanes[i] for i, c in enumerate(state) if c in "Gg"}
                others = set(lanes) - served
                qs = sum(conn.lane.getLastStepVehicleNumber(x) for x in served)
                qc = sum(conn.lane.getLastStepVehicleNumber(x) for x in others)
                if job.controller != "oracle":
                    qs, qc = cam.count(qs, t, job.degraded), cam.count(qc, t, job.degraded)
                if job.controller == "aware":
                    key = (tl, ph)
                    p = prior.get(key, PRIOR0)
                    if r >= R_TRUST:
                        prior[key] = 0.7 * p + 0.3 * qs
                    qs, qc = r * qs + (1 - r) * p, r * qc + (1 - r) * PRIOR0
                conn.trafficlight.setPhaseDuration(tl, green_duration(qs, qc))
        unfinished = conn.simulation.getMinExpectedNumber()
    finally:
        conn.close()
    ev_time, cor, oth = float("nan"), [], []
    for ti in ET.parse(tripinfo).getroot().findall("tripinfo"):
        vid, loss = ti.get("id", ""), float(ti.get("timeLoss", "0"))
        if vid == "ev":
            ev_time = float(ti.get("duration", "nan"))
        elif vid.startswith("cor."):
            cor.append(loss)
        else:
            oth.append(loss)
    nan = float("nan")
    return {"seed": job.seed, "controller": job.controller, "degraded": job.degraded,
            "ev_time_s": ev_time, "corridor_loss_s": float(np.mean(cor)) if cor else nan,
            "other_loss_s": float(np.mean(oth)) if oth else nan, "n_corridor": len(cor),
            "n_other": len(oth), "unfinished": int(unfinished)}
