"""Blocking: candidate pairs are records of compatible categories in the same or a neighbouring grid cell, within a
maximum distance. Two engines produce the same pairs: a local one, and a Spark job for full-size deliveries
(tests/test_pipeline.py checks they agree)."""

from __future__ import annotations

from collections import defaultdict

from pgl.geo import cell, haversine_m


def pairs_local(records: list[dict], cell_m: float, max_m: float) -> set[tuple[str, str]]:
    grid: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in records:
        grid[cell(r["lat"], r["lon"], cell_m)].append(r)
    out = set()
    for (y, x), here in grid.items():
        near = [r for dy in (-1, 0, 1) for dx in (-1, 0, 1) for r in grid.get((y + dy, x + dx), [])]
        for a in here:
            for b in near:
                if (
                    a["key"] < b["key"]
                    and a["category"] == b["category"]
                    and a["source"] != b["source"]
                    and haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= max_m
                ):
                    out.add((a["key"], b["key"]))
    return out


def pairs_spark(records: list[dict], cell_m: float, max_m: float, spark=None) -> set[tuple[str, str]]:
    """The same blocking as a Spark job: explode each record into its 9 neighbourhood cells, join on cell."""
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    own = spark is None
    spark = spark or (
        SparkSession.builder.master("local[2]")
        .appName("pgl-candidates")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    try:
        rows = [
            (r["key"], r["source"], r["category"], r["lat"], r["lon"], *cell(r["lat"], r["lon"], cell_m))
            for r in records
        ]
        df = spark.createDataFrame(rows, ["key", "source", "category", "lat", "lon", "cy", "cx"])
        offsets = spark.createDataFrame([(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)], ["dy", "dx"])
        probe = df.crossJoin(offsets).select(
            F.col("key").alias("bkey"),
            F.col("source").alias("bsource"),
            F.col("category").alias("bcategory"),
            F.col("lat").alias("blat"),
            F.col("lon").alias("blon"),
            (F.col("cy") + F.col("dy")).alias("cy"),
            (F.col("cx") + F.col("dx")).alias("cx"),
        )
        j = df.join(probe, ["cy", "cx"]).where(
            (F.col("key") < F.col("bkey"))
            & (F.col("category") == F.col("bcategory"))
            & (F.col("source") != F.col("bsource"))
        )
        rad = F.lit(3.141592653589793 / 180)
        dlat, dlon = (F.col("blat") - F.col("lat")) * rad, (F.col("blon") - F.col("lon")) * rad
        a = F.sin(dlat / 2) ** 2 + F.cos(F.col("lat") * rad) * F.cos(F.col("blat") * rad) * F.sin(dlon / 2) ** 2
        j = j.withColumn("d", 2 * 6_371_000.0 * F.asin(F.sqrt(a))).where(F.col("d") <= max_m)
        return {(r["key"], r["bkey"]) for r in j.select("key", "bkey").distinct().collect()}
    finally:
        if own:
            spark.stop()
