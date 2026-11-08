"""A simulated tool-calling model. It reads the request and the observations in its context and proposes the next
tool call or the answer, and it makes the mistakes production agents make, at the rates in config:

- it invents an argument (coordinates or a place id) instead of taking one from a tool result;
- it answers a follow-up from details it fetched in an earlier turn;
- it treats a partial search result as complete;
- it repeats a search that came back empty instead of changing it.

The harness only sees what the model proposes, the way it would with a real model, so every guard in
`harness.py` has to catch a mistake from evidence, not from a flag. A live model can replace this class: it
has to implement `next()` and `plan()` with the same inputs and outputs."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from pgl.settings import Settings

CATEGORY = re.compile(r"Find an? (.+?) that is open now near (.+)\.")
ETA = re.compile(r"How long does it take to walk from (.+) to (.+) on (.+)\?")
PHONE = re.compile(r"What is the phone number of (.+) on (.+)\?")
FOLLOW = re.compile(r"Is it still open now\?")


def intent(text: str) -> tuple[str, tuple]:
    for name, rx in (("category", CATEGORY), ("eta", ETA), ("phone", PHONE), ("follow_up", FOLLOW)):
        m = rx.search(text)
        if m:
            return name, m.groups()
    return "unknown", ()


def request_type(text: str) -> str:
    """The router's input: a request type from the wording, in code."""
    kind, _ = intent(text)
    return {"category": "search", "eta": "eta", "phone": "phone", "follow_up": "follow_up"}.get(kind, "unknown")


@dataclass
class Obs:
    """One observation in the model's context: the call it made and what came back (or a note from the harness)."""
    tool: str
    args: dict
    result: dict | None = None
    error: str | None = None
    note: str | None = None
    turn: int = 0


@dataclass
class Context:
    text: str
    day: int
    hour: float
    turn: int
    obs: list[Obs] = field(default_factory=list)
    memory: dict = field(default_factory=dict)   # what the model said in earlier turns (its own answers)
    draws: dict = field(default_factory=dict)
    log: list[Obs] = field(default_factory=list)   # everything that happened, kept for the trace

    def add(self, o: Obs) -> None:
        self.obs.append(o)
        self.log.append(o)

    def rejections(self) -> int:
        return sum(1 for o in self.obs if o.turn == self.turn and o.note == "ungrounded")


class SimulatedModel:
    def __init__(self, s: Settings, rng: random.Random, small: bool = False):
        m = s.model
        extra = m.small_extra_error if small else 0.0
        self.p_halluc = m.hallucinate_argument + extra
        self.p_stale = m.reuse_stale + extra
        self.p_partial = m.ignore_partial + extra
        self.p_repeat = m.repeat_on_empty + extra
        self.p_guess = m.guess_when_ambiguous + extra
        self.rng, self.s, self.small = rng, s, small
        w = s.world
        self.box = (w.lat_min, w.lat_max, w.lon_min, w.lon_max)

    # invented arguments look plausible: a point in the city, an id in the right format
    def _invent_point(self) -> tuple[float, float]:
        a, b, c, d = self.box
        return round(self.rng.uniform(a, b), 6), round(self.rng.uniform(c, d), 6)

    def _invent_id(self) -> str:
        return f"plc_{self.rng.randint(1, 1500):06d}"

    def _draw(self, ctx: Context, key: str, p: float) -> bool:
        """One decision per slot and attempt, so asking the model again for the same step gives the same choice
        until the harness has pushed back."""
        k = (ctx.turn, key, ctx.rejections())
        if k not in ctx.draws:
            ctx.draws[k] = self.rng.random() < p
        return ctx.draws[k]

    def _last(self, ctx: Context, tool: str) -> Obs | None:
        """The last call of `tool` this turn that ran, or that the harness answered with a note."""
        for o in reversed(ctx.obs):
            if o.tool == tool and o.turn == ctx.turn and (o.result is not None or o.note == "duplicate_empty"):
                return o
        return None

    def _pick(self, ctx: Context, hits: list[dict], query: str, slot: str) -> dict:
        """The first hit, unless another one matches the request just as well: then it asks which one is meant,
        or (at the configured rate) guesses."""
        if any(o.note == "ambiguous" and o.turn == ctx.turn for o in ctx.obs):
            return {"answer": {"clarify": [h["place_id"] for h in same_as(hits[0], hits, query)]}}
        twins = same_as(hits[0], hits, query)
        if len(twins) > 1 and not self._draw(ctx, f"guess:{slot}", self.p_guess):
            return {"answer": {"clarify": [h["place_id"] for h in twins]}}
        return hits[0]

    def _search_result(self, o: Obs, ctx: Context) -> dict | None:
        """Takes a search result. A partial one is retried unless the model doesn't notice it is partial."""
        r = o.result
        if r["complete"] or o.note == "partial_after_retries":
            return r
        seen = sum(1 for x in ctx.obs if x.tool == o.tool and x.args == o.args and x.turn == ctx.turn)
        if seen >= 3 or self._draw(ctx, f"partial:{id(o)}", self.p_partial):
            return r
        return None

    def next(self, ctx: Context) -> dict:
        kind, g = intent(ctx.text)
        if kind == "category":
            return self._category(ctx, g[0].replace(" ", "_"), g[1])
        if kind == "eta":
            return self._eta(ctx, *g)
        if kind == "phone":
            return self._phone(ctx, *g)
        if kind == "follow_up":
            return self._follow_up(ctx)
        return {"answer": {"text": "I can't help with that."}}

    def _geocode(self, ctx: Context, query: str, want: str) -> dict | tuple[float, float]:
        """Returns coordinates for `query` from a search result, or the search call to make."""
        for o in reversed(ctx.obs):
            if o.tool == "search_forward" and o.args.get("query") == query and o.turn == ctx.turn and o.result:
                r = self._search_result(o, ctx)
                if r is None:
                    return {"tool": "search_forward", "args": {"query": query}}
                hits = [x for x in r["results"] if x["kind"] == want] or r["results"]
                if not hits:
                    return {"answer": {"text": f"I couldn't find {query}.", "found": False}}
                h = self._pick(ctx, hits, query, query) if want == "place" else hits[0]
                if "answer" in h:
                    return h
                return h["lat"], h["lon"]
        return {"tool": "search_forward", "args": {"query": query}}

    def _category(self, ctx: Context, cat: str, near: str) -> dict:
        last = self._last(ctx, "category_search")
        if last is None:
            if self._draw(ctx, "coords", self.p_halluc):     # skips the geocode and makes a point up
                lat, lon = self._invent_point()
            else:
                pt = self._geocode(ctx, near, "landmark")
                if isinstance(pt, dict):
                    return pt
                lat, lon = pt
            return {"tool": "category_search", "args": {"category": cat, "lat": lat, "lon": lon,
                                                        "radius_m": self.s.harness.start_radius_m,
                                                        "day": ctx.day, "hour": ctx.hour}}
        if last.note == "duplicate_empty" or (not last.result["results"] and last.result["complete"]):
            args = dict(last.args)
            if last.note != "duplicate_empty" and self._draw(ctx, f"repeat:{id(last)}", self.p_repeat):
                return {"tool": "category_search", "args": args}
            args["radius_m"] = args["radius_m"] * self.s.harness.widen_radius_factor
            return {"tool": "category_search", "args": args}
        r = self._search_result(last, ctx)
        if r is None:
            return {"tool": "category_search", "args": dict(last.args)}
        if not r["results"]:
            return {"tool": "category_search", "args": dict(last.args)}
        top = r["results"][0]
        det = self._last(ctx, "place_details")
        if det is None:
            pid = self._invent_id() if self._draw(ctx, "pid", self.p_halluc) else top["place_id"]
            return {"tool": "place_details", "args": {"place_id": pid}}
        d = det.result
        return {"answer": {"place_id": d["place_id"], "name": d["name"], "open": _open(d, ctx),
                           "closes": (d["hours"] or {}).get("close"), "partial": last.note == "partial_after_retries",
                           "data_version": d["data_version"]}}

    def _follow_up(self, ctx: Context) -> dict:
        pid = ctx.memory.get("place_id")
        if pid is None:
            return {"answer": {"text": "Which place do you mean?"}}
        det = self._last(ctx, "place_details")
        if det is None:
            earlier = [o for o in ctx.obs if o.tool == "place_details" and o.result
                       and o.result.get("place_id") == pid and o.turn < ctx.turn]
            if earlier and self._draw(ctx, "stale", self.p_stale):      # answers from what it read last turn
                d = earlier[-1].result
                return {"answer": {"place_id": pid, "open": _open(d, ctx), "data_version": d["data_version"],
                                   "from_turn": earlier[-1].turn}}
            return {"tool": "place_details", "args": {"place_id": pid}}
        d = det.result
        return {"answer": {"place_id": pid, "open": _open(d, ctx), "data_version": d["data_version"]}}

    def _eta(self, ctx: Context, origin: str, name: str, street: str) -> dict:
        a = self._geocode(ctx, origin, "landmark")
        if isinstance(a, dict):
            return a
        target = f"{name} {street}"
        if self._last(ctx, "route") is None and self._draw(ctx, "dest", self.p_halluc):
            b = self._invent_point()
        else:
            b = self._geocode(ctx, target, "place")
            if isinstance(b, dict):
                return b
        rt = self._last(ctx, "route")
        if rt is None:
            return {"tool": "route", "args": {"from_lat": a[0], "from_lon": a[1], "to_lat": b[0], "to_lon": b[1],
                                              "mode": "walking"}}
        return {"answer": {"minutes": rt.result["duration_min"]}}

    def _phone(self, ctx: Context, name: str, addr: str) -> dict:
        target = f"{name} {addr}"
        det = self._last(ctx, "place_details")
        if det is None:
            o = next((x for x in reversed(ctx.obs) if x.tool == "search_forward" and x.turn == ctx.turn
                      and x.result), None)
            if o is None:
                return {"tool": "search_forward", "args": {"query": target}}
            r = self._search_result(o, ctx)
            if r is None:
                return {"tool": "search_forward", "args": {"query": target}}
            hits = [x for x in r["results"] if x["kind"] == "place"]
            if not hits:
                return {"answer": {"phone": None, "found": False}}
            h = self._pick(ctx, hits, target, "phone")
            if "answer" in h:
                return h
            pid = self._invent_id() if self._draw(ctx, "pid", self.p_halluc) else h["place_id"]
            return {"tool": "place_details", "args": {"place_id": pid}}
        return {"answer": {"place_id": det.result["place_id"], "phone": det.result["phone"]}}

    # plan-then-fetch: the whole turn as one plan, later steps referring to earlier results
    def plan(self, ctx: Context) -> list[dict]:
        kind, g = intent(ctx.text)
        R = "$"
        if kind == "category":
            cat, near = g[0].replace(" ", "_"), g[1]
            last = self._last(ctx, "category_search")
            radius = self.s.harness.start_radius_m
            if last is not None and (last.note == "duplicate_empty" or not last.result["results"]):
                radius = last.args["radius_m"]
                if last.note == "duplicate_empty" or not self._draw(ctx, f"repeat:{id(last)}", self.p_repeat):
                    radius *= self.s.harness.widen_radius_factor
            if self._draw(ctx, "coords", self.p_halluc):
                lat, lon = self._invent_point()
                first = []
                coords = {"lat": lat, "lon": lon}
            else:
                first = [{"tool": "search_forward", "args": {"query": near}, "pick": "landmark"}]
                coords = {"lat": f"{R}0.lat", "lon": f"{R}0.lon"}
            n = len(first)
            return first + [
                {"tool": "category_search", "args": {"category": cat, **coords, "radius_m": radius,
                                                     "day": ctx.day, "hour": ctx.hour},
                 "on_empty": {"widen": self.s.harness.widen_radius_factor,
                              "max_radius_m": self.s.harness.max_radius_m}},
                {"tool": "place_details", "args": {"place_id": f"{R}{n}.place_id"}}]
        if kind == "eta":
            origin, name, street = g
            b = ({"to_lat": "$1.lat", "to_lon": "$1.lon"} if not self._draw(ctx, "dest", self.p_halluc) else
                 dict(zip(("to_lat", "to_lon"), self._invent_point())))
            return [{"tool": "search_forward", "args": {"query": origin}, "pick": "landmark"},
                    {"tool": "search_forward", "args": {"query": f"{name} {street}"}, "pick": "place"},
                    {"tool": "route", "args": {"from_lat": "$0.lat", "from_lon": "$0.lon", **b, "mode": "walking"}}]
        if kind == "phone":
            pid = "$0.place_id" if not self._draw(ctx, "pid", self.p_halluc) else self._invent_id()
            return [{"tool": "search_forward", "args": {"query": " ".join(g)}, "pick": "place"},
                    {"tool": "place_details", "args": {"place_id": pid}}]
        if kind == "follow_up":
            pid = ctx.memory.get("place_id")
            earlier = [o for o in ctx.obs if o.tool == "place_details" and o.result and o.turn < ctx.turn
                       and o.result.get("place_id") == pid]
            if earlier and self._draw(ctx, "stale", self.p_stale):
                return []
            return [{"tool": "place_details", "args": {"place_id": pid}}] if pid else []
        return []

    def answer_from(self, ctx: Context) -> dict:
        """After a plan ran: the answer from the observations of this turn (or, for a stale follow-up, the last)."""
        return self.next(ctx)


def same_as(hit: dict, hits: list[dict], query: str) -> list[dict]:
    """Hits that match the request exactly as well as `hit`: same name and street, and the same house number when
    the request gives one."""
    from pgl.pipeline.normalize import name_key, street_key
    num = hit.get("housenumber") if f" {hit.get('housenumber')}" in f" {query} " else None
    key = (name_key(hit["name"]), street_key(hit.get("street", "")), num)
    return [h for h in hits if h.get("kind") == "place" and
            (name_key(h["name"]), street_key(h.get("street", "")), num and h.get("housenumber")) == key]


def _open(d: dict, ctx: Context) -> bool:
    h = d.get("hours")
    if d["status"] != "open":
        return False
    if not h:
        return True
    if ctx.day == 6 and not h.get("sunday", True):
        return False
    return h["open"] <= ctx.hour < h["close"]
