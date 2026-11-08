"""The feedback loop: production traffic is logged, users report bad answers (and sometimes good ones by mistake),
a reviewer confirms the reports, and every confirmed failure becomes a regression case that replays the same
request with the same tool behaviour. The log carries no truth; the reviewer's label lives with the cases, on the
evaluation side."""

from __future__ import annotations

import json
import random
import zlib

from pgl.agents.harness import Agent, Guards
from pgl.evals.tasks import Evaluator
from pgl.settings import ROOT, Settings

CASES = ROOT / "evalcases" / "regressions.jsonl"
LOG = ROOT / "logs" / "production.jsonl"


def production(ev: Evaluator, guards: Guards, tasks: list[dict], truth: dict, s: Settings, days: int,
               offset: int = 100) -> tuple[list[dict], list[dict]]:
    """Runs `days` passes of production traffic and returns the log and the scored runs. Users report
    from what they experienced, which the world knows and the log does not."""
    agent = Agent(ev.svc, s, guards, cache={})
    rng = random.Random(s.run.seed + 7)
    log, runs = [], []
    for d in range(offset, offset + days):
        for task in tasks:
            r = ev.one(agent, task, truth[task["id"]], d)
            bad = r["outcome"] != "right"
            reported = rng.random() < (s.eval.user_report_wrong if bad else s.eval.user_report_right)
            log.append({"request": f"{task['id']}@{d}", "task": task["id"], "seed_repeat": d, "turns": task["turns"],
                        "now": task["now"], "answers": r["answers"], "trace": [
                            {k: o[k] for k in ("turn", "tool", "args", "note", "error", "complete", "empty")}
                            for o in r["trace"]], "user_report": reported})
            runs.append(r)
    return log, runs


def triage(log: list[dict], runs: list[dict]) -> dict:
    """A reviewer looks at every reported request. Confirmed failures become cases (one per task and failure
    mode, the first time it is seen); reports of right answers are dropped."""
    by_req = {f"{r['id']}@{r['repeat']}": r for r in runs}
    reported = [e for e in log if e["user_report"]]
    confirmed = [e for e in reported if by_req[e["request"]]["outcome"] != "right"]
    cases, seen = [], set()
    for e in confirmed:
        r = by_req[e["request"]]
        key = (e["task"], tuple(r["modes"]) or ("data",))
        if key in seen:
            continue
        seen.add(key)
        cases.append({"case": f"REG-{len(cases) + 1:03d}", "task": e["task"], "seed_repeat": e["seed_repeat"],
                      "modes": list(key[1]), "found_in": e["request"]})
    missed = sum(1 for r in runs if r["outcome"] != "right") - len(confirmed)
    return {"requests": len(log), "failed": sum(1 for r in runs if r["outcome"] != "right"),
            "reported": len(reported), "false_reports": len(reported) - len(confirmed),
            "confirmed": len(confirmed), "unreported_failures": missed, "cases": cases}


def save_cases(cases: list[dict]) -> None:
    CASES.parent.mkdir(exist_ok=True)
    CASES.write_text("".join(json.dumps(c) + "\n" for c in cases))


def save_log(log: list[dict]) -> None:
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text("".join(json.dumps(e) + "\n" for e in log))


def load_cases() -> list[dict]:
    return [json.loads(l) for l in CASES.read_text().splitlines()] if CASES.exists() else []


def replay(ev: Evaluator, guards: Guards, cases: list[dict], tasks: list[dict], truth: dict, s: Settings) -> dict:
    """Each case with the request's own seed, so the tools fail the way they did in production."""
    by_id = {t["id"]: t for t in tasks}
    agent = Agent(ev.svc, s, guards, cache={})
    out = {}
    for c in cases:
        r = ev.one(agent, by_id[c["task"]], truth[c["task"]], c["seed_repeat"])
        out[c["case"]] = r["outcome"] == "right"
    return out


def fingerprint(cases: list[dict]) -> str:
    return f"{zlib.crc32(json.dumps(cases, sort_keys=True).encode()):08x}"
