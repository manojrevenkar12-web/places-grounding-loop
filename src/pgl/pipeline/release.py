"""One release of the places dataset: match the sources, fuse attributes with provenance, keep place ids stable
across deliveries, apply corroborated closures, and check the release before it ships.

`naive=True` builds the release the way a first version often does: same normalised name within a short distance,
and an id derived from the source keys."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

import numpy as np

from pgl.geo import haversine_m
from pgl.pipeline.candidates import pairs_local
from pgl.pipeline.features import features
from pgl.pipeline.normalize import name_key, similarity
from pgl.settings import ROOT, Settings

MODEL = ROOT / "models" / "matcher.json"


def read_jsonl(path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def sources(release: int) -> tuple[list[dict], list[dict]]:
    d = ROOT / "data" / "sources"
    recs = read_jsonl(d / f"community_r{release}.jsonl") + read_jsonl(d / f"partner_r{release}.jsonl")
    return recs, read_jsonl(d / f"feedback_r{release}.jsonl")


@dataclass
class Release:
    number: int
    places: dict[str, dict]
    members: dict[str, list[str]]  # place id -> source keys
    checks: dict = field(default_factory=dict)
    version: int = 0
    blocked: bool = False


class Matcher:
    def __init__(self, coef: list[float], intercept: float):
        self.coef, self.intercept = np.asarray(coef), intercept

    def prob(self, a: dict, b: dict) -> float:
        z = float(np.dot(self.coef, features(a, b)) + self.intercept)
        return 1 / (1 + math.exp(-z))

    @staticmethod
    def load() -> Matcher:
        m = json.loads(MODEL.read_text())
        return Matcher(m["coef"], m["intercept"])


def _match(recs: list[dict], s: Settings, naive: bool) -> list[tuple[str, str]]:
    by = {r["key"]: r for r in recs}
    cand = pairs_local(recs, s.pipeline.cell_m, s.pipeline.max_distance_m)
    scored = []
    if naive:
        for a, b in cand:
            ra, rb = by[a], by[b]
            if (
                name_key(ra["name"]) == name_key(rb["name"])
                and haversine_m(ra["lat"], ra["lon"], rb["lat"], rb["lon"]) <= s.pipeline.naive_match_m
            ):
                scored.append((1.0, a, b))
    else:
        m = Matcher.load()
        for a, b in cand:
            p = m.prob(by[a], by[b])
            if p >= s.pipeline.match_threshold:
                scored.append((p, a, b))
    # one record per source per place: greedy one-to-one by probability
    used, out = set(), []
    for _, a, b in sorted(scored, reverse=True):
        if a not in used and b not in used:
            used |= {a, b}
            out.append((a, b))
    return out


def _fuse(group: list[dict], s: Settings) -> dict:
    com = next((r for r in group if r["source"] == "community"), None)
    par = next((r for r in group if r["source"] == "partner"), None)
    base = com or par
    prov = {}
    if (
        com
        and par
        and haversine_m(com["lat"], com["lon"], par["lat"], par["lon"]) > s.pipeline.coord_prefer_community_m
    ):
        prov["position"] = "community (sources disagree)"
    else:
        prov["position"] = base["source"]
    hours = (par or {}).get("hours") or (com or {}).get("hours")
    prov["hours"] = "partner" if (par or {}).get("hours") else ("community" if hours else None)
    return {
        "name": base["name"],
        "category": base["category"],
        "lat": base["lat"],
        "lon": base["lon"],
        "street": (com or par)["street"],
        "housenumber": base["housenumber"],
        "hours": hours,
        "phone": (par or {}).get("phone"),
        "status": "open",
        "sources": sorted(r["source"] for r in group),
        "provenance": prov,
    }


def _mint(n: int) -> str:
    return f"plc_{n:06d}"


def build(release: int, s: Settings, previous: Release | None = None, naive: bool = False) -> Release:
    recs, fb = sources(release)
    by = {r["key"]: r for r in recs}
    matched = _match(recs, s, naive)
    groups: list[list[dict]] = [[by[a], by[b]] for a, b in matched]
    paired = {k for ab in matched for k in ab}
    groups += [[r] for r in recs if r["key"] not in paired]
    places, members = {}, {}
    prev_by_key = {}
    if previous:
        for pid, keys in previous.members.items():
            for k in keys:
                prev_by_key[k] = pid
    counter = max(
        [int(p.split("_")[1]) for p in (previous.places if previous else {}) if p.split("_")[1].isdigit()] + [0]
    )
    taken = set()
    pending = []
    for g in groups:
        keys = sorted(r["key"] for r in g)
        fused = _fuse(g, s)
        if naive:
            pid = "plc_" + hashlib.sha1("|".join(keys).encode()).hexdigest()[:10]
        else:
            votes = [prev_by_key[k] for k in keys if k in prev_by_key and prev_by_key[k] not in taken]
            pid = max(set(votes), key=votes.count) if votes else None
            if pid is None:
                pending.append((g, keys, fused))
                continue
        taken.add(pid)
        places[pid], members[pid] = fused, keys
    # no shared source key: inherit a previous id nearby with a similar name, else mint a new one
    for g, keys, fused in pending:
        pid = None
        if previous:
            best = None
            for qid, q in previous.places.items():
                if qid in taken or q["category"] != fused["category"]:
                    continue
                d = haversine_m(q["lat"], q["lon"], fused["lat"], fused["lon"])
                if (
                    d <= s.pipeline.inherit_radius_m
                    and similarity(q["name"], fused["name"]) >= s.pipeline.inherit_min_similarity
                ):
                    if best is None or d < best[0]:
                        best = (d, qid)
            pid = best[1] if best else None
        if pid is None:
            counter += 1
            pid = _mint(counter)
        taken.add(pid)
        places[pid], members[pid] = fused, keys
    _closures(places, members, by, fb, s)
    rel = Release(release, places, members)
    rel.checks = checks(rel, previous, s)
    rel.blocked = rel.checks["id_loss_share"] > s.pipeline.max_id_loss_share
    return rel


def _closures(places: dict, members: dict, by: dict, fb: list[dict], s: Settings) -> None:
    """A place closes only with corroboration from independent kinds of signal: the partner feed, the community
    source, and user reports (two or more reports count as one kind: reports alone never close a place)."""
    signals: dict[str, set[str]] = {pid: set() for pid in places}
    for pid, keys in members.items():
        for k in keys:
            if by[k].get("listed_status") == "closed":
                signals[pid].add(by[k]["source"])
    reports: dict[str, int] = {}
    for r in fb:
        near = [
            (haversine_m(p["lat"], p["lon"], r["lat"], r["lon"]), pid)
            for pid, p in places.items()
            if p["category"] == r["category"] and similarity(p["name"], r["name"]) >= 0.5
        ]
        near = [x for x in near if x[0] <= 80]
        if near:
            pid = min(near)[1]
            reports[pid] = reports.get(pid, 0) + 1
            if reports[pid] >= 2:
                signals[pid].add("users")
    for pid, sig in signals.items():
        if len(sig) >= s.pipeline.closure_corroboration:
            places[pid]["status"] = "closed"
            places[pid]["provenance"]["status"] = f"{len(sig)} signals"


def checks(rel: Release, previous: Release | None, s: Settings) -> dict:
    """Checks a release can run on itself, without the world: the three Cs as far as the data shows them."""
    ps = list(rel.places.values())
    both = sum(len(p["sources"]) == 2 for p in ps)
    with_hours = sum(p["hours"] is not None for p in ps)
    disagree = sum("disagree" in p["provenance"]["position"] for p in ps)
    lost = 0.0
    if previous:
        kept = set(rel.places) & set(previous.places)
        lost = 1 - len(kept) / max(1, len(previous.places))
    return {
        "places": len(ps),
        "confirmed_by_both": round(both / max(1, len(ps)), 4),
        "with_hours": round(with_hours / max(1, len(ps)), 4),
        "position_disagreement": round(disagree / max(1, len(ps)), 4),
        "closed": sum(p["status"] == "closed" for p in ps),
        "id_loss_share": round(lost, 4),
    }


def apply_event(rel: Release, event: dict) -> None:
    """Streaming updates between batch releases: hours changes and closures, each bumping the data version."""
    p = rel.places.get(event["place_id"])
    if p is None:
        return
    if event["kind"] == "hours":
        p["hours"] = dict(p["hours"] or {"sunday": True}, open=event["open"], close=event["close"])
    elif event["kind"] == "closed":
        p["status"] = "closed"
    p["updated_version"] = rel.version + 1
    rel.version += 1
