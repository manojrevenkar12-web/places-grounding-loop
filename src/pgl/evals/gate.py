"""The release gate for a harness change. A candidate is blocked when, against the current harness on the
development tasks, the lower bound of the paired difference in task success is below -gate_max_drop; when it fails
a regression case the current harness passes; or when it is over the latency or cost budget and worse than the
current harness there."""

from __future__ import annotations

from pgl.evals.stats import paired, pct
from pgl.settings import Settings


def budget(runs: list[dict]) -> dict:
    turns = [x for r in runs for x in r["turn_ms"]]
    return {
        "p50_ms": round(pct(turns, 50)),
        "p95_ms": round(pct(turns, 95)),
        "cost_eur": round(sum(r["cost_eur"] for r in runs) / max(1, len(turns)), 5),
    }


def decide(base: list[dict], cand: list[dict], base_reg: dict, cand_reg: dict, s: Settings) -> dict:
    e = s.eval
    diff, lo, hi = paired(base, cand, e.bootstrap, e.alpha, s.run.seed)
    b = budget(cand)
    broken = sorted(k for k, ok in base_reg.items() if ok and not cand_reg.get(k, False))
    reasons = []
    if lo < -e.gate_max_drop:
        reasons.append(
            f"task success may drop: paired difference {diff:+.3f}, lower bound {lo:+.3f} below -{e.gate_max_drop}"
        )
    if broken:
        reasons.append(f"fails {len(broken)} regression case(s) the current harness passes: {', '.join(broken[:5])}")
    a = budget(base)
    # over budget is allowed only while a change makes it better: a change may not make it worse
    if b["p95_ms"] > s.targets.p95_latency_ms and b["p95_ms"] > a["p95_ms"] * (1 + e.budget_slack):
        reasons.append(
            f"p95 latency {b['p95_ms']} ms, over the {s.targets.p95_latency_ms:.0f} ms budget and "
            f"above the current {a['p95_ms']} ms"
        )
    if b["cost_eur"] > s.targets.cost_per_request_eur and b["cost_eur"] > a["cost_eur"] * (1 + e.budget_slack):
        reasons.append(
            f"€{b['cost_eur']:.4f} per request, over the €{s.targets.cost_per_request_eur} budget and "
            f"above the current €{a['cost_eur']:.4f}"
        )
    return {
        "diff": round(diff, 4),
        "lo": round(lo, 4),
        "hi": round(hi, 4),
        "budget": b,
        "baseline_budget": a,
        "regressions_broken": broken,
        "blocked": bool(reasons),
        "reasons": reasons,
    }
