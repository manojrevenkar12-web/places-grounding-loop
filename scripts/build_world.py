"""Builds the synthetic world: true places, what three sources say about them in two deliveries, the changes in
between, a gazetteer of landmarks, and agent tasks with their accepted answers. Deterministic.

    python scripts/build_world.py

data/sources/, data/landmarks.json and data/tasks_*.jsonl are what the system may read.
data/truth/ is for training the matcher on the development area and for scoring, nothing else.
"""

from __future__ import annotations

import json
import math
import random
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pgl.geo import haversine_m, offset  # noqa: E402

CFG = tomllib.loads((ROOT / "config" / "pgl.toml").read_text())
W = CFG["world"]
DATA, TRUTH, SOURCES = ROOT / "data", ROOT / "data" / "truth", ROOT / "data" / "sources"

STREETS = ["Lindenstraße", "Gartenweg", "Am Markt", "Bahnhofstraße", "Schulstraße", "Parkallee", "Kastanienweg",
           "Wiesenstraße", "Uferstraße", "Brunnenstraße", "Ahornweg", "Mühlenstraße", "Kirchplatz", "Seestraße",
           "Birkenallee", "Feldstraße", "Hafenweg", "Rosenstraße", "Waldstraße", "Brückenstraße"]
DISTRICTS = ["Nordkiez", "Westend", "Altstadt", "Südpark", "Spreebogen", "Hafenviertel", "Ostbahnhof", "Seeufer"]
WORDS = ["Linden", "Markt", "Rosen", "Stern", "Adler", "Park", "Bahnhof", "Spree", "Kiez", "Sonnen", "Brunnen",
         "Eichen", "Mond", "Turm", "Hafen", "Wiesen"]
SURNAMES = ["Krüger", "Weber", "Hoffmann", "Schulz", "Becker", "Wagner", "Richter", "Klein", "Wolf", "Neumann"]
CHAINS = {"supermarket": ["FrischMarkt", "Kaufgut"], "fuel": ["Tankpunkt"], "ev_charger": ["Ladewerk"],
          "pharmacy": ["Gesundpunkt Apotheke"], "cafe": ["Bohnenwerk"], "bakery": ["Kornfeld"]}
CATEGORIES = {"pharmacy": 0.13, "cafe": 0.17, "bakery": 0.13, "supermarket": 0.12, "restaurant": 0.18,
              "ev_charger": 0.09, "fuel": 0.05, "post_office": 0.04, "atm": 0.09}
HOURS = {"pharmacy": [(8, 20), (8, 18.5), (0, 24)], "cafe": [(7, 19), (8, 18), (9, 23)], "bakery": [(6, 18), (6.5, 14)],
         "supermarket": [(7, 22), (8, 21), (7, 24)], "restaurant": [(11.5, 23), (17, 23.5), (12, 22)],
         "ev_charger": [(0, 24)], "fuel": [(0, 24), (6, 22)], "post_office": [(9, 18), (8, 12)], "atm": [(0, 24)]}
LANDMARKS = ["Rathausplatz", "Nordbahnhof", "Stadtpark Eingang Süd", "Markthalle", "Spreebrücke", "Kulturhaus",
             "Messehalle", "Zentralbibliothek", "Hafenturm", "Seebad", "Kunsthalle", "Universitätsplatz",
             "Busbahnhof", "Stadion", "Kirche am Markt", "Rosengarten"]


def name_for(rng, cat: str, chain: str | None, street: str) -> str:
    if chain:
        return chain
    w, s = rng.choice(WORDS), rng.choice(SURNAMES)
    return {"pharmacy": f"{w}-Apotheke", "cafe": f"Café {w}", "bakery": f"Bäckerei {s}",
            "supermarket": f"{s} Lebensmittel", "restaurant": rng.choice([f"Trattoria {w}", f"Imbiss {s}",
                                                                          f"Gasthaus {w}", f"Bistro {w}"]),
            "ev_charger": f"Ladestation {street}", "fuel": f"Tankstelle {s}", "post_office": f"Postfiliale {w}",
            "atm": f"Geldautomat {w}bank"}[cat]


def variant(rng, name: str) -> str:
    """How another source writes the same name."""
    options = [name.replace("-", " "), name.replace("Café", "Cafe"), name + " GmbH", name.upper(),
               " ".join(reversed(name.split())) if " " in name else name, name.replace("straße", "str."),
               name.replace("Bäckerei", "Backstube"), name + " e.K."]
    return rng.choice([o for o in options if o != name] or [name + " GmbH"])


def build_places(rng) -> list[dict]:
    places, buildings = [], 0
    cats, weights = zip(*CATEGORIES.items(), strict=True)
    i = 0
    while len(places) < W["places"]:
        cat = rng.choices(cats, weights)[0]
        lat = rng.uniform(W["lat_min"], W["lat_max"])
        lon = rng.uniform(W["lon_min"], W["lon_max"])
        chain = rng.choice(CHAINS[cat]) if cat in CHAINS and rng.random() < W["chain_share"] * 2 else None
        street, number = rng.choice(STREETS), rng.randint(1, 140)
        buildings += 1
        group = [(lat, lon)]
        if rng.random() < W["shared_building_share"]:
            group.append(offset(lat, lon, rng.uniform(4, 12), rng.uniform(0, 360)))  # a second shop, same building
        for k, (la, lo) in enumerate(group):
            i += 1
            o, c = rng.choice(HOURS[cat])
            places.append({
                "pid": f"W{i:05d}", "name": name_for(rng, cat, chain if k == 0 else None, street), "brand": chain if k == 0 else None,
                "category": cat, "lat": round(la, 6), "lon": round(lo, 6), "street": street,
                "housenumber": str(number), "postcode": f"10{rng.randint(115, 999)}",
                "district": DISTRICTS[int((lo - W["lon_min"]) / (W["lon_max"] - W["lon_min"]) * 4) * 2 % 8
                                      + (1 if la > (W["lat_min"] + W["lat_max"]) / 2 else 0)],
                "building_id": f"B{buildings:05d}", "phone": f"+49 30 {rng.randint(1000000, 9999999)}",
                "hours": {"open": o, "close": c, "sunday": cat in ("pharmacy", "ev_charger", "fuel", "atm", "restaurant")
                          or rng.random() < 0.3},
                "status": "open",
            })
    return places


def apply_changes(rng, places: list[dict]) -> tuple[list[dict], list[dict]]:
    """Release 2: some places close, some open, some change hours. Returns the new truth and the change log."""
    ch = CFG["changes"]
    new = [dict(p, hours=dict(p["hours"])) for p in places]
    log = []
    for p in rng.sample([p for p in new if p["status"] == "open"], ch["closures"]):
        p["status"] = "closed"
        log.append({"kind": "closed", "pid": p["pid"]})
    for p in rng.sample([p for p in new if p["status"] == "open"], ch["hours_changes"]):
        o, c = rng.choice(HOURS[p["category"]])
        if (o, c) == (p["hours"]["open"], p["hours"]["close"]):
            c = max(o + 2, c - 2)
        p["hours"].update(open=o, close=c)
        log.append({"kind": "hours", "pid": p["pid"]})
    extra = build_places(random.Random(rng.random()))[: ch["openings"]]
    for j, p in enumerate(extra):
        p["pid"] = f"N{j + 1:05d}"
        p["building_id"] = f"NB{j + 1:05d}"
        new.append(p)
        log.append({"kind": "opened", "pid": p["pid"]})
    return new, log


def jitter(rng, p: dict, noise_m: float) -> tuple[float, float]:
    return offset(p["lat"], p["lon"], abs(rng.gauss(0, noise_m)), rng.uniform(0, 360))


def deliver(rng, truth: list[dict], previous: dict | None, release: int):
    """What each source delivers for one release. Returns source records and a record -> true place link."""
    out = {"community": [], "partner": []}
    links = {}
    c, pt = CFG["sources"]["community"], CFG["sources"]["partner"]
    prev_keys = previous or {}
    for p in truth:
        if p["status"] == "closed" and rng.random() < 0.6:
            continue  # most sources drop a closed place; some still list it
        if rng.random() < c["coverage"] or (previous and f"c:{p['pid']}" in prev_keys):
            key = prev_keys.get(f"c:{p['pid']}") or f"osm/{rng.randint(10**8, 10**9)}"
            prev_keys[f"c:{p['pid']}"] = key
            la, lo = jitter(rng, p, c["coord_noise_m"])
            hours = None
            if rng.random() < c["hours_share"]:
                hours = dict(p["hours"])
                if rng.random() < c["stale_hours_share"]:
                    hours["close"] = max(hours["open"] + 1, hours["close"] - rng.choice([1, 2, 3]))
            rec = {"key": key, "source": "community", "name": variant(rng, p["name"]) if rng.random() < c["name_variant_share"]
                   else p["name"], "category": p["category"], "lat": round(la, 6), "lon": round(lo, 6),
                   "street": p["street"], "housenumber": p["housenumber"], "hours": hours, "phone": None,
                   "listed_status": p["status"] if rng.random() < 0.3 else "open", "release": release}
            out["community"].append(rec)
            links[key] = p["pid"]
        if rng.random() < pt["coverage"] or (previous and f"p:{p['pid']}" in prev_keys):
            key = prev_keys.get(f"p:{p['pid']}")
            if key is None or rng.random() < pt["rekey_share"]:
                key = f"partner/{rng.randint(10**6, 10**7)}"
            prev_keys[f"p:{p['pid']}"] = key
            la, lo = jitter(rng, p, pt["coord_noise_m"])
            hours = dict(p["hours"]) if rng.random() < pt["hours_share"] else None
            if hours and rng.random() < pt["stale_hours_share"]:
                hours["open"] = hours["open"] + 1
            rec = {"key": key, "source": "partner", "name": variant(rng, p["name"]) if rng.random() < pt["name_variant_share"]
                   else p["name"], "category": p["category"], "lat": round(la, 6), "lon": round(lo, 6),
                   "street": p["street"].replace("straße", "str."), "housenumber": p["housenumber"], "hours": hours,
                   "phone": p["phone"] if rng.random() < pt["phone_share"] else None,
                   "listed_status": p["status"], "release": release}
            out["partner"].append(rec)
            links[key] = p["pid"]
    for v in out.values():
        rng.shuffle(v)
    return out, links, prev_keys


def feedback(rng, truth: list[dict], release: int) -> list[dict]:
    f = CFG["sources"]["feedback"]
    closed = [p for p in truth if p["status"] == "closed"]
    reports = []
    for i in range(f["reports"]):
        false = rng.random() < f["false_report_share"] or not closed
        p = rng.choice(truth) if false else rng.choice(closed)
        reports.append({"key": f"fb/{release}/{i}", "source": "feedback", "kind": "closed", "lat": p["lat"],
                        "lon": p["lon"], "name": p["name"], "category": p["category"], "release": release,
                        "_true": not false and p["status"] == "closed", "_pid": p["pid"]})
    return reports


def open_at(p: dict, day: int, hour: float) -> bool:
    h = p["hours"]
    if p["status"] != "open" or (day == 6 and not h["sunday"]):
        return False
    return h["open"] <= hour < h["close"]


def tasks(rng, truth: list[dict], landmarks: list[dict], area: str, n: int, prefix: str):
    """Agent tasks and their accepted answers, on release-2 truth."""
    sp = CFG["tools"]
    in_area = [p for p in truth if (p["lon"] < W["heldout_lon_split"]) == (area == "dev")]
    marks = [m for m in landmarks if (m["lon"] < W["heldout_lon_split"]) == (area == "dev")]
    out, accepted = [], []
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    kinds = ["nearest_open", "eta", "follow_up", "phone", "sparse"]
    for i in range(n):
        kind = kinds[i % len(kinds)]
        m = rng.choice(marks)
        day, hour = rng.randrange(7), rng.choice([7.5, 9, 12.5, 16, 19.5, 21.5, 23])
        now = f"{days[day]} {int(hour):02d}:{int(round(hour % 1 * 60)):02d}"
        tid = f"{prefix}-{i + 1:03d}"
        if kind in ("nearest_open", "follow_up", "sparse"):
            cats = ["ev_charger", "post_office", "fuel"] if kind == "sparse" else ["pharmacy", "cafe", "bakery",
                                                                                     "supermarket", "restaurant"]
            cat = rng.choice(cats)
            cands = sorted(((haversine_m(m["lat"], m["lon"], p["lat"], p["lon"]), p) for p in truth
                            if p["category"] == cat and open_at(p, day, hour)), key=lambda x: x[0])
            if not cands:
                continue
            best = cands[0][0]
            ok = [p["pid"] for d, p in cands if d <= best * 1.25 + 150]
            q = f"Find a {cat.replace('_', ' ')} that is open now near {m['name']}."
            if kind == "follow_up":
                q2 = "Is it still open now?"
                out.append({"id": tid, "kind": kind, "now": {"day": day, "hour": hour, "text": now}, "turns": [q, q2],
                            "event_after_turn": 1})
            else:
                out.append({"id": tid, "kind": kind, "now": {"day": day, "hour": hour, "text": now}, "turns": [q]})
            accepted.append({"id": tid, "accept_pids": ok, "category": cat, "nearest_m": round(best, 1)})
        elif kind == "eta":
            p = rng.choice([p for p in in_area if p["status"] == "open" and not p["brand"]])
            d = haversine_m(m["lat"], m["lon"], p["lat"], p["lon"]) * sp["detour_factor"]
            minutes = d / 1000 / sp["route_speed_walk_kmh"] * 60
            out.append({"id": tid, "kind": kind, "now": {"day": day, "hour": hour, "text": now},
                        "turns": [f"How long does it take to walk from {m['name']} to {p['name']} on {p['street']}?"]})
            accepted.append({"id": tid, "accept_pids": [p["pid"]], "eta_min": round(minutes, 1)})
        else:
            brands = [p for p in in_area if p["brand"] and p["status"] == "open"]
            p = rng.choice(brands)
            out.append({"id": tid, "kind": kind, "now": {"day": day, "hour": hour, "text": now},
                        "turns": [f"What is the phone number of {p['name']} on {p['street']} {p['housenumber']}?"]})
            accepted.append({"id": tid, "accept_pids": [p["pid"]], "phone": p["phone"]})
    return out, accepted


def main() -> None:
    rng = random.Random(W["seed"])
    r1 = build_places(rng)
    r2, changes = apply_changes(rng, r1)
    landmarks = [{"name": n, "lat": round(rng.uniform(W["lat_min"] + 0.01, W["lat_max"] - 0.01), 6),
                  "lon": round(rng.uniform(W["lon_min"] + 0.01, W["lon_max"] - 0.01), 6)} for n in LANDMARKS]
    landmarks += [{"name": f"{n} Ost", "lat": round(rng.uniform(W["lat_min"] + 0.01, W["lat_max"] - 0.01), 6),
                   "lon": round(rng.uniform(W["heldout_lon_split"] + 0.01, W["lon_max"] - 0.01), 6)} for n in LANDMARKS[:8]]
    landmarks += [{"name": f"{n} West", "lat": round(rng.uniform(W["lat_min"] + 0.01, W["lat_max"] - 0.01), 6),
                   "lon": round(rng.uniform(W["lon_min"] + 0.01, W["heldout_lon_split"] - 0.01), 6)} for n in LANDMARKS[:8]]
    for d in (DATA, TRUTH, SOURCES):
        d.mkdir(parents=True, exist_ok=True)
    s1, links1, keys = deliver(rng, r1, None, 1)
    s2, links2, _ = deliver(rng, r2, dict(keys), 2)
    for rel, s, fb_truth in ((1, s1, r1), (2, s2, r2)):
        for src, rows in s.items():
            (SOURCES / f"{src}_r{rel}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        fb = feedback(rng, fb_truth, rel)
        (SOURCES / f"feedback_r{rel}.jsonl").write_text("".join(
            json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False) + "\n" for r in fb))
        (TRUTH / f"feedback_r{rel}.jsonl").write_text("".join(json.dumps({"key": r["key"], "true": r["_true"],
                                                                          "pid": r["_pid"]}) + "\n" for r in fb))
    (DATA / "landmarks.json").write_text(json.dumps(landmarks, indent=1, ensure_ascii=False) + "\n")
    for rel, places in ((1, r1), (2, r2)):
        (TRUTH / f"places_r{rel}.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in places))
    (TRUTH / "links.json").write_text(json.dumps({"r1": links1, "r2": links2}) + "\n")
    (TRUTH / "changes.json").write_text(json.dumps(changes) + "\n")
    # hours changes that arrive as stream events after release 2, used by follow-up tasks
    for area, seed, n in (("dev", W["seed"] + 1, 100), ("heldout", W["seed"] + 2, 60)):
        t, acc = tasks(random.Random(seed), r2, landmarks, area, n, "DEV" if area == "dev" else "HEL")
        (DATA / f"tasks_{area}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in t))
        (TRUTH / f"tasks_{area}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in acc))
    print(f"{len(r1)} places in release 1, {len(r2)} in release 2; "
          f"{sum(map(len, s1.values()))} + {sum(map(len, s2.values()))} source records; {math.nan if not t else len(t)} held-out tasks")


if __name__ == "__main__":
    main()
