"""Trains the pair matcher on labelled pairs from the development area only (west of the split), release 1.
The labels come from the world's record-to-place links, the stand-in for a team's hand-labelled pairs."""

from __future__ import annotations

import json

import numpy as np
from sklearn.linear_model import LogisticRegression

from pgl.pipeline.candidates import pairs_local
from pgl.pipeline.features import NAMES, features
from pgl.pipeline.release import MODEL, sources
from pgl.settings import ROOT, load


def train() -> dict:
    s = load()
    links = json.loads((ROOT / "data" / "truth" / "links.json").read_text())["r1"]
    recs, _ = sources(1)
    recs = [r for r in recs if r["lon"] < s.world.heldout_lon_split]
    by = {r["key"]: r for r in recs}
    pairs = sorted(pairs_local(recs, s.pipeline.cell_m, s.pipeline.max_distance_m))
    x = np.asarray([features(by[a], by[b]) for a, b in pairs])
    y = np.asarray([links[a] == links[b] for a, b in pairs])
    clf = LogisticRegression(max_iter=2000, C=1.0).fit(x, y)
    p = clf.predict_proba(x)[:, 1] >= s.pipeline.match_threshold
    out = {
        "features": NAMES,
        "coef": clf.coef_[0].round(5).tolist(),
        "intercept": round(float(clf.intercept_[0]), 5),
        "training_pairs": len(pairs),
        "positives": int(y.sum()),
        "train_precision": round(float((p & y).sum() / max(1, p.sum())), 4),
        "train_recall": round(float((p & y).sum() / max(1, y.sum())), 4),
    }
    MODEL.parent.mkdir(exist_ok=True)
    MODEL.write_text(json.dumps(out, indent=1) + "\n")
    return out
