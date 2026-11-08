"""The development evaluation: the pipeline (full and naive), the three harnesses, the ablations, the agents on
naive data, the feedback loop and the gate on a set of changes. Writes reports/dev.json. Never touches the held-out
tasks or area."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter

from pgl.agents.harness import ABLATIONS, CHANGES, HARNESSES
from pgl.evals import feedback, gate
from pgl.evals.pipeline_eval import score
from pgl.evals.stats import by_task, interval, paired, pct
from pgl.evals.tasks import Evaluator, load_tasks
from pgl.pipeline.release import build
from pgl.settings import ROOT, load

MODES = ["invented_argument", "stale_context", "silent_partial", "unbounded_loop", "guessed_between_matches"]


def summary(runs: list[dict], s) -> dict:
    e = s.eval
    rate, lo, hi = interval(list(by_task(runs).values()), e.bootstrap, e.alpha, s.run.seed)
    wrong = interval(list(by_task(runs, lambda r: r["outcome"] == "wrong").values()), e.bootstrap, e.alpha, s.run.seed)
    turns = [x for r in runs for x in r["turn_ms"]]
    kinds = sorted({r["kind"] for r in runs})
    n = len(runs)
    return {
        "success": round(rate, 4),
        "success_lo": round(lo, 4),
        "success_hi": round(hi, 4),
        "wrong": round(wrong[0], 4),
        "no_answer": round(sum(r["outcome"] == "no_answer" for r in runs) / n, 4),
        "by_kind": {
            k: round(
                sum(r["outcome"] == "right" for r in runs if r["kind"] == k) / sum(r["kind"] == k for r in runs), 4
            )
            for k in kinds
        },
        "modes": {m: round(sum(m in r["modes"] for r in runs) / n, 4) for m in MODES},
        "trips": dict(sum((Counter(r["trips"]) for r in runs), Counter())),
        "p50_ms": round(pct(turns, 50)),
        "p95_ms": round(pct(turns, 95)),
        "cost_eur": round(sum(r["cost_eur"] for r in runs) / len(turns), 5),
        "model_calls": round(sum(r["model_calls"] for r in runs) / len(turns), 2),
        "tool_calls": round(sum(r["tool_calls"] for r in runs) / len(turns), 2),
        "cache_hit_share": round(
            sum(r["cache_hits"] for r in runs) / max(1, sum(r["cache_hits"] + r["tool_calls"] for r in runs)), 4
        ),
        "runs": n,
        "turns": len(turns),
    }


def main() -> None:
    s = load()
    t0 = time.time()
    out: dict = {"area": "dev", "repeats": s.run.repeats}
    full1 = build(1, s)
    full2 = build(2, s, full1)
    naive1 = build(1, s, naive=True)
    naive2 = build(2, s, naive1, naive=True)
    out["pipeline"] = {
        "full": {
            "r1": score(full1, s, "dev"),
            "r2": score(full2, s, "dev", full1),
            "checks": full2.checks,
            "blocked": full2.blocked,
        },
        "naive": {
            "r1": score(naive1, s, "dev"),
            "r2": score(naive2, s, "dev", naive1),
            "checks": naive2.checks,
            "blocked": naive2.blocked,
        },
    }
    print("pipeline", round(time.time() - t0, 1), "s", file=sys.stderr)
    tasks, truth = load_tasks("dev")
    ev = Evaluator(full2, s)
    runs = {name: ev.run(g, tasks, truth, s.run.repeats) for name, g in HARNESSES.items()}
    out["harnesses"] = {name: summary(r, s) for name, r in runs.items()}
    e = s.eval
    out["paired"] = {
        f"{b} vs {a}": [round(x, 4) for x in paired(runs[a], runs[b], e.bootstrap, e.alpha, s.run.seed)]
        for a, b in (("plain", "guarded"), ("plain", "plan_fetch"), ("guarded", "plan_fetch"))
    }
    print("harnesses", round(time.time() - t0, 1), "s", file=sys.stderr)
    abl = {name: ev.run(g, tasks, truth, s.run.repeats) for name, g in ABLATIONS.items()}
    out["ablations"] = {
        name: dict(
            summary(r, s),
            vs_guarded=[round(x, 4) for x in paired(runs["guarded"], r, e.bootstrap, e.alpha, s.run.seed)],
        )
        for name, r in abl.items()
    }
    print("ablations", round(time.time() - t0, 1), "s", file=sys.stderr)
    ev_naive = Evaluator(naive2, s)
    out["on_naive_data"] = {
        name: summary(ev_naive.run(HARNESSES[name], tasks, truth, s.run.repeats), s)
        for name in ("guarded", "plan_fetch")
    }
    # the feedback loop: the first harness serves production, users report, a reviewer confirms, cases are kept
    log, prod = feedback.production(
        ev, HARNESSES[s.feedback.production_harness], tasks, truth, s, s.feedback.production_days
    )
    tri = feedback.triage(log, prod)
    feedback.save_log(log)
    feedback.save_cases(tri["cases"])
    replays = {name: feedback.replay(ev, g, tri["cases"], tasks, truth, s) for name, g in HARNESSES.items()}
    out["feedback"] = {k: v for k, v in tri.items() if k != "cases"} | {
        "cases": len(tri["cases"]),
        "case_modes": dict(Counter(m for c in tri["cases"] for m in c["modes"])),
        "pass": {name: sum(r.values()) for name, r in replays.items()},
        "fingerprint": feedback.fingerprint(tri["cases"]),
    }
    print("feedback", round(time.time() - t0, 1), "s", file=sys.stderr)
    # the gate on a set of changes
    from pgl.agents.harness import Agent  # noqa: F401  (kept for readers following the flow)

    decisions = {}
    cache_runs = dict(runs)
    for change, (current, cand) in CHANGES.items():
        cand_runs = ev.run(cand, tasks, truth, s.run.repeats)
        cand_reg = feedback.replay(ev, cand, tri["cases"], tasks, truth, s)
        decisions[change] = {
            "current": current,
            **gate.decide(cache_runs[current], cand_runs, replays[current], cand_reg, s),
        }
    out["gate"] = decisions
    out["seconds"] = round(time.time() - t0, 1)
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "dev.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("harnesses", "paired")}, indent=1))
    print(json.dumps(out["feedback"], indent=1))
    for k, d in decisions.items():
        print("BLOCKED" if d["blocked"] else "passes ", k, d["diff"], d["lo"], d["budget"], d["reasons"])


if __name__ == "__main__":
    main()
