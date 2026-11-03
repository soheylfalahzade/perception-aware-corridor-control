.PHONY: install test lint typecheck eval figures all
install:
	pip install -e ".[sumo,dev]"
test:
	pytest
lint:
	ruff check src tests
typecheck:
	mypy src/pacc
eval:
	pacc-eval --corridor-vph 700 --seeds 12 --jobs 2 --out results/eval700
	pacc-eval --corridor-vph 900 --seeds 12 --jobs 2 --out results/eval900
figures:
	pacc-figures --summary docs/results/summary_700.json docs/results/summary_900.json \
	  --labels "700 veh/h" "900 veh/h" --out docs/assets/corridor_results.png
all: lint typecheck test
