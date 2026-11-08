from pgl.evals.gate import decide


def _runs(success: dict[str, float], ms=1000.0, cost=0.001):
    out = []
    for tid, p in success.items():
        for k in range(10):
            out.append({"id": tid, "outcome": "right" if k < p * 10 else "wrong", "turn_ms": [ms], "cost_eur": cost})
    return out


def test_same_results_pass(s):
    a = _runs({f"T{i}": 0.8 for i in range(40)})
    assert not decide(a, a, {}, {}, s)["blocked"]


def test_a_drop_is_blocked(s):
    a = _runs({f"T{i}": 0.9 for i in range(40)})
    b = _runs({f"T{i}": 0.9 if i % 3 else 0.5 for i in range(40)})
    d = decide(a, b, {}, {}, s)
    assert d["blocked"] and "success" in d["reasons"][0]


def test_a_broken_regression_case_is_blocked(s):
    a = _runs({f"T{i}": 0.8 for i in range(40)})
    d = decide(a, a, {"REG-001": True, "REG-002": False}, {"REG-001": False, "REG-002": True}, s)
    assert d["blocked"] and d["regressions_broken"] == ["REG-001"]


def test_over_budget_is_allowed_only_while_getting_better(s):
    a = _runs({f"T{i}": 0.8 for i in range(40)}, ms=9000)
    better = _runs({f"T{i}": 0.8 for i in range(40)}, ms=6000)
    worse = _runs({f"T{i}": 0.8 for i in range(40)}, ms=9900)
    assert not decide(a, better, {}, {}, s)["blocked"]
    assert decide(a, worse, {}, {}, s)["blocked"]
    pricey = _runs({f"T{i}": 0.8 for i in range(40)}, cost=0.02)
    assert decide(_runs({f"T{i}": 0.8 for i in range(40)}), pricey, {}, {}, s)["blocked"]
