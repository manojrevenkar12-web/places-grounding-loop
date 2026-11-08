"""Three ways to run the same model against the same tools.

- `plain`: the loop most first versions ship. Propose, execute, repeat, with a safety stop.
- `guarded`: the same loop with the guards a production agent needs, each one catching a mistake from evidence:
  arguments must come from the request or a tool result (provenance); a turn starts by checking the data version
  and drops facts read at an older one (freshness); a partial result is retried, and disclosed if it stays partial;
  a call that already came back empty is not run again (loop guard); a step budget; a result cache keyed by data
  version; simple requests routed to a small model.
- `plan_fetch`: the model plans the turn's calls in one go, later calls referring to earlier results; the harness
  runs them, in parallel where they don't depend on each other, then the model answers, with the guarded loop's
  guards and a step-by-step fallback when the plan isn't enough.

Latency and cost are simulated from config: model calls by tokens and size, tool calls with a spread."""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field, replace

from mcp.server.mcpserver.exceptions import ToolError

from pgl.agents.model import Context, Obs, SimulatedModel, request_type, same_as
from pgl.servers.places import PlacesService
from pgl.settings import Settings

COORDS = (("lat", "lon"), ("from_lat", "from_lon"), ("to_lat", "to_lon"))
SEARCHES = ("search_forward", "category_search")


@dataclass(frozen=True)
class Guards:
    style: str = "react"  # react | plan
    provenance: bool = True
    freshness: bool = True
    partial_retry: bool = True
    loop_guard: bool = True
    ambiguity: bool = True
    step_budget: bool = True
    cache: str = "versioned"  # off | versioned | unversioned
    routing: str = "by_type"  # large | by_type | small
    streaming: bool = True


PLAIN = Guards(
    provenance=False,
    freshness=False,
    partial_retry=False,
    loop_guard=False,
    ambiguity=False,
    step_budget=False,
    cache="off",
    routing="large",
    streaming=False,
)
GUARDED = Guards()
PLAN_FETCH = Guards(style="plan")
HARNESSES = {"plain": PLAIN, "guarded": GUARDED, "plan_fetch": PLAN_FETCH}
CHANGES = {  # changes put through the gate, each against the harness it would replace
    "add the guards": ("plain", GUARDED),
    "plan then fetch": ("guarded", PLAN_FETCH),
    "drop the freshness check (one status call less per turn)": ("plan_fetch", replace(PLAN_FETCH, freshness=False)),
    "cache without the version key (more cache hits)": ("plan_fetch", replace(PLAN_FETCH, cache="unversioned")),
    "send every request to the large model": ("plan_fetch", replace(PLAN_FETCH, routing="large")),
    "skip partial-result retries (fewer tool calls)": ("plan_fetch", replace(PLAN_FETCH, partial_retry=False)),
}
ABLATIONS = {
    "guarded without provenance": replace(GUARDED, provenance=False),
    "guarded without freshness": replace(GUARDED, freshness=False),
    "guarded without partial retry": replace(GUARDED, partial_retry=False),
    "guarded without loop guard": replace(GUARDED, loop_guard=False, step_budget=False),
    "guarded without ambiguity check": replace(GUARDED, ambiguity=False),
    "guarded, cache without version key": replace(GUARDED, cache="unversioned"),
    "guarded, large model only": replace(GUARDED, routing="large"),
    "guarded without streaming": replace(GUARDED, streaming=False),
}


@dataclass
class Meter:
    latency_ms: float = 0.0
    cost_eur: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0
    cache_hits: int = 0
    trips: dict = field(default_factory=dict)  # guard -> times it fired
    turn_ms: list = field(default_factory=list)  # time until the user sees each answer start

    def trip(self, name: str) -> None:
        self.trips[name] = self.trips.get(name, 0) + 1


class Agent:
    def __init__(self, svc: PlacesService, s: Settings, guards: Guards, cache: dict | None = None):
        self.svc, self.s, self.g = svc, s, guards
        self.cache = cache if cache is not None else {}

    # ---- costs ----
    def _jitter(self, rng: random.Random, spread: float) -> float:
        return rng.lognormvariate(0, spread)

    def _charge_model(self, ctx: Context, m: Meter, small: bool, rng: random.Random, out_tokens: int) -> None:
        t, md = self.s.tokens, self.s.model
        results = sum(max(1, len((o.result or {}).get("results", [1]))) for o in ctx.obs)
        tin = t.system + 5 * t.per_tool_schema + t.per_result * results + t.action * len(ctx.obs) + len(ctx.text) // 4
        base, per_k = (md.small_latency_ms, md.small_ms_per_1k_in) if small else (md.latency_ms, md.ms_per_1k_in)
        pin, pout = (md.small_price_in, md.small_price_out) if small else (md.price_in, md.price_out)
        m.latency_ms += base * self._jitter(rng, md.latency_spread) + per_k * tin / 1000
        if out_tokens == self.s.tokens.answer and not self.g.streaming:  # the user waits for the whole answer
            m.latency_ms += out_tokens / (md.small_tokens_per_s if small else md.tokens_per_s) * 1000
        m.cost_eur += tin / 1000 * pin + out_tokens / 1000 * pout
        m.model_calls += 1

    def _tool_ms(self, rng: random.Random) -> float:
        return self.s.tools.latency_ms * self._jitter(rng, self.s.tools.latency_spread)

    # ---- tools ----
    def _run_tool(
        self, tool: str, args: dict, version: int | None, m: Meter, rng: random.Random
    ) -> tuple[dict | None, str | None, float]:
        """Executes one call (through the cache, with partial retries). Returns result, error, latency."""
        key = None
        if self.g.cache != "off" and tool != "status":
            key = (tool, json.dumps(args, sort_keys=True)) + ((version,) if self.g.cache == "versioned" else ())
            if key in self.cache:
                m.cache_hits += 1
                return copy.deepcopy(self.cache[key]), None, 2.0
        ms, tries = 0.0, 0
        while True:
            ms += self._tool_ms(rng)
            m.tool_calls += 1
            try:
                r = getattr(self.svc, tool)(**args)
            except ToolError as e:
                return None, str(e), ms
            except TypeError as e:
                return None, f"bad arguments: {e}", ms
            if r.get("complete", True) or not self.g.partial_retry or tries >= self.s.harness.partial_retries:
                break
            tries += 1
            m.trip("partial_retry")
        if key is not None and r.get("complete", True):
            self.cache[key] = copy.deepcopy(r)
        return r, None, ms

    # ---- guards ----
    @staticmethod
    def _grounded(ctx: Context) -> tuple[set, set]:
        pts, ids = set(), set()
        for o in ctx.obs:
            r = o.result
            if not r:
                continue
            for x in r.get("results", [r]):
                if "lat" in x:
                    pts.add((round(x["lat"], 6), round(x["lon"], 6)))
                if "place_id" in x:
                    ids.add(x["place_id"])
        if ctx.memory.get("place_id"):
            ids.add(ctx.memory["place_id"])
        return pts, ids

    def _ungrounded(self, ctx: Context, args: dict) -> str | None:
        pts, ids = self._grounded(ctx)
        for a, b in COORDS:
            if a in args and (round(float(args[a]), 6), round(float(args[b]), 6)) not in pts:
                return f"{a}/{b} were not taken from the request or a tool result"
        if "place_id" in args and args["place_id"] not in ids:
            return f"place_id {args['place_id']} was not returned by a tool"
        return None

    @staticmethod
    def _ambiguous(ctx: Context, args: dict) -> bool:
        """Whether the place an argument came from has a twin in the same search result."""
        for o in ctx.obs:
            if o.tool != "search_forward" or o.turn != ctx.turn or not o.result:
                continue
            hits = o.result["results"]
            for h in hits:
                if h.get("kind") != "place":
                    continue
                used = args.get("place_id") == h["place_id"] or (
                    "to_lat" in args and (args["to_lat"], args["to_lon"]) == (h["lat"], h["lon"])
                )
                if used and len(same_as(h, hits, o.args["query"])) > 1:
                    return True
        return False

    @staticmethod
    def _dup_empty(ctx: Context, tool: str, args: dict) -> bool:
        return any(
            o.tool == tool
            and o.args == args
            and o.turn == ctx.turn
            and o.result is not None
            and o.result.get("complete", True)
            and not o.result.get("results", [1])
            for o in ctx.obs
        )

    def _check(self, ctx: Context, call: dict, m: Meter) -> Obs | None:
        """The guards before a call runs. Returns the note that replaces the call, or None to run it."""
        if self.g.provenance:
            why = self._ungrounded(ctx, call["args"])
            if why:
                m.trip("provenance")
                return Obs(call["tool"], call["args"], error=why, note="ungrounded", turn=ctx.turn)
        if self.g.ambiguity and self._ambiguous(ctx, call["args"]):
            m.trip("ambiguity")
            return Obs(
                call["tool"],
                call["args"],
                error="several places match the request equally; ask which",
                note="ambiguous",
                turn=ctx.turn,
            )
        if self.g.loop_guard and self._dup_empty(ctx, call["tool"], call["args"]):
            m.trip("loop_guard")
            return Obs(
                call["tool"],
                call["args"],
                error="this exact call already returned nothing; change it",
                note="duplicate_empty",
                turn=ctx.turn,
            )
        return None

    def _execute(self, ctx: Context, call: dict, version: int | None, m: Meter, rng: random.Random) -> Obs:
        r, err, ms = self._run_tool(call["tool"], call["args"], version, m, rng)
        m.latency_ms += ms
        note = None
        if r is not None and not r.get("complete", True) and self.g.partial_retry:
            note = "partial_after_retries"
        return Obs(call["tool"], call["args"], result=r, error=err, note=note, turn=ctx.turn)

    # ---- a turn ----
    def turn(self, ctx: Context, model: SimulatedModel, small: bool, rng: random.Random, m: Meter) -> dict:
        version = None
        if self.g.freshness or self.g.cache == "versioned":
            m.latency_ms += self._tool_ms(rng)
            version = self.svc.status()["data_version"]
            if self.g.freshness and ctx.turn > 0:
                stale = [o for o in ctx.obs if o.result and o.result.get("data_version", version) != version]
                if stale:
                    m.trip("freshness")
                    ctx.obs = [o for o in ctx.obs if o not in stale]
                    ctx.add(Obs("status", {}, result={"data_version": version}, note="data_changed", turn=ctx.turn))
        budget = self.s.harness.max_steps if self.g.step_budget else self.s.harness.plain_max_steps
        steps = 0
        if self.g.style == "plan":
            steps += self._plan_turn(ctx, model, small, rng, m, version)
        while steps < budget:
            steps += 1
            act = model.next(ctx)
            self._charge_model(ctx, m, small, rng, self.s.tokens.answer if "answer" in act else self.s.tokens.action)
            if "answer" in act:
                ans = act["answer"]
                if self.g.provenance and ans.get("place_id") and ans["place_id"] not in self._grounded(ctx)[1]:
                    m.trip("provenance")
                    ctx.add(
                        Obs(
                            "answer",
                            ans,
                            error="the answer names a place no tool returned",
                            note="ungrounded",
                            turn=ctx.turn,
                        )
                    )
                    continue
                if self.g.partial_retry and any(
                    o.note == "partial_after_retries" and o.turn == ctx.turn for o in ctx.obs
                ):
                    ans = dict(ans, partial=True)
                return dict(ans, steps=steps)
            note = self._check(ctx, act, m)
            ctx.add(note or self._execute(ctx, act, version, m, rng))
        return {"stopped": "step_budget" if self.g.step_budget else "safety_stop", "steps": steps}

    def _resolve(self, v, picks: dict):
        if isinstance(v, str) and v.startswith("$") and "." in v:
            i, f = v[1:].split(".", 1)
            hit = picks.get(int(i))
            return None if hit is None else hit.get(f)
        return v

    def _plan_turn(
        self, ctx: Context, model: SimulatedModel, small: bool, rng: random.Random, m: Meter, version: int | None
    ) -> int:
        """Runs plans until one completes or the replans run out. Returns the steps used (one per model call)."""
        used = 0
        for _ in range(3):
            plan = model.plan(ctx)
            used += 1
            self._charge_model(ctx, m, small, rng, self.s.tokens.action * max(1, len(plan)))
            if not plan:
                return used
            if self.g.provenance:
                lit = [
                    st
                    for st in plan
                    if self._ungrounded(
                        ctx, {k: v for k, v in st["args"].items() if not (isinstance(v, str) and v.startswith("$"))}
                    )
                ]
                if lit:
                    m.trip("provenance")
                    ctx.add(
                        Obs(
                            lit[0]["tool"],
                            lit[0]["args"],
                            error="plan uses arguments no tool returned",
                            note="ungrounded",
                            turn=ctx.turn,
                        )
                    )
                    continue
            picks, done, ok = {}, set(), True
            while len(done) < len(plan) and ok:
                wave = [
                    i
                    for i, st in enumerate(plan)
                    if i not in done
                    and all(
                        int(v[1:].split(".")[0]) in done
                        for v in st["args"].values()
                        if isinstance(v, str) and v.startswith("$")
                    )
                ]
                if not wave:
                    ok = False
                    break
                wave_ms = 0.0
                for i in wave:
                    st = plan[i]
                    args = {k: self._resolve(v, picks) for k, v in st["args"].items()}
                    done.add(i)
                    if any(v is None for v in args.values()):
                        ok = False
                        break
                    call = {"tool": st["tool"], "args": args}
                    note = self._check(ctx, call, m)
                    if note:
                        ctx.add(note)
                        ok = False
                        break
                    before = m.latency_ms
                    o = self._execute(ctx, call, version, m, rng)
                    wave_ms = max(wave_ms, m.latency_ms - before)
                    m.latency_ms = before
                    ctx.add(o)
                    widen = st.get("on_empty")
                    while (
                        widen
                        and o.result is not None
                        and o.result.get("results") == []
                        and o.result["complete"]
                        and call["args"]["radius_m"] * widen["widen"] <= widen["max_radius_m"]
                    ):
                        # the plan says what to do when nothing is found, so no model round trip is needed
                        m.trip("plan_widen")
                        call = {
                            "tool": call["tool"],
                            "args": dict(call["args"], radius_m=call["args"]["radius_m"] * widen["widen"]),
                        }
                        o = self._execute(ctx, call, version, m, rng)
                        ctx.add(o)
                    hits = (o.result or {}).get("results")
                    if hits is None:
                        picks[i] = o.result
                    else:
                        want = st.get("pick")
                        sel = [h for h in hits if want is None or h.get("kind", "place") == want] or hits
                        picks[i] = sel[0] if sel else None
                        if not sel:
                            ok = False
                            break
                m.latency_ms += wave_ms
            if ok:
                return used
        return used


def run_task(agent: Agent, task: dict, s: Settings, seed: int, on_turn=None) -> dict:
    """Runs every turn of a task. `on_turn(i, answer)` lets the evaluation change the world between turns."""
    rng = random.Random(seed)
    agent.svc.reseed(seed + 1)
    ctx = Context(text="", day=task["now"]["day"], hour=task["now"]["hour"], turn=0)
    m = Meter()
    answers = []
    for i, text in enumerate(task["turns"]):
        ctx.text, ctx.turn = text, i
        small = agent.g.routing == "small" or (
            agent.g.routing == "by_type" and request_type(text) in s.harness.route_small
        )
        model = SimulatedModel(s, random.Random(seed * 31 + i), small=small)
        before = m.latency_ms
        ans = agent.turn(ctx, model, small, rng, m)
        m.turn_ms.append(round(m.latency_ms - before, 1))
        answers.append(ans)
        if ans.get("place_id"):
            ctx.memory["place_id"] = ans["place_id"]
        if on_turn:
            on_turn(i, ans)
    trace = [
        {
            "turn": o.turn,
            "tool": o.tool,
            "args": o.args,
            "note": o.note,
            "error": o.error,
            "complete": (o.result or {}).get("complete"),
            "empty": o.result is not None and o.result.get("results") == [],
            "result": o.result,
        }
        for o in ctx.log
    ]
    return {
        "answers": answers,
        "trace": trace,
        "latency_ms": round(m.latency_ms, 1),
        "turn_ms": m.turn_ms,
        "cost_eur": round(m.cost_eur, 6),
        "model_calls": m.model_calls,
        "tool_calls": m.tool_calls,
        "cache_hits": m.cache_hits,
        "trips": m.trips,
    }
