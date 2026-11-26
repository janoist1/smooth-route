"""Honest model-card metrics for the live RQI artifact (torch-free).

The artifact's own ``cv_metrics`` may predate the spatial evaluation protocol
(the live v2 champion still says QWK 0.895 from a leaky random CV). Re-saving
the champion would also change its cut-points and calibrator, so the honest
numbers live in a small committed sidecar, ``ml/model_card.json`` (written by
ml/build_model_card.py), keyed by the first 12 hex digits of the artifact's
sha256. The sidecar is used only while that hash matches the live file; any
other artifact keeps its own ``cv_metrics``.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

_hash_cache: dict[str, tuple[float, int, str]] = {}


def artifact_hash(path: str) -> Optional[str]:
    """sha256[:12] of a file (cached by mtime + size); None if unreadable."""
    try:
        st = os.stat(path)
        cached = _hash_cache.get(path)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return cached[2]
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()[:12]
        _hash_cache[path] = (st.st_mtime, st.st_size, digest)
        return digest
    except OSError:
        return None


def load_card(card_path: str, artifact_path: str) -> Optional[dict]:
    """The sidecar dict if it exists, parses and matches the artifact's hash."""
    try:
        with open(card_path, encoding="utf-8") as f:
            card = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(card, dict) or not card.get("artifact_sha256_12"):
        return None
    if card["artifact_sha256_12"] != artifact_hash(artifact_path):
        return None
    return card


def _num(d: Any, key: str) -> Optional[float]:
    v = d.get(key) if isinstance(d, dict) else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def apply_card(info: dict, card: Optional[dict]) -> dict:
    """Overlay the sidecar's spatial metrics on the artifact-derived ``info``.

    Without a (matching) card the info is returned unchanged except for
    ``metrics_source = "artifact"``, so the UI can say the numbers are the
    artifact's own.
    """
    out = dict(info)
    if not card:
        out["metrics_source"] = "artifact"
        return out
    frame, seg, new = card.get("frame", {}), card.get("segment", {}), card.get("new_area", {})
    out.update({
        "metrics_source": "spatial_cv",
        "metrics_protocol": card.get("protocol"),
        "metrics_measured_on": card.get("measured_on"),
        "qwk": _num(frame, "qwk"),
        "mae": _num(frame, "mae"),
        "exact_acc": _num(frame, "exact"),
        "bad_road_acc": _num(frame, "bad_acc"),
        "bad_road_auc": _num(frame, "bad_auc"),
        "segment_qwk": _num(seg, "qwk"),
        "segment_length_m": _num(seg, "length_m"),
        "new_area_qwk": _num(new, "qwk"),
    })
    if isinstance(card.get("n_train"), int):
        out["n_train"] = card["n_train"]
    return out
