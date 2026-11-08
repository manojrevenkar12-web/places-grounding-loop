"""Builds reports/results.json, reports/RESULTS.md, the README results block and the dashboard's data from
reports/dev.json and reports/heldout.json. Every number in the README comes from here."""

from __future__ import annotations

import json
import re

from pgl.evals.pipeline_eval import area_of, place_to_truth, truth_places
from pgl.pipeline.release import build
from pgl.settings import ROOT, load

H = {"plain": "Plain loop", "guarded": "Guarded loop", "plan_fetch": "Plan then fetch"}
MODES = {
    "invented_argument": "Invented argument",
    "stale_context": "Stale context",
    "silent_partial": "Silent partial result",
    "unbounded_loop": "Unbounded loop",
    "guessed_between_matches": "Guessed between twins",
}


def map_points(s) -> dict:
    """Release-2 places in the development area, flagged against the world: duplicate or wrong merge."""
    truth = truth_places(2)
    out = {}
    for name, naive in (("full", False), ("naive", True)):
        r1 = build(1, s, naive=naive)
        r2 = build(2, s, r1, naive=naive)
        mapping = place_to_truth(r2)
        count: dict[str, int] = {}
        for t in mapping.values():
            for x in t:
                count[x] = count.get(x, 0) + 1
        pts = []
        for pid, p in r2.places.items():
            t = mapping[pid]
            if not t or area_of(truth[t[0]], s) != "dev":
                continue
            flag = 2 if len(t) > 1 else 1 if count[t[0]] > 1 else 0
            pts.append([round(p["lon"], 5), round(p["lat"], 5), flag, len(p["sources"])])
        out[name] = pts
    w = s.world
    out["box"] = [w.lon_min, w.lat_min, w.heldout_lon_split, w.lat_max]
    out["lon_max"] = w.lon_max
    return out


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def main() -> None:
    s = load()
    dev = json.loads((ROOT / "reports" / "dev.json").read_text())
    ho = json.loads((ROOT / "reports" / "heldout.json").read_text())
    log = (ROOT / "reports" / "heldout-runs.log").read_text().strip().splitlines()
    res = {
        "dev": dev,
        "heldout": ho,
        "heldout_runs": log,
        "targets": s.targets.model_dump(),
        "config": {
            "repeats": s.run.repeats,
            "tasks_dev": dev["harnesses"]["plain"]["runs"] // s.run.repeats,
            "tasks_heldout": ho["harnesses"]["plain"]["runs"] // s.run.repeats,
            "model": s.model.model_dump(),
            "max_steps": s.harness.max_steps,
            "gate_max_drop": s.eval.gate_max_drop,
        },
    }
    (ROOT / "reports" / "results.json").write_text(json.dumps(res, indent=1))
    web = ROOT / "web" / "public" / "data"
    web.mkdir(parents=True, exist_ok=True)
    (web / "results.json").write_text(json.dumps(res))
    (web / "map.json").write_text(json.dumps(map_points(s)))

    pf, pl, gd = (ho["harnesses"][k] for k in ("plan_fetch", "plain", "guarded"))
    fb = dev["feedback"]
    p_full, p_naive = dev["pipeline"]["full"]["r2"], dev["pipeline"]["naive"]["r2"]
    lines = [
        f"Held-out run (east area, {res['config']['tasks_heldout']} tasks × {s.run.repeats} repeats, run once at "
        f"commit `{ho['commit']}`):",
        "",
        "| | Plain loop | Guarded loop | Plan then fetch | Target |",
        "|---|---|---|---|---|",
        f"| Task success | {pct(pl['success'])} ({pct(pl['success_lo'], 0)}–{pct(pl['success_hi'], 0)}) | "
        f"{pct(gd['success'])} ({pct(gd['success_lo'], 0)}–{pct(gd['success_hi'], 0)}) | "
        f"**{pct(pf['success'])}** ({pct(pf['success_lo'], 0)}–{pct(pf['success_hi'], 0)}) | |",
        f"| Confidently wrong answers | {pct(pl['wrong'])} | {pct(gd['wrong'])} | {pct(pf['wrong'])} | |",
        f"| Latency p50 / p95 per turn | {pl['p50_ms'] / 1000:.1f} / {pl['p95_ms'] / 1000:.1f} s | "
        f"{gd['p50_ms'] / 1000:.1f} / {gd['p95_ms'] / 1000:.1f} s | {pf['p50_ms'] / 1000:.1f} / "
        f"{pf['p95_ms'] / 1000:.1f} s | p95 ≤ {s.targets.p95_latency_ms / 1000:.1f} s |",
        f"| Cost per turn | €{pl['cost_eur']:.4f} | €{gd['cost_eur']:.4f} | €{pf['cost_eur']:.4f} | "
        f"≤ €{s.targets.cost_per_request_eur} |",
        f"| Model calls per turn | {pl['model_calls']} | {gd['model_calls']} | {pf['model_calls']} | |",
        "",
        "Failure modes that reached the user (share of held-out runs):",
        "",
        "| | " + " | ".join(H.values()) + " |",
        "|---|---|---|---|",
    ]
    for m, label in MODES.items():
        lines.append(f"| {label} | " + " | ".join(pct(ho["harnesses"][k]["modes"][m]) for k in H) + " |")
    lines += [
        "",
        f"Pipeline, release 2 of the development area: {p_full['duplicates']} duplicate places against "
        f"{p_naive['duplicates']} for a name-and-distance merge, {p_full['wrong_merges']} wrong merges, place-id "
        f"stability {pct(p_full['id_stability'], 2)} against {pct(p_naive['id_stability'])}; the naive release is "
        f"blocked by the id-loss check ({pct(dev['pipeline']['naive']['checks']['id_loss_share'])} of ids lost). "
        f"Held-out area: {ho['pipeline']['full']['duplicates']} duplicates, {ho['pipeline']['full']['wrong_merges']} "
        f"wrong merges, stability {pct(ho['pipeline']['full']['id_stability'], 2)}.",
        "",
        f"Feedback loop: {fb['requests']} production requests on the plain loop, {fb['failed']} failed, "
        f"{fb['reported']} reported by users ({fb['false_reports']} of them about right answers), "
        f"{fb['unreported_failures']} failures nobody reported, {fb['cases']} regression cases kept. Plan then fetch "
        f"passes {fb['pass']['plan_fetch']} of {fb['cases']}; the rest are data gaps, not agent mistakes.",
        "",
        "Gate on six changes (development tasks plus the regression cases):",
        "",
        "| Change | Decision | Why |",
        "|---|---|---|",
    ]
    for change, d in dev["gate"].items():
        why = (
            "; ".join(d["reasons"])
            if d["reasons"]
            else (
                f"success {d['diff']:+.3f} (lower bound {d['lo']:+.3f}), p95 {d['budget']['p95_ms'] / 1000:.1f} s, "
                f"€{d['budget']['cost_eur']:.4f}"
            )
        )
        lines.append(f"| {change} | {'blocked' if d['blocked'] else 'passes'} | {why} |")
    block = "\n".join(lines)
    (ROOT / "reports" / "RESULTS.md").write_text("# Results\n\nGenerated by `make report`.\n\n" + block + "\n")
    readme = ROOT / "README.md"
    if readme.exists():
        t = readme.read_text()
        t = re.sub(
            r"<!-- results:start -->.*<!-- results:end -->",
            "<!-- results:start -->\n" + block + "\n<!-- results:end -->",
            t,
            flags=re.S,
        )
        readme.write_text(t)
    print(block)


if __name__ == "__main__":
    main()
