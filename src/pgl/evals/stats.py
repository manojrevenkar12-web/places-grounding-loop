"""Statistics for comparing harnesses: per-task means over repeats, a task-clustered bootstrap, percentiles."""

from __future__ import annotations

import numpy as np


def by_task(runs: list[dict], key=lambda r: r["outcome"] == "right") -> dict[str, float]:
    acc: dict[str, list[float]] = {}
    for r in runs:
        acc.setdefault(r["id"], []).append(float(key(r)))
    return {k: sum(v) / len(v) for k, v in acc.items()}


def interval(values: list[float], n: int, alpha: float, seed: int) -> tuple[float, float, float]:
    """Mean and bootstrap interval, resampling tasks (repeats of one task stay together)."""
    x = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(n, len(x)))].mean(axis=1)
    return float(x.mean()), float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def paired(a: list[dict], b: list[dict], n: int, alpha: float, seed: int) -> tuple[float, float, float]:
    """Difference in success, b minus a, paired by task."""
    ta, tb = by_task(a), by_task(b)
    ids = sorted(set(ta) & set(tb))
    return interval([tb[i] - ta[i] for i in ids], n, alpha, seed)


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else 0.0
