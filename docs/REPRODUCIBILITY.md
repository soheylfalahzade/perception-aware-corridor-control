# Reproducibility

Ubuntu 22.04 (WSL2), Python 3.10 to 3.12, SUMO 1.2x. All numbers come from `pacc-eval` with fixed seeds 0 to 11.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[sumo,dev]"
pytest
pacc-eval --corridor-vph 700 --seeds 12 --jobs 2 --out results/eval700    # about 5 min on one core per level
pacc-eval --corridor-vph 900 --seeds 12 --jobs 2 --out results/eval900
pacc-figures --summary results/eval700/summary.json results/eval900/summary.json \
  --labels "700 veh/h" "900 veh/h" --out docs/assets/corridor_results.png
```

With a system SUMO installation, set `SUMO_HOME` (for example `/usr/share/sumo`) so that `randomTrips.py` is found.
The network was generated with the `netgenerate` command in `docs/METHODS.md`. `docs/results/` holds the summaries
and per-run tables behind the figures and tables.
