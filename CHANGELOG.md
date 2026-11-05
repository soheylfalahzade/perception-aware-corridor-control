# Changelog

All notable changes to this project are documented here. The format follows Keep a Changelog and
the project uses semantic versioning.

## [Unreleased]

- `route_comparison` in `pacc.graph` (backbone against shortest route: times, stretch, junction sets).
- `--replay` / `--replay-cond`, `pacc.replay.ReplayCamera` and `scripts/build_replay.py`: perception replayed from real-footage results (`docs/data/perception_replay.csv`, `docs/results/replay_*_700*`).
- `--preempt-m` (preemption distance) and results for 150 m (`docs/results/*_p150.csv`, `preempt150_*`).
- `--trace` and `summarise_trace`: time, stopped time and vehicles ahead per segment of the emergency vehicle (`docs/results/edge_*_700.csv`).
- `--route-mode backbone|shortest` in `pacc-eval`; larger-stretch results in `docs/results/stretch7_*`.

## [0.1.0]

- Junction graph, greedy t-spanner backbone and backbone routes (`pacc.graph`).
- Sugeno fuzzy green-split rule base (`pacc.fuzzy`).
- Emulated camera counts and reliability score (`pacc.perception`).
- SUMO corridor study with four controllers and paired bootstrap summaries (`pacc-eval`).
- Result figure (`pacc-figures`).
