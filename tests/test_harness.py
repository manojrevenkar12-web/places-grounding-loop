"""Each guard catches its failure from evidence: scripted models propose the mistake, and the guard has to see it."""

import random

from pgl.agents.harness import GUARDED, PLAIN, PLAN_FETCH, Agent, Meter
from pgl.agents.model import Context
from pgl.servers.places import PlacesService


class Scripted:
    """Proposes the given actions in order, whatever comes back."""

    def __init__(self, actions):
        self.actions = list(actions)

    def next(self, ctx):
        return self.actions.pop(0) if self.actions else {"answer": {"text": "done"}}

    def plan(self, ctx):
        return []


def _ctx(text="Find a cafe that is open now near Rathausplatz."):
    return Context(text=text, day=2, hour=12.5, turn=0)


def _agent(s, rel, g):
    return Agent(PlacesService(rel, s), s, g)


def test_provenance_rejects_invented_coordinates(s, releases):
    _, r2 = releases
    call = {"tool": "category_search", "args": {"category": "cafe", "lat": 52.51, "lon": 13.4, "radius_m": 900,
                                                "day": 2, "hour": 12.5}}
    for g, ran in ((GUARDED, False), (PLAIN, True)):
        ctx = _ctx()
        _agent(s, r2, g).turn(ctx, Scripted([call]), False, random.Random(0), Meter())
        executed = [o for o in ctx.log if o.tool == "category_search" and o.result is not None]
        assert bool(executed) is ran
        assert ran or ctx.log[0].note == "ungrounded"


def test_provenance_accepts_coordinates_from_a_tool_result(s, releases):
    _, r2 = releases
    ctx = _ctx()
    agent = _agent(s, r2, GUARDED)
    agent.svc.reseed(0)
    hit = agent.svc.search_forward("Rathausplatz")["results"][0]
    agent.turn(ctx, Scripted([{"tool": "search_forward", "args": {"query": "Rathausplatz"}},
                              {"tool": "category_search", "args": {"category": "cafe", "lat": hit["lat"],
                                                                   "lon": hit["lon"], "radius_m": 900, "day": 2,
                                                                   "hour": 12.5}}]), False, random.Random(0), Meter())
    assert ctx.log[1].note is None and ctx.log[1].result is not None


def test_loop_guard_stops_a_repeated_empty_call_and_the_budget_ends_the_turn(s, releases):
    _, r2 = releases
    ctx = _ctx()
    agent = _agent(s, r2, GUARDED)
    agent.svc.reseed(0)
    hit = agent.svc.search_forward("Rathausplatz")["results"][0]
    empty = {"tool": "category_search", "args": {"category": "ev_charger", "lat": hit["lat"], "lon": hit["lon"],
                                                 "radius_m": 1, "day": 2, "hour": 12.5}}
    m = Meter()
    ans = agent.turn(ctx, Scripted([{"tool": "search_forward", "args": {"query": "Rathausplatz"}}] + [empty] * 40),
                     False, random.Random(0), m)
    assert ans["stopped"] == "step_budget" and ans["steps"] == s.harness.max_steps
    assert sum(1 for o in ctx.log if o.tool == "category_search" and o.result is not None) == 1
    assert m.trips["loop_guard"] == s.harness.max_steps - 2


def test_plain_loop_runs_to_its_safety_stop(s, releases):
    _, r2 = releases
    ctx = _ctx()
    empty = {"tool": "category_search", "args": {"category": "ev_charger", "lat": 52.5, "lon": 13.4,
                                                 "radius_m": 1, "day": 2, "hour": 12.5}}
    ans = _agent(s, r2, PLAIN).turn(ctx, Scripted([empty] * 40), False, random.Random(0), Meter())
    assert ans["stopped"] == "safety_stop" and ans["steps"] == s.harness.plain_max_steps


def test_freshness_drops_facts_read_at_an_older_version(s, releases):
    from pgl.pipeline.release import apply_event
    _, r2 = releases
    agent = _agent(s, r2, GUARDED)
    pid = next(iter(r2.places))
    ctx = _ctx()
    ctx.memory["place_id"] = pid
    agent.turn(ctx, Scripted([{"tool": "place_details", "args": {"place_id": pid}}]), False, random.Random(0), Meter())
    apply_event(r2, {"place_id": pid, "kind": "closed"})
    ctx.turn, ctx.text = 1, "Is it still open now?"
    m = Meter()
    agent.turn(ctx, Scripted([]), False, random.Random(0), m)
    assert m.trips.get("freshness") == 1
    assert not any(o.tool == "place_details" for o in ctx.obs)


def test_the_cache_is_keyed_by_data_version(s, releases):
    from pgl.pipeline.release import apply_event
    _, r2 = releases
    pid = next(iter(r2.places))
    for mode, stale in (("versioned", False), ("unversioned", True)):
        rel = __import__("copy").deepcopy(r2)
        agent = Agent(PlacesService(rel, s), s, GUARDED.__class__(cache=mode))
        m = Meter()
        agent._run_tool("place_details", {"place_id": pid}, rel.version, m, random.Random(0))
        apply_event(rel, {"place_id": pid, "kind": "closed"})
        r, _, _ = agent._run_tool("place_details", {"place_id": pid}, rel.version, m, random.Random(0))
        assert (r["status"] == "open") is stale


def test_partial_results_are_retried_then_disclosed(s, releases):
    _, r2 = releases
    agent = _agent(s, r2, GUARDED)

    class Lossy:
        def __getattr__(self, name):
            return getattr(agent.svc.__class__, name).__get__(agent.svc)

        def search_forward(self, **kw):
            return {"results": [], "complete": False, "data_version": 0}

    agent.svc = Lossy()
    m = Meter()
    r, _, _ = agent._run_tool("search_forward", {"query": "x"}, 0, m, random.Random(0))
    assert r["complete"] is False and m.trips["partial_retry"] == s.harness.partial_retries
    assert m.tool_calls == 1 + s.harness.partial_retries


def test_ambiguous_twins_are_not_guessed(s, releases):
    from pgl.agents.model import same_as
    hits = [{"kind": "place", "place_id": "a", "name": "Café Brunnen", "street": "Uferstraße", "housenumber": "82"},
            {"kind": "place", "place_id": "b", "name": "Café Brunnen", "street": "Uferstraße", "housenumber": "81"},
            {"kind": "place", "place_id": "c", "name": "Café Brunnen", "street": "Am Markt", "housenumber": "9"}]
    assert [h["place_id"] for h in same_as(hits[0], hits, "Café Brunnen Uferstraße")] == ["a", "b"]
    assert [h["place_id"] for h in same_as(hits[0], hits, "Café Brunnen Uferstraße 82")] == ["a"]


def test_a_plan_runs_independent_calls_in_parallel(s, releases):
    _, r2 = releases
    agent = _agent(s, r2, PLAN_FETCH)

    class Planner(Scripted):
        def plan(self, ctx):
            return [] if ctx.obs else [
                {"tool": "search_forward", "args": {"query": "Rathausplatz"}, "pick": "landmark"},
                {"tool": "search_forward", "args": {"query": "Busbahnhof"}, "pick": "landmark"},
                {"tool": "route", "args": {"from_lat": "$0.lat", "from_lon": "$0.lon", "to_lat": "$1.lat",
                                           "to_lon": "$1.lon", "mode": "walking"}}]
    agent.svc.reseed(0)
    ctx = _ctx("How long does it take to walk from Rathausplatz to Busbahnhof on x?")
    m = Meter()
    agent._plan_turn(ctx, Planner([]), False, random.Random(0), m, 0)
    assert [o.tool for o in ctx.log] == ["search_forward", "search_forward", "route"]
    assert m.tool_calls == 3 and m.model_calls == 1
    assert m.latency_ms < 3 * s.tools.latency_ms * 2 + s.model.latency_ms * 3
