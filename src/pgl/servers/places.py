"""The places dataset as an MCP server: search, category search, details and routes, the shape of the tools a
location platform gives agents. Search is sharded; a shard can time out, and then the result says it is partial.
Every result carries the data version it was read at."""

from __future__ import annotations

import json
import random

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from pgl.geo import haversine_m
from pgl.pipeline.normalize import similarity
from pgl.pipeline.release import Release
from pgl.settings import ROOT, Settings

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
SHARDS = 4


def open_at(p: dict, day: int, hour: float) -> bool | None:
    h = p.get("hours")
    if p["status"] != "open":
        return False
    if not h:
        return None
    if day == 6 and not h.get("sunday", True):
        return False
    return h["open"] <= hour < h["close"]


def shard(place_id: str) -> int:
    return sum(map(ord, place_id)) % SHARDS


class PlacesService:
    """The tool logic, independent of the transport, so the harnesses can be tested without MCP."""

    def __init__(self, rel: Release, s: Settings):
        self.rel, self.s = rel, s
        self.rng = random.Random(0)
        self.landmarks = json.loads((ROOT / "data" / "landmarks.json").read_text())

    def reseed(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def _failed_shard(self) -> int | None:
        return self.rng.randrange(SHARDS) if self.rng.random() < self.s.tools.search_failure else None

    def search_forward(self, query: str, near_lat: float | None = None, near_lon: float | None = None,
                       limit: int = 5) -> dict:
        lost = self._failed_shard()
        q = query.lower()
        out = []
        for m in self.landmarks:
            sim = similarity(m["name"], query)
            if m["name"].lower() in q or sim >= 0.55:
                out.append({"kind": "landmark", "name": m["name"], "lat": m["lat"], "lon": m["lon"], "score": 1 + sim})
        for pid, p in self.rel.places.items():
            if p["status"] != "open" or shard(pid) == lost:
                continue
            sim = max(similarity(p["name"], query), similarity(f"{p['name']} {p['street']}", query),
                      similarity(f"{p['name']} {p['street']} {p['housenumber']}", query))
            if sim < 0.35:
                continue
            bonus = 0.0
            if near_lat is not None:
                bonus += 0.2 / (1 + haversine_m(near_lat, near_lon, p["lat"], p["lon"]) / 1000)
            out.append({"kind": "place", "place_id": pid, "name": p["name"], "category": p["category"],
                        "street": p["street"], "housenumber": p["housenumber"], "lat": p["lat"], "lon": p["lon"],
                        "score": round(sim + bonus, 4)})
        out.sort(key=lambda r: -r["score"])
        return {"results": out[:limit], "complete": lost is None, "data_version": self.rel.version}

    def category_search(self, category: str, lat: float, lon: float, radius_m: float, day: int | None = None,
                        hour: float | None = None, limit: int = 5) -> dict:
        lost = self._failed_shard()
        out = []
        for pid, p in self.rel.places.items():
            if p["category"] != category or p["status"] != "open" or shard(pid) == lost:
                continue
            d = haversine_m(lat, lon, p["lat"], p["lon"])
            if d > radius_m:
                continue
            o = open_at(p, day, hour) if day is not None else None
            if day is not None and o is False:
                continue
            out.append({"place_id": pid, "name": p["name"], "lat": p["lat"], "lon": p["lon"],
                        "distance_m": round(d, 1), "open_now": o})
        out.sort(key=lambda r: (r["open_now"] is None, r["distance_m"]))
        return {"results": out[:limit], "complete": lost is None, "data_version": self.rel.version}

    def place_details(self, place_id: str) -> dict:
        p = self.rel.places.get(place_id)
        if p is None:
            raise ToolError(f"no place {place_id}")
        return {"place_id": place_id, **{k: p[k] for k in ("name", "category", "lat", "lon", "street", "housenumber",
                                                             "hours", "phone", "status")},
                "data_version": self.rel.version}

    def status(self) -> dict:
        return {"data_version": self.rel.version}

    def route(self, from_lat: float, from_lon: float, to_lat: float, to_lon: float, mode: str = "walking") -> dict:
        t = self.s.tools
        d = haversine_m(from_lat, from_lon, to_lat, to_lon) * t.detour_factor
        speed = t.route_speed_walk_kmh if mode == "walking" else t.route_speed_drive_kmh
        return {"distance_m": round(d, 1), "duration_min": round(d / 1000 / speed * 60, 1), "mode": mode}


def server(svc: PlacesService) -> MCPServer:
    srv = MCPServer("places", instructions="Search places, categories, details and routes. Results carry the data "
                    "version and say when they are partial.", log_level="CRITICAL")
    srv.tool(description="Search places and landmarks by name or address, optionally near a point.",
             annotations=READ)(svc.search_forward)
    srv.tool(description="Places of a category within a radius, optionally open at a day (0=Mon) and hour.",
             annotations=READ)(svc.category_search)
    srv.tool(description="Full details of a place: hours, phone, status, data version.",
             annotations=READ)(svc.place_details)
    srv.tool(description="The current data version, to tell whether facts read earlier are still current.",
             annotations=READ)(svc.status)
    srv.tool(description="Walking or driving distance and duration between two points.",
             annotations=READ)(svc.route)
    return srv
