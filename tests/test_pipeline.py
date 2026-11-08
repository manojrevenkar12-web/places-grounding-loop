import pytest

from pgl.evals.pipeline_eval import score
from pgl.pipeline.candidates import pairs_local
from pgl.pipeline.release import apply_event, build, sources


def test_spark_and_local_blocking_agree(s):
    pytest.importorskip("pyspark")
    from pgl.pipeline.candidates import pairs_spark

    recs, _ = sources(1)
    recs = [r for r in recs if r["lon"] < s.world.lon_min + 0.06]  # a slice keeps the test quick
    assert pairs_spark(recs, s.pipeline.cell_m, s.pipeline.max_distance_m) == pairs_local(
        recs, s.pipeline.cell_m, s.pipeline.max_distance_m
    )


def test_place_ids_survive_a_refresh(s, releases):
    r1, r2 = releases
    assert r2.checks["id_loss_share"] <= s.pipeline.max_id_loss_share and not r2.blocked
    assert score(r2, s, "dev", r1)["id_stability"] > 0.98


def test_the_naive_release_is_blocked(s):
    n1 = build(1, s, naive=True)
    n2 = build(2, s, n1, naive=True)
    assert n2.blocked and n2.checks["id_loss_share"] > s.pipeline.max_id_loss_share


def test_full_pipeline_merges_better_than_naive(s, releases):
    r1, r2 = releases
    n1 = build(1, s, naive=True)
    n2 = build(2, s, n1, naive=True)
    assert score(r2, s, "dev", r1)["duplicates"] * 10 < score(n2, s, "dev", n1)["duplicates"]


def test_no_place_is_closed_on_a_single_kind_of_signal(s, releases):
    _, r2 = releases
    assert score(r2, s, "dev")["wrongly_closed"] == 0


def test_streaming_events_bump_the_version(releases):
    _, r2 = releases
    pid = next(iter(r2.places))
    v = r2.version
    apply_event(r2, {"place_id": pid, "kind": "closed"})
    assert r2.places[pid]["status"] == "closed" and r2.version == v + 1
    apply_event(r2, {"place_id": "nope", "kind": "closed"})
    assert r2.version == v + 1
