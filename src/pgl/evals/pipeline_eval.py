"""Scores a release against the world's truth, per area. Reads data/truth/; nothing in the pipeline, servers or
agents does (tests/test_isolation.py)."""

from __future__ import annotations

import json
import statistics

from pgl.geo import haversine_m
from pgl.pipeline.release import Release, read_jsonl
from pgl.settings import ROOT, Settings


def truth_places(release: int) -> dict[str, dict]:
    return {p["pid"]: p for p in read_jsonl(ROOT / "data" / "truth" / f"places_r{release}.jsonl")}


def links(release: int) -> dict[str, str]:
    return json.loads((ROOT / "data" / "truth" / "links.json").read_text())[f"r{release}"]


def place_to_truth(rel: Release) -> dict[str, list[str]]:
    lk = links(rel.number)
    return {pid: sorted({lk[k] for k in keys if k in lk}) for pid, keys in rel.members.items()}


def area_of(p: dict, s: Settings) -> str:
    return "dev" if p["lon"] < s.world.heldout_lon_split else "heldout"


def score(rel: Release, s: Settings, area: str, previous: Release | None = None) -> dict:
    truth = truth_places(rel.number)
    mapping = place_to_truth(rel)
    in_area = {pid for pid, t in mapping.items() if t and area_of(truth[t[0]], s) == area}
    by_truth: dict[str, list[str]] = {}
    for pid in in_area:
        for t in mapping[pid]:
            by_truth.setdefault(t, []).append(pid)
    duplicates = sum(len(v) > 1 for v in by_truth.values())
    wrong_merges = sum(len(mapping[pid]) > 1 for pid in in_area)
    errs, hours_ok, hours_n, stale_open = [], 0, 0, 0
    for pid in in_area:
        p, t = rel.places[pid], truth[mapping[pid][0]]
        errs.append(haversine_m(p["lat"], p["lon"], t["lat"], t["lon"]))
        if p["hours"]:
            hours_n += 1
            hours_ok += (p["hours"]["open"], p["hours"]["close"]) == (t["hours"]["open"], t["hours"]["close"])
        if t["status"] == "closed" and p["status"] == "open":
            stale_open += 1
    closed_true = sum(1 for pid in in_area if truth[mapping[pid][0]]["status"] == "closed")
    closed_right = sum(
        1 for pid in in_area if truth[mapping[pid][0]]["status"] == "closed" and rel.places[pid]["status"] == "closed"
    )
    closed_wrong = sum(
        1 for pid in in_area if truth[mapping[pid][0]]["status"] == "open" and rel.places[pid]["status"] == "closed"
    )
    open_truth = [t for t in truth.values() if t["status"] == "open" and area_of(t, s) == area]
    covered = sum(1 for t in open_truth if t["pid"] in by_truth)
    out = {
        "places": len(in_area),
        "completeness": round(covered / max(1, len(open_truth)), 4),
        "duplicates": duplicates,
        "wrong_merges": wrong_merges,
        "position_error_median_m": round(statistics.median(errs), 1) if errs else None,
        "position_error_p90_m": round(sorted(errs)[int(0.9 * (len(errs) - 1))], 1) if errs else None,
        "hours_correct": round(hours_ok / max(1, hours_n), 4),
        "closed_still_listed_open": stale_open,
        "closures_applied": closed_right,
        "closed_in_truth": closed_true,
        "wrongly_closed": closed_wrong,
    }
    if previous is not None:
        prev_map = place_to_truth(previous)
        prev_by_truth = {t[0]: pid for pid, t in prev_map.items() if len(t) == 1}
        stable = total = 0
        for t, pids in by_truth.items():
            if t in prev_by_truth and truth[t]["status"] == "open" and len(pids) == 1:
                total += 1
                stable += pids[0] == prev_by_truth[t]
        out["id_stability"] = round(stable / max(1, total), 4)
        out["id_stability_n"] = total
    return out
