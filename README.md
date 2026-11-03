# perception-aware-corridor-control

<p align="center"><img src="docs/assets/banner.svg" alt="perception-aware-corridor-control" width="860"></p>

**Does a corridor controller do better when it is told how far to trust its camera? A backbone route, a fuzzy green-split rule base and a reliability-weighted input, tested in SUMO with an emergency vehicle.**

A camera-based signal controller usually receives a vehicle count and nothing about the quality of that count. When the camera degrades (rain, glare, dirt) the count is too low, and a controller that trusts it shortens the wrong greens. This package asks whether passing a reliability score to the controller, so that it falls back on what it learned in good conditions when the score is low, recovers the loss. The corridor is a route on a spanner backbone of the street grid, and only the junctions of that route are controlled. Nothing is trained and no detector is run: perception is emulated at its interface (counts that miss vehicles, and a lagged reliability score).

<p align="center"><img src="docs/assets/backbone_route.png" alt="Backbone, emergency-vehicle route and controlled junctions" width="420"></p>

## Method in one paragraph

On a 5 x 5 signalised grid the greedy 3-spanner keeps 30 of 40 street segments; the shortest backbone route between two corners has stretch 1.0 and passes 7 signals. Demand is a random background plus a heavy flow along the route (700 or 900 vehicles per hour). At the start of each green, a four-rule Sugeno fuzzy system sets the green time from the vehicle counts on the served and on the competing approaches. Three count sources are compared: the true counts (oracle), the emulated camera counts (naive), and the emulated counts shrunk towards a running prior by the reliability score r (aware: r x count + (1 - r) x prior). A camera degradation episode (300 to 750 s, severity 0.7) removes up to 56 % of the vehicles from the counts, and r follows the degradation with a lag of a few seconds. An emergency vehicle is preempted on the route in all conditions. Full definitions: [`docs/METHODS.md`](docs/METHODS.md).

## Installation (Ubuntu / WSL2)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[sumo,dev]"
pytest
```

## Usage

```bash
pacc-eval --corridor-vph 700 --seeds 12 --jobs 2 --out results/eval700     # about 5 min on one core
pacc-eval --corridor-vph 900 --seeds 12 --jobs 2 --out results/eval900
pacc-figures --summary results/eval700/summary.json results/eval900/summary.json \
  --labels "700 veh/h" "900 veh/h" --out docs/assets/corridor_results.png
```

## Results (SUMO, 12 seeds, paired by seed)

Time loss of the vehicles of the corridor flow and travel time of the emergency vehicle (EV), with the change against fixed-time control and a percentile bootstrap 95% interval over seeds. In the clear condition the emulated counts are exact, so *camera, clear* equals *true counts* by construction.

**Corridor flow of 700 vehicles per hour**

| controller | corridor time loss (s) | change vs fixed [95% CI] | EV travel time (s) | change vs fixed [95% CI] |
|---|---|---|---|---|
| fixed-time | 139.6 | | 139.5 | |
| true counts | 120.7 | -18.8 [-29.3, -9.6] | 163.9 | +24.4 [12.4, 37.2] |
| camera, clear | 120.7 | -18.8 [-29.3, -9.6] | 163.9 | +24.4 [12.4, 37.2] |
| camera + reliability, clear | 125.6 | -13.9 [-21.7, -6.9] | 153.1 | +13.6 [2.5, 27.0] |
| camera, degraded | 137.0 | -2.6 [-11.7, 5.6] | 167.0 | +27.5 [21.5, 33.3] |
| camera + reliability, degraded | 119.8 | -19.7 [-29.4, -11.6] | 160.0 | +20.5 [4.7, 35.6] |

**Corridor flow of 900 vehicles per hour (fixed-time operation is close to saturation)**

| controller | corridor time loss (s) | change vs fixed [95% CI] | EV travel time (s) | change vs fixed [95% CI] |
|---|---|---|---|---|
| fixed-time | 256.8 | | 264.7 | |
| true counts | 153.2 | -103.6 [-111.8, -96.1] | 206.1 | -58.6 [-109.8, -13.9] |
| camera, clear | 153.2 | -103.6 [-111.8, -96.1] | 206.1 | -58.6 [-109.8, -13.9] |
| camera + reliability, clear | 156.2 | -100.6 [-110.1, -90.1] | 216.5 | -48.2 [-105.4, 9.3] |
| camera, degraded | 185.6 | -71.1 [-79.7, -63.5] | 250.6 | -14.1 [-59.6, 36.3] |
| camera + reliability, degraded | 178.0 | -78.8 [-87.3, -69.9] | 213.3 | -51.3 [-103.6, 1.8] |

Reliability-aware against naive, same seeds (negative: aware is better):

| demand | camera | corridor time loss (s) | EV travel time (s) |
|---|---|---|---|
| 700 veh/h | clear | +4.9 [-2.9, 12.3] | -10.8 [-27.3, 3.5] |
| 700 veh/h | degraded | -17.1 [-23.5, -11.1] | -7.0 [-23.4, 7.9] |
| 900 veh/h | clear | +2.9 [-3.1, 9.6] | +10.4 [-6.8, 28.8] |
| 900 veh/h | degraded | -7.7 [-16.9, 1.6] | -37.2 [-69.0, -4.8] |

<p align="center"><img src="docs/assets/corridor_results.png" alt="Change against fixed-time control by controller and demand" width="900"></p>

- **Adaptive green splits reduce the corridor delay** relative to fixed-time operation when the counts are right: by 18.8 s at 700 veh/h and 103.6 s at 900 veh/h (true counts).
- **A degraded camera removes most of that gain at 700 veh/h** (naive: -2.6 s, interval including zero) **and a third of it at 900 veh/h** (naive -71.1 s against -103.6 s).
- **Passing the reliability score recovers the loss at 700 veh/h** (aware against naive: -17.1 [-23.5, -11.1] s) and **gives a smaller, not significant gain at 900 veh/h** on corridor delay (-7.7 [-16.9, 1.6] s), where the emergency vehicle is faster (interval excludes zero; -37.2 [-69.0, -4.8] s).
- **With a healthy camera the reliability weighting costs little**: the differences against naive are positive but their intervals include zero (+4.9 [-2.9, 12.3] s and +2.9 [-3.1, 9.6] s).
- **The emergency vehicle is slower with adaptive control at 700 veh/h** than under fixed-time operation (+13.6 to +27.5 s, all intervals above zero), although it is preempted in every condition. The cause was not isolated here; at 900 veh/h the sign reverses and the intervals include zero except for the oracle and naive-clear conditions. Other vehicles' delay is within about 3 s of fixed-time in all conditions.

## Claims and evidence

| claim | evidence | file |
|---|---|---|
| fuzzy green splits reduce corridor delay when counts are right | 700 veh/h: -18.8 [-29.3, -9.6] s; 900 veh/h: -103.6 [-111.8, -96.1] s | `docs/results/summary_*.json` |
| a degraded camera removes the gain | naive degraded at 700 veh/h: -2.6 [-11.7, 5.6] s | `docs/results/summary_700.json` |
| the reliability score recovers it | aware minus naive, degraded, 700 veh/h: -17.1 [-23.5, -11.1] s | `docs/results/summary_700.json` |
| the reliability score helps at saturation | **partially supported**: corridor delay -7.7 [-16.9, 1.6] s (interval includes zero), EV time -37.2 [-69.0, -4.8] s | `docs/results/summary_900.json` |
| the reliability weighting is free in clear conditions | **partially supported**: +4.9 and +2.9 s on corridor delay, intervals include zero | `docs/results/summary_*.json` |
| adaptive control speeds up the emergency vehicle | **not supported** at 700 veh/h (slower by 13.6 to 27.5 s, intervals above zero); at 900 veh/h faster with true counts or a clear camera (-58.6 [-109.8, -13.9] s), intervals include zero for the other conditions | `docs/results/summary_*.json` |

## Threats to validity

- *Construct:* perception is emulated at the interface of counts and a reliability score; the miss model (binomial thinning), the severity and the lag are assumptions, not measurements of a detector. The lag is chosen in line with alarm latencies reported by `perception-reliability-monitor`.
- *Internal:* the rule base, the prior update and the trust threshold (r >= 0.8) were set a priori and not tuned; the corridor flow and the degradation window are fixed scenario choices. The emergency-vehicle result at 700 veh/h is unexplained.
- *External:* one 5 x 5 grid, one route, one degradation episode and one emergency-vehicle trip per run; the backbone route coincides with the shortest route (stretch 1.0), so the backbone does not change the route here.
- *Statistical:* 12 seeds; intervals are bootstrap intervals of the mean paired difference and are not corrected for the number of comparisons.

## Data and code availability

All code, the network, seeds, per-run tables and summaries are in this repository (`docs/results/`). No external data are used. Commands and versions: [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

## Limitations and scope

- Emulated perception only; no detector, no image data.
- The backbone enters through the choice of the controlled route; a route that differs from the shortest one, and several corridors at once, are not studied.
- Fuzzy rules use queue counts at the start of a green; no coordination between junctions and no learning.

## Roadmap

Reliability scores from a real monitor and counts from a real detector instead of the emulation; routes on backbones with a larger stretch; several corridors sharing junctions; an emergency-vehicle objective in the green-split rules.

## Citation

See [`CITATION.cff`](CITATION.cff).

## License

MIT. See [LICENSE](LICENSE).
