"""Pair features for the matcher. Each is something a reviewer would look at to decide 'same place?'."""

from __future__ import annotations

import math

from pgl.geo import haversine_m
from pgl.pipeline.normalize import name_key, similarity, street_key

NAMES = [
    "log_distance",
    "name_similarity",
    "same_name_key",
    "same_housenumber",
    "same_street",
    "same_phone",
    "phone_conflict",
]


def features(a: dict, b: dict) -> list[float]:
    d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    pa, pb = a.get("phone"), b.get("phone")
    return [
        math.log1p(d),
        similarity(a["name"], b["name"]),
        float(name_key(a["name"]) == name_key(b["name"])),
        float(a.get("housenumber") == b.get("housenumber")),
        float(street_key(a.get("street", "")) == street_key(b.get("street", ""))),
        float(bool(pa and pb and pa == pb)),
        float(bool(pa and pb and pa != pb)),
    ]
