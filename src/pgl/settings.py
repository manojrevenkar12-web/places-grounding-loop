"""Settings from config/pgl.toml, loaded strictly."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Run(Strict):
    seed: int
    repeats: int


class World(Strict):
    seed: int
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    heldout_lon_split: float
    places: int
    shared_building_share: float
    chain_share: float


class Pipeline(Strict):
    cell_m: float
    max_distance_m: float
    match_threshold: float
    closure_corroboration: int
    coord_prefer_community_m: float
    max_id_loss_share: float
    inherit_radius_m: float
    inherit_min_similarity: float
    naive_match_m: float


class Model(Strict):
    latency_ms: float
    latency_spread: float
    ms_per_1k_in: float
    price_in: float
    price_out: float
    small_latency_ms: float
    small_ms_per_1k_in: float
    small_price_in: float
    small_price_out: float
    tokens_per_s: float
    small_tokens_per_s: float
    hallucinate_argument: float
    reuse_stale: float
    ignore_partial: float
    repeat_on_empty: float
    guess_when_ambiguous: float
    small_extra_error: float


class Harness(Strict):
    max_steps: int
    plain_max_steps: int
    start_radius_m: float
    widen_radius_factor: float
    max_radius_m: float
    partial_retries: int
    route_small: list[str]


class Tools(Strict):
    latency_ms: float
    latency_spread: float
    search_failure: float
    route_speed_walk_kmh: float
    route_speed_drive_kmh: float
    detour_factor: float


class Tokens(Strict):
    system: int
    per_tool_schema: int
    per_result: int
    answer: int
    action: int


class Targets(Strict):
    p95_latency_ms: float
    cost_per_request_eur: float


class Eval(Strict):
    eta_tolerance: float
    follow_up_change_share: float
    user_report_wrong: float
    user_report_right: float
    budget_slack: float
    bootstrap: int
    alpha: float
    gate_max_drop: float


class Feedback(Strict):
    production_days: int
    production_harness: str


class Gate(Strict):
    current: str
    candidate: str


class Settings(Strict):
    run: Run
    world: World
    sources: dict[str, dict[str, Any]]
    changes: dict[str, int]
    pipeline: Pipeline
    model: Model
    harness: Harness
    tools: Tools
    tokens: Tokens
    targets: Targets
    eval: Eval
    feedback: Feedback
    gate: Gate


@lru_cache
def load(path: Path | None = None) -> Settings:
    with open(path or ROOT / "config" / "pgl.toml", "rb") as f:
        return Settings.model_validate(tomllib.load(f))
