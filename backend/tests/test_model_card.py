"""Model-card sidecar: honest spatial metrics overlay, keyed by artifact hash."""
import hashlib
import json
from pathlib import Path

from app.services.model_card import apply_card, artifact_hash, load_card

ROOT = Path(__file__).resolve().parents[2]
INFO = {"version": 2, "qwk": 0.895, "mae": 0.19, "exact_acc": 0.81,
        "bad_road_acc": 0.92, "bad_road_auc": 0.97, "n_train": 1903}


def _write(tmp_path, card, artifact=b"model-bytes"):
    art = tmp_path / "rqi_model.joblib"
    art.write_bytes(artifact)
    p = tmp_path / "model_card.json"
    p.write_text(json.dumps(card) if not isinstance(card, str) else card)
    return str(p), str(art)


def _card(sha):
    return {"artifact_sha256_12": sha, "measured_on": "2026-11-26",
            "protocol": "spatial CV", "n_train": 1903,
            "frame": {"qwk": 0.774, "mae": 0.405, "exact": 0.61,
                      "bad_acc": 0.86, "bad_auc": 0.934},
            "segment": {"length_m": 200, "qwk": 0.843},
            "new_area": {"qwk": 0.663}}


def test_artifact_hash_is_sha256_prefix(tmp_path):
    _, art = _write(tmp_path, {})
    assert artifact_hash(art) == hashlib.sha256(b"model-bytes").hexdigest()[:12]
    assert artifact_hash(str(tmp_path / "missing")) is None


def test_matching_card_overrides_the_leaky_artifact_metrics(tmp_path):
    sha = hashlib.sha256(b"model-bytes").hexdigest()[:12]
    card = load_card(*_write(tmp_path, _card(sha)))
    out = apply_card(INFO, card)
    assert out["metrics_source"] == "spatial_cv"
    assert (out["qwk"], out["mae"], out["bad_road_auc"]) == (0.774, 0.405, 0.934)
    assert (out["exact_acc"], out["bad_road_acc"]) == (0.61, 0.86)
    assert (out["segment_qwk"], out["segment_length_m"], out["new_area_qwk"]) == (0.843, 200.0, 0.663)
    assert out["metrics_measured_on"] == "2026-11-26" and out["version"] == 2


def test_stale_missing_or_broken_card_falls_back_to_the_artifact(tmp_path):
    assert load_card(*_write(tmp_path, _card("000000000000"))) is None   # other artifact
    assert load_card(*_write(tmp_path, "{not json")) is None
    assert load_card(str(tmp_path / "none.json"), str(tmp_path / "x")) is None
    out = apply_card(INFO, None)
    assert out["metrics_source"] == "artifact" and out["qwk"] == 0.895


def test_committed_card_is_well_formed():
    card = json.loads((ROOT / "ml" / "model_card.json").read_text())
    assert len(card["artifact_sha256_12"]) == 12
    for section in ("frame", "segment", "new_area"):
        assert 0 < card[section]["qwk"] <= 1
    assert card["frame"]["qwk"] < 0.8    # the honest number, not the leaky 0.895
