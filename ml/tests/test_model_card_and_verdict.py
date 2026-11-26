"""Tests for ml/build_model_card.py (the honest model-card sidecar) and the
boundaries of ml/retrain.py's promotion verdict. Synthetic data, stubs for the
heavy steps: no caches, no torch, no images.

Run: .venv/bin/python -m pytest -q ml/tests/test_model_card_and_verdict.py
"""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_model_card as B  # noqa: E402
import retrain as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- model card -----------------------------------------------------------------

def test_sha256_12_is_the_prefix_the_backend_matches(tmp_path):
    p = tmp_path / "art.joblib"
    p.write_bytes(b"x" * (3 << 20))                             # > one 1 MiB read chunk
    assert B.sha256_12(str(p)) == hashlib.sha256(b"x" * (3 << 20)).hexdigest()[:12]


def test_rounded_keeps_known_keys_only():
    out = B.rounded({"qwk": 0.77449, "mae": 0.40501, "junk": 1.0, "bad_auc": np.float64(0.9341)})
    assert out == {"qwk": 0.774, "mae": 0.405, "bad_auc": 0.934}
    assert all(type(v) is float for v in out.values())          # JSON-serialisable


def test_main_writes_a_card_keyed_to_the_artifact(tmp_path, monkeypatch):
    art = tmp_path / "rqi_model.joblib"
    art.write_bytes(b"champion")
    out = tmp_path / "model_card.json"
    yc = np.array([1, 2, 3, 4] * 5)
    fr = pd.DataFrame({"human_rqi": yc, "pred_rqi": yc, "score": yc.astype(float)})
    seg_metrics = {"qwk": 0.84, "mae": 0.29, "exact": 0.7, "bad_auc": 0.97}

    monkeypatch.setattr(B, "OUT", str(out))
    monkeypatch.setattr(B.E, "ARTIFACT", str(art))
    monkeypatch.setattr(B.joblib, "load", lambda p: {"n_train": 1903})
    monkeypatch.setattr(B.E, "champion_oof", lambda: (fr, None, None, None))
    monkeypatch.setattr(B.E, "build_chains", lambda fr: (None, None, None, None))
    monkeypatch.setattr(B.E, "cut_segments", lambda *a: None)
    monkeypatch.setattr(B.E, "segment_table", lambda *a: None)
    monkeypatch.setattr(B.E, "evaluate", lambda *a: {"runs": [{"m": seg_metrics}] * 3})
    monkeypatch.setattr(B, "leave_area_out",
                        lambda fr: {"qwk": 0.663, "mae": 0.491, "bad_auc": 0.872})
    B.main()

    card = json.loads(out.read_text())
    assert card["artifact_sha256_12"] == hashlib.sha256(b"champion").hexdigest()[:12]
    assert card["frame"]["qwk"] == 1.0 and card["frame"]["mae"] == 0.0
    assert card["segment"] == {"length_m": 200, "aggregator": "median_score", **seg_metrics}
    assert card["new_area"]["qwk"] == 0.663 and card["n_train"] == 1903
    assert "spatial CV" in card["protocol"] and card["measured_on"]


def test_committed_card_matches_the_live_champion_hash():
    """The sidecar is only shown while it matches; a stale one is a silent fallback,
    so flag it here (skipped where the artifact is not checked out)."""
    art = os.path.join(ROOT, "ml", "cache", "rqi_model.joblib")
    if not os.path.exists(art):
        pytest.skip("no champion artifact in this checkout")
    card = json.load(open(os.path.join(ROOT, "ml", "model_card.json")))
    assert card["artifact_sha256_12"] == B.sha256_12(art), \
        "champion changed: re-run ml/build_model_card.py"


# --- promotion verdict boundaries ---------------------------------------------------

@pytest.mark.parametrize("delta,ok", [
    ((0.0, -0.019, 0.02), True),     # neutral and CI low just above -0.02
    ((0.0, -0.020, 0.02), False),    # exactly -0.02 is not enough
    ((0.05, 0.01, 0.09), True),
    ((-0.0001, 0.0, 0.01), False),   # any negative point estimate fails
])
def test_verdict_boundaries(delta, ok):
    got, why = R.verdict(True, {"qwk": delta}, n_new=100, min_new=50)
    assert got is ok and isinstance(why, str) and why


def test_verdict_checks_gate_before_anything_else():
    got, why = R.verdict(False, None, n_new=0, min_new=50)
    assert got is False and "FAIL" in why
