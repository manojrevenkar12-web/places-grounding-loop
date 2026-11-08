import asyncio
import json

import pytest
from mcp import Client

from pgl.servers.places import PlacesService, server


def test_tools_are_listed_read_only_and_answer(s, releases):
    _, r2 = releases
    svc = PlacesService(r2, s)

    async def go():
        async with Client(server(svc)) as c:
            tools = {t.name: t for t in (await c.list_tools()).tools}
            assert set(tools) == {"search_forward", "category_search", "place_details", "route", "status"}
            assert all(t.annotations.read_only_hint for t in tools.values())
            r = await c.call_tool("search_forward", {"query": "Rathausplatz"})
            body = json.loads(r.content[0].text)
            assert body["results"][0]["name"] == "Rathausplatz" and "data_version" in body
            bad = await c.call_tool("place_details", {"place_id": "plc_999999"})
            assert bad.is_error
    asyncio.run(go())


def test_a_lost_shard_is_reported_as_partial(s, releases):
    _, r2 = releases
    svc = PlacesService(r2, s)
    flags = []
    for seed in range(200):
        svc.reseed(seed)
        flags.append(svc.search_forward("Bäckerei")["complete"])
    share = 1 - sum(flags) / len(flags)
    assert 0 < share < 3 * s.tools.search_failure


def test_details_carry_the_version_they_were_read_at(s, releases):
    from pgl.pipeline.release import apply_event
    _, r2 = releases
    svc = PlacesService(r2, s)
    pid = next(iter(r2.places))
    v = svc.place_details(pid)["data_version"]
    apply_event(r2, {"place_id": pid, "kind": "closed"})
    d = svc.place_details(pid)
    assert d["data_version"] == v + 1 and d["status"] == "closed" and svc.status()["data_version"] == v + 1
