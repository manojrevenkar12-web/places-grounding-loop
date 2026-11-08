PY ?= python3
export PYTHONPATH := src

.PHONY: world train test eval gate heldout report web check

world:      ## regenerate the world (changes the held-out fingerprint: only before the pin)
	$(PY) scripts/build_world.py
train:      ## train the matcher on development-area pairs of release 1
	$(PY) -m pgl.training.train
test:
	$(PY) -m pytest -q
eval:       ## the development evaluation -> reports/dev.json (about nine minutes)
	$(PY) scripts/evaluate.py
gate:       ## CI gate: [gate].candidate against [gate].current; exits 1 when blocked
	$(PY) scripts/gate.py
heldout:    ## once: the east area and its tasks -> reports/heldout.json, reports/heldout-runs.log
	$(PY) scripts/heldout.py
report:     ## results.json, RESULTS.md, the README block and the dashboard's data
	$(PY) scripts/report.py
web:
	cd web && npm ci && npm test && npm run build
check: test gate
