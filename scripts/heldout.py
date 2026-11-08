"""The held-out run: the east area and its tasks, once. Checks the pin, refuses a second run, scores the pipeline and
the three harnesses, and appends to reports/heldout-runs.log. The result is published as it comes out."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

from pgl import heldout
from pgl.agents.harness import HARNESSES
from pgl.evals.pipeline_eval import score
from pgl.evals.stats import paired
from pgl.evals.tasks import Evaluator, load_tasks
from pgl.pipeline.release import build
from pgl.settings import ROOT, load

sys.path.insert(0, str(ROOT / "scripts"))
from evaluate import summary

LOG = ROOT / "reports" / "heldout-runs.log"


def main() -> None:
    heldout.check()
    if LOG.exists() and LOG.read_text().strip():
        sys.exit("the held-out run has already happened; see reports/heldout-runs.log")
    s = load()
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "src", "config", "scripts"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
    )
    if dirty:
        sys.exit("commit the code first: the log records the commit the run used")
    full1 = build(1, s)
    full2 = build(2, s, full1)
    naive1 = build(1, s, naive=True)
    naive2 = build(2, s, naive1, naive=True)
    out = {
        "area": "heldout",
        "commit": commit,
        "fingerprint": heldout.fingerprint(),
        "pipeline": {"full": score(full2, s, "heldout", full1), "naive": score(naive2, s, "heldout", naive1)},
    }
    tasks, truth = load_tasks("heldout")
    ev = Evaluator(full2, s)
    runs = {name: ev.run(g, tasks, truth, s.run.repeats) for name, g in HARNESSES.items()}
    out["harnesses"] = {name: summary(r, s) for name, r in runs.items()}
    e = s.eval
    out["paired"] = {
        f"{b} vs {a}": [round(x, 4) for x in paired(runs[a], runs[b], e.bootstrap, e.alpha, s.run.seed)]
        for a, b in (("plain", "guarded"), ("plain", "plan_fetch"), ("guarded", "plan_fetch"))
    }
    (ROOT / "reports" / "heldout.json").write_text(json.dumps(out, indent=1))
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG.open("a") as f:
        f.write(
            f"{stamp} commit={commit} fingerprint={out['fingerprint'][:16]} tasks={len(tasks)} "
            f"repeats={s.run.repeats} "
            + " ".join(f"{k}={v['success']:.3f}" for k, v in out["harnesses"].items())
            + "\n"
        )
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
