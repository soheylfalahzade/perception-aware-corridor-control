# Methods

## 1. Network and backbone
A 5 x 5 signalised grid (`examples/grid5.net.xml`, two lanes per direction, links of about 130 m, 13.89 m/s)
generated with `netgenerate --grid --grid.number 5 --grid.length 150 -j traffic_light --no-turnarounds true
--default.lanenumber 2`. The junction graph carries undirected free-flow travel times. The **backbone** is the greedy
t-spanner of that graph: edges are scanned by increasing weight and an edge (u, v) is kept when the kept subgraph does
not already connect u and v within t times its weight. With t = 3 the backbone keeps 30 of 40 edges. The emergency
vehicle (EV) route from junction A0 to E4 is the shortest route on the backbone; its stretch against the shortest
route on the full graph is 1.0, and it passes 9 junctions, 7 of them signalised with four phases. Those junctions are
the only ones the controllers act on.

## 2. Demand
Per seed: random background trips (`randomTrips.py`, one trip every 3.5 s for 900 s, fringe factor 10) and a flow along
the EV route (700 or 900 vehicles per hour for 900 s). Every controller replays the same seed. The EV enters at
t = 450 s.

## 3. Perception emulation
The controller sees a queue count and a reliability score r in [0, 1].
- Degradation episode: severity 0.7 for t in [300, 750] s, else 0 (conditions *clear* and *degraded*).
- Counts: each vehicle on a lane group is missed with probability 0.8 x severity (binomial thinning).
- Reliability: raw score 1 - 1.15 x severity + N(0, 0.07), clipped to [0, 1] and smoothed by an exponential filter
  (alpha = 0.15 per second, time constant about 6.7 s), in line with alarm latencies of 3 to 8 s reported for the
  reliability monitor in `perception-reliability-monitor`.
This is an emulation of the interface, not of a detector.

## 4. Controllers
At the start of each green phase of a controlled junction the green duration is set from the vehicle counts on the
served lanes (q_s) and on the competing lanes (q_c) by a four-rule Sugeno system with product t-norm:

| q_s | q_c | green (s) |
|---|---|---|
| high | low | 60 |
| high | high | 48 |
| low | low | 36 |
| low | high | 24 |

"high" rises linearly from 0 at 3 vehicles to 1 at 14 vehicles, "low" is its complement; the output is clipped to
[20, 60] s. Fixed-time operation uses 42 s.
- **fixed**: no change to the signal programme.
- **oracle**: fuzzy rules on the true counts.
- **naive**: fuzzy rules on the emulated counts.
- **aware**: fuzzy rules on r x count + (1 - r) x prior, with the prior a per-junction, per-phase moving average of
  past counts updated only while r >= 0.8 (initial value 8 vehicles); competing lanes use the constant 8 as prior.

### 4.1 Standard controllers and camera-driven max-pressure
All of them act on the same controlled junctions, keep the yellow phases of the programme, use the green limits of the
fuzzy rule base (20 to 60 s) and are preempted for the emergency vehicle exactly like the fuzzy controllers.
- **actuated**: SUMO's gap-based actuated logic (`TRAFFICLIGHT_TYPE_ACTUATED`) on the phases of the fixed programme, with
  `minDur` 20 s and `maxDur` 60 s on the green phases and SUMO's default detector gap; true counts.
- **maxpressure**: at the start of a green the duration is set to 60 s; after 20 s, once per second, the green ends when
  the pressure of the competing phase exceeds that of the running phase. The pressure of a phase is the sum, over the
  signal links that are green in it, of the vehicles on the incoming lane minus the vehicles on the outgoing lane; true counts.
- **mp_naive**: the same rule with every lane count thinned by the emulated camera (section 3).
- **mp_aware**: the same rule on r x pressure + (1 - r) x prior, the prior being a per-junction, per-phase moving average
  of past camera pressures (weight 0.3) updated only while r >= 0.8, initial value 0.

## 5. Emergency-vehicle preemption
Identical for all controllers. When the EV is within 80 m of the stop line of a controlled junction the signal is
forced green for its approach and all others red; after the EV has left, the signal programme is restored.

## 6. Metrics and statistics
Travel time of the EV; mean time loss (SUMO `timeLoss`) of the vehicles of the corridor flow and of all other
vehicles. Differences against fixed-time and of *aware* against *naive* are paired by seed; intervals are
percentile bootstrap intervals (2000 resamples) of the mean paired difference over 12 seeds.
