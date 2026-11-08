"""Runs agent tasks against a release and scores them with the world's accepted answers. Between the turns of a
follow-up it changes the world the way a live feed does (the place closes or its hours change), so an agent that
answers from what it read earlier is caught."""

from __future__ import annotations

import copy
import json
import zlib
from collections import Counter

from pgl.agents.harness import Agent, Guards, run_task
from pgl.evals.pipeline_eval import place_to_truth
from pgl.pipeline.release import Release, apply_event, read_jsonl
from pgl.servers.places import PlacesService
from pgl.settings import ROOT, Settings

COORDS = (("lat", "lon"), ("from_lat", "from_lon"), ("to_lat", "to_lon"))


def load_tasks(area: str) -> tuple[list[dict], dict[str, dict]]:
    """Tasks and their accepted answers. A request is ambiguous when another open place in the world has the same
    name on the same street (and house number, when the request gives one)."""
    tasks = read_jsonl(ROOT / "data" / f"tasks_{area}.jsonl")
    truth = {t["id"]: t for t in read_jsonl(ROOT / "data" / "truth" / f"tasks_{area}.jsonl")}
    world = read_jsonl(ROOT / "data" / "truth" / "places_r2.jsonl")
    by_pid = {p["pid"]: p for p in world}
    for t in tasks:
        tr = truth[t["id"]]
        if t["kind"] in ("eta", "phone"):
            p = by_pid[tr["accept_pids"][0]]
            same = [
                q
                for q in world
                if q["status"] == "open"
                and q["name"] == p["name"]
                and q["street"] == p["street"]
                and (t["kind"] == "eta" or q["housenumber"] == p["housenumber"])
            ]
            tr["ambiguous"] = len(same) > 1
    return tasks, truth


def seed_of(s: Settings, task_id: str, repeat: int) -> int:
    return zlib.crc32(f"{s.run.seed}:{task_id}:{repeat}".encode())


def open_now(p: dict, day: int, hour: float) -> bool:
    if p["status"] != "open":
        return False
    h = p.get("hours")
    if not h:
        return True
    if day == 6 and not h.get("sunday", True):
        return False
    return h["open"] <= hour < h["close"]


def failure_modes(run: dict, task: dict, truth: dict) -> set[str]:
    """Which production failure modes got past the harness in this run, read from the trace and the answers."""
    found = set()
    pts, ids = set(), set()
    for o in run["trace"]:
        earlier = {a.get("place_id") for a in run["answers"][: o["turn"]]} - {None}
        executed = o["note"] not in ("ungrounded", "duplicate_empty", "ambiguous") and o["tool"] not in (
            "answer",
            "status",
        )
        if executed:
            for x, y in COORDS:
                if x in o["args"] and (round(o["args"][x], 6), round(o["args"][y], 6)) not in pts:
                    found.add("invented_argument")
            if "place_id" in o["args"] and o["args"]["place_id"] not in ids | earlier:
                found.add("invented_argument")
        r = o["result"] or {}
        for h in r.get("results", [r]):
            if "lat" in h:
                pts.add((round(h["lat"], 6), round(h["lon"], 6)))
            if "place_id" in h:
                ids.add(h["place_id"])
    for i, a in enumerate(run["answers"]):
        if truth.get("ambiguous") and a.get("clarify") is None and not a.get("stopped"):
            found.add("guessed_between_matches")
        if a.get("from_turn") is not None and a.get("stale_version"):
            found.add("stale_context")
        if a.get("stopped"):
            found.add("unbounded_loop" if a["stopped"] == "safety_stop" else "step_budget")
        searches = [
            o
            for o in run["trace"]
            if o["turn"] == i and o["tool"] in ("search_forward", "category_search") and o["result"] is not None
        ]
        if searches and searches[-1]["complete"] is False and not a.get("partial") and not a.get("stopped"):
            found.add("silent_partial")
    calls = Counter((o["turn"], o["tool"], json.dumps(o["args"], sort_keys=True)) for o in run["trace"] if o["empty"])
    if any(n >= 3 for n in calls.values()):
        found.add("unbounded_loop")
    return found


def score_turn(
    task: dict, truth: dict, i: int, ans: dict, rel: Release, mapping: dict, s: Settings, expect_open: bool | None
) -> str:
    """'right', 'wrong' or 'no_answer'. Asking which place is meant is right when the request is ambiguous."""
    kind = task["kind"]
    if ans.get("clarify") is not None:
        return "right" if truth.get("ambiguous") else "no_answer"
    if ans.get("stopped") or ans.get("found") is False or ans.get("text"):
        return "no_answer"
    if kind == "follow_up" and i == 1:
        return "right" if ans.get("open") == expect_open else "wrong"
    if kind in ("nearest_open", "sparse", "follow_up"):
        pid = ans.get("place_id")
        hit = pid in mapping and set(mapping[pid]) & set(truth["accept_pids"])
        return "right" if hit and ans.get("open") else "wrong"
    if kind == "eta":
        mins = ans.get("minutes")
        if mins is None:
            return "no_answer"
        return "right" if abs(mins - truth["eta_min"]) <= s.eval.eta_tolerance * truth["eta_min"] else "wrong"
    if kind == "phone":
        if ans.get("phone") is None:
            return "no_answer"
        return "right" if ans["phone"] == truth["phone"] else "wrong"
    return "wrong"


class Evaluator:
    def __init__(self, rel: Release, s: Settings):
        self.rel, self.s = rel, s
        self.mapping = place_to_truth(rel)
        self.svc = PlacesService(rel, s)

    def run(
        self,
        guards: Guards,
        tasks: list[dict],
        truth: dict,
        repeats: int,
        repeat_offset: int = 0,
        cache: dict | None = None,
    ) -> list[dict]:
        agent = Agent(self.svc, self.s, guards, cache={} if cache is None else cache)
        out = []
        for r in range(repeat_offset, repeat_offset + repeats):
            for task in tasks:
                out.append(self.one(agent, task, truth[task["id"]], r))
        return out

    def one(self, agent: Agent, task: dict, truth: dict, repeat: int) -> dict:
        s, rel = self.s, self.rel
        seed = seed_of(s, task["id"], repeat)
        saved, expect = {}, [None]

        def on_turn(i: int, ans: dict) -> None:
            if task["kind"] != "follow_up" or i != 0:
                return
            pid = ans.get("place_id")
            p = rel.places.get(pid)
            if p is None:
                return
            saved[pid] = copy.deepcopy(p)
            if zlib.crc32(f"change:{task['id']}:{repeat}".encode()) % 1000 < s.eval.follow_up_change_share * 1000:
                if zlib.crc32(f"kind:{task['id']}:{repeat}".encode()) % 2:
                    apply_event(rel, {"place_id": pid, "kind": "closed"})
                else:
                    h = p.get("hours") or {}
                    apply_event(
                        rel,
                        {
                            "place_id": pid,
                            "kind": "hours",
                            "open": h.get("open", 8),
                            "close": max(h.get("open", 8) + 1, task["now"]["hour"] - 0.5),
                        },
                    )
                    if open_now(rel.places[pid], task["now"]["day"], task["now"]["hour"]):
                        apply_event(rel, {"place_id": pid, "kind": "closed"})
            expect[0] = open_now(rel.places[pid], task["now"]["day"], task["now"]["hour"])

        run = run_task(agent, task, s, seed, on_turn)
        version_now = rel.version
        for a in run["answers"]:
            if a.get("from_turn") is not None:
                a["stale_version"] = a.get("data_version") != version_now
        verdicts = [
            score_turn(task, truth, i, a, rel, self.mapping, s, expect[0]) for i, a in enumerate(run["answers"])
        ]
        for pid, p in saved.items():  # the world goes back for the next task, as a new data version
            rel.places[pid] = p
            rel.version += 1
        outcome = "right" if all(v == "right" for v in verdicts) else "wrong" if "wrong" in verdicts else "no_answer"
        return {
            "id": task["id"],
            "kind": task["kind"],
            "repeat": repeat,
            "outcome": outcome,
            "verdicts": verdicts,
            "modes": sorted(failure_modes(run, task, truth)),
            "latency_ms": run["latency_ms"],
            "turn_ms": run["turn_ms"],
            "cost_eur": run["cost_eur"],
            "model_calls": run["model_calls"],
            "tool_calls": run["tool_calls"],
            "cache_hits": run["cache_hits"],
            "trips": run["trips"],
            "answers": run["answers"],
            "trace": run["trace"],
        }
