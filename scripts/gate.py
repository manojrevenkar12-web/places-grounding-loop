"""The CI gate: the candidate harness from config against the current one, on the development tasks and the
regression cases mined from production. Exits 1 when the change is blocked."""

from __future__ import annotations

import json
import sys

from pgl.agents.harness import ABLATIONS, CHANGES, HARNESSES
from pgl.evals import feedback, gate
from pgl.evals.tasks import Evaluator, load_tasks
from pgl.pipeline.release import build
from pgl.settings import load


def named(name: str):
    pool = {**HARNESSES, **ABLATIONS, **{k: v[1] for k, v in CHANGES.items()}}
    if name not in pool:
        sys.exit(f"unknown harness {name!r}; known: {', '.join(pool)}")
    return pool[name]


def main() -> None:
    s = load()
    cur, cand = s.gate.current, (sys.argv[1] if len(sys.argv) > 1 else s.gate.candidate)
    r1 = build(1, s)
    ev = Evaluator(build(2, s, r1), s)
    tasks, truth = load_tasks("dev")
    cases = feedback.load_cases()
    a = ev.run(named(cur), tasks, truth, s.run.repeats)
    b = ev.run(named(cand), tasks, truth, s.run.repeats)
    d = gate.decide(a, b, feedback.replay(ev, named(cur), cases, tasks, truth, s),
                    feedback.replay(ev, named(cand), cases, tasks, truth, s), s)
    print(json.dumps({"current": cur, "candidate": cand, **d}, indent=1))
    sys.exit(1 if d["blocked"] else 0)


if __name__ == "__main__":
    main()
