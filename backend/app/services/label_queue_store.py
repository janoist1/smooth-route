"""DB / filesystem side of the label queue (the pure logic is label_queue.py).

- Loads candidate frames (image file on disk, no manual_rqi) and labelled
  coordinates from Postgres.
- Model score per frame: ``analysis_metadata.dino_score`` / ``dino_p_bad``
  (written by the v2 analysis pass); frames without one fall back to the
  ``data/cache/frame_scores.csv`` cache (backend/scripts/score_frames.py).
- Writes quick labels into ``training_data`` exactly like the review page's
  ``saveTrainingData`` (one row per image_filename, ``manual_rqi``), so
  ml/export_labels.sh picks them up unchanged. Existing annotations, tags and
  comments on a row are kept; the quick-label context goes into
  ``meta_data.quick_label`` so undo can restore the previous state.

Scale: label values are the canonical levels of shared/rqi_scale.json
(``app.core.rqi_scale.SCALE``, 1..5 today, 5 = Nagyon rossz). Model scores,
cut-points and the OOF table are in the fixed *severity* orientation (1 = best)
and are converted with ``SCALE.from_severity`` before they leave this module.

Torch-free: the cut-points are read from the joblib artifact (sklearn only).
"""
from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.paths import data_path
from app.core.rqi_scale import SCALE
from app.core.timeutil import utcnow
from app.services import label_queue as lq

SCORE_CACHE_FIELDS = ["image_filename", "score", "p_bad", "model_version"]
QUICK_LABEL_AGENT = "quick-label"
VALID_RQI = tuple(SCALE.values)  # every level can be labelled, incl. ones the model never predicts

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = _PROJECT_ROOT / "ml" / "cache" / "rqi_model.joblib"


# --- model metadata (torch-free) ----------------------------------------------

def model_version() -> str:
    """Identifies the artifact a cached score came from (its mtime)."""
    try:
        return str(int(MODEL_PATH.stat().st_mtime))
    except OSError:
        return "none"


@lru_cache(maxsize=4)
def _cut_points_for(version: str) -> tuple[float, ...]:
    try:
        import joblib

        thresholds = joblib.load(MODEL_PATH).get("thresholds")
        if thresholds and len(thresholds) == 3:
            return tuple(float(t) for t in thresholds)
    except Exception as exc:  # pragma: no cover - artifact missing/unreadable
        print(f"label_queue: cut-points unavailable ({exc}); using defaults")
    return lq.DEFAULT_CUT_POINTS


def cut_points() -> tuple[float, ...]:
    return _cut_points_for(model_version())


def model_rqi(score: Optional[float], cuts: Iterable[float]) -> Optional[int]:
    """Canonical RQI level of a continuous severity score (same cut rule as
    dino_service.rqi_from_score, then converted to the scale's direction)."""
    if score is None:
        return None
    return int(SCALE.from_severity(1 + sum(1 for c in cuts if score >= c)))


def canonical_score(score: Optional[float]) -> Optional[float]:
    """Continuous severity score (1 = best) on the canonical scale."""
    return None if score is None else float(SCALE.from_severity(score))


def canonical_boundary(label: Optional[str]) -> Optional[str]:
    """Severity boundary "2|3" on the canonical scale (identity today)."""
    if not label:
        return label
    a, b = (int(x) for x in label.split("|"))
    return f"{SCALE.from_severity(a)}|{SCALE.from_severity(b)}"


# --- score cache + image listing ---------------------------------------------

def score_cache_path() -> Path:
    return data_path("cache", "frame_scores.csv")


_score_cache: dict = {"mtime": None, "data": {}}


def load_score_cache() -> dict[str, tuple[Optional[float], Optional[float]]]:
    path = score_cache_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _score_cache["mtime"] != mtime:
        data: dict[str, tuple[Optional[float], Optional[float]]] = {}
        with path.open() as fh:
            for row in csv.DictReader(fh):
                try:
                    score = float(row["score"]) if row.get("score") else None
                    p_bad = float(row["p_bad"]) if row.get("p_bad") else None
                except ValueError:
                    continue
                data[row["image_filename"]] = (score, p_bad)
        _score_cache.update(mtime=mtime, data=data)
    return _score_cache["data"]


_files_cache: dict = {"at": 0.0, "files": frozenset()}
FILES_TTL_S = 30.0


def image_files() -> frozenset[str]:
    """Names in data/images (listed at most every FILES_TTL_S seconds)."""
    now = time.monotonic()
    if now - _files_cache["at"] > FILES_TTL_S or not _files_cache["files"]:
        try:
            files = frozenset(os.listdir(data_path("images")))
        except OSError:
            files = frozenset()
        _files_cache.update(at=now, files=files)
    return _files_cache["files"]


# --- loading ------------------------------------------------------------------

@dataclass(frozen=True)
class FrameInfo:
    """Display data for a queued frame (kept out of the pure Frame)."""
    filename: str
    heading: Optional[float]
    pitch: Optional[float]
    pano_id: Optional[str]
    capture_date: Optional[object]


def _filename(image_url: Optional[str]) -> Optional[str]:
    if not image_url:
        return None
    return os.path.basename(image_url.split("/data/images/")[-1])


def _float(value) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


_rows_cache: dict = {"at": -1e9, "rows": []}
ROWS_TTL_S = 600.0


def _frame_rows(db: Session) -> list:
    """All street_view_images rows the queue needs, cached in-process for
    ROWS_TTL_S: the table changes only when a route is collected, and the
    17k-row read is the slow part of a queue request."""
    now = time.monotonic()
    if now - _rows_cache["at"] > ROWS_TTL_S:
        rows = db.execute(text(
            "SELECT id, image_url, latitude, longitude, heading, pitch, pano_id, "
            "capture_date, analysis_metadata->>'dino_score', "
            "analysis_metadata->>'dino_p_bad' "
            "FROM street_view_images "
            "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        )).all()
        _rows_cache.update(at=now, rows=rows)
    return _rows_cache["rows"]


def load_inputs(db: Session):
    """(candidates, labelled coords, FrameInfo by id). The labelled set is
    re-read on every call so a fresh label immediately clears its area."""
    labelled_names = {
        name for (name,) in db.execute(text(
            "SELECT image_filename FROM training_data WHERE manual_rqi IS NOT NULL"))
    }
    rows = _frame_rows(db)
    files = image_files()
    cache = load_score_cache()

    candidates: list[lq.Frame] = []
    labelled: list[tuple[float, float]] = []
    info: dict[int, FrameInfo] = {}
    for (fid, url, lat, lon, heading, pitch, pano, cdate, score, p_bad) in rows:
        name = _filename(url)
        if not name:
            continue
        if name in labelled_names:
            labelled.append((lat, lon))
            continue
        if name not in files:
            continue
        score, p_bad = _float(score), _float(p_bad)
        if score is None and name in cache:
            score, p_bad = cache[name]
        candidates.append(lq.Frame(id=fid, lat=lat, lon=lon, pano_id=pano,
                                   score=score, p_bad=p_bad))
        info[fid] = FrameInfo(filename=name, heading=heading, pitch=pitch,
                              pano_id=pano, capture_date=cdate)
    return candidates, labelled, info


def build(db: Session, strategy: str, limit: int, exclude_ids: Iterable[int] = ()):
    candidates, labelled, info = load_inputs(db)
    cuts = cut_points()
    result = lq.build_queue(candidates, labelled, strategy, limit,
                            cut_points=cuts, exclude_ids=exclude_ids)
    return result, info, cuts


# --- stats ----------------------------------------------------------------------

def _local_midnight_utc() -> datetime:
    """Start of 'today' on the server's clock (the owner's machine), as naive
    UTC like the DB timestamps."""
    local_now = datetime.now().astimezone()
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


def label_counts(db: Session) -> tuple[int, int]:
    """(all manual labels, quick labels written today)."""
    total = db.execute(text(
        "SELECT count(*) FROM training_data WHERE manual_rqi IS NOT NULL")).scalar() or 0
    today = db.execute(text(
        "SELECT count(*) FROM training_data WHERE manual_rqi IS NOT NULL "
        "AND updated_at >= :since AND (meta_data::jsonb) ? 'quick_label'"),
        {"since": _local_midnight_utc()}).scalar() or 0
    return int(total), int(today)


# --- writes -----------------------------------------------------------------------

class QuickLabelError(ValueError):
    pass


def _point_filename(db: Session, point_id: int) -> str:
    from app.models.models import StreetViewImage

    point = db.query(StreetViewImage).filter(StreetViewImage.id == point_id).first()
    if point is None:
        raise QuickLabelError(f"Point {point_id} not found")
    name = _filename(point.image_url)
    if not name or not data_path("images", name).is_file():
        raise QuickLabelError(f"Point {point_id} has no local image")
    return name


def save_quick_label(db: Session, point_id: int, rqi: int, *,
                     labeller: Optional[str] = None,
                     context: Optional[dict] = None) -> str:
    """Upsert manual_rqi for one frame; returns the image filename.

    Same row shape as the review page (training_data keyed by image_filename).
    """
    from app.models.models import TrainingData

    if rqi not in VALID_RQI:
        raise QuickLabelError(f"RQI must be one of {VALID_RQI}, got {rqi}")
    name = _point_filename(db, point_id)
    now = utcnow()
    stamp = now.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    ql = {"timestamp": stamp, "rqi": rqi, **({"labeller": labeller} if labeller else {}),
          **(context or {})}

    row = db.query(TrainingData).filter(TrainingData.image_filename == name).first()
    if row is None:
        db.add(TrainingData(
            image_filename=name, manual_rqi=float(rqi), annotations=[], tags=[],
            comment="",
            meta_data={"agent": QUICK_LABEL_AGENT, "timestamp": stamp,
                       "quick_label": {**ql, "created_row": True,
                                       "previous_rqi": None}},
        ))
    else:
        meta = dict(row.meta_data or {})
        previous = meta.get("quick_label")
        # Re-rating a frame quick-labelled earlier keeps the original "before"
        # state, so undo always returns to what the review page had.
        if previous:
            created, prev_rqi = previous.get("created_row", False), previous.get("previous_rqi")
        else:
            created, prev_rqi = False, row.manual_rqi
        meta["quick_label"] = {**ql, "created_row": created, "previous_rqi": prev_rqi}
        row.manual_rqi = float(rqi)
        row.meta_data = meta  # new dict: JSON column change detection
        row.updated_at = now
    db.commit()
    return name


def undo_quick_label(db: Session, point_id: int) -> bool:
    """Revert a quick label. Rows the quick-rate screen created (and nobody
    annotated since) are deleted; otherwise the previous manual_rqi returns.
    Labels not written by the quick-rate screen are never touched."""
    from app.models.models import TrainingData

    name = _point_filename(db, point_id)
    row = db.query(TrainingData).filter(TrainingData.image_filename == name).first()
    if row is None:
        return False
    meta = dict(row.meta_data or {})
    ql = meta.get("quick_label")
    if not ql:
        return False
    if ql.get("created_row") and not row.annotations and not row.tags and not row.comment:
        db.delete(row)
    else:
        meta.pop("quick_label", None)
        row.manual_rqi = ql.get("previous_rqi")
        row.meta_data = meta
        row.updated_at = utcnow()
    db.commit()
    return True


# --- rubric examples ------------------------------------------------------------

OOF_TABLE = _PROJECT_ROOT / "ml" / "cache" / "oof_table.csv"
EXAMPLE_MIN_ROAD_PROB = 0.9
EXAMPLE_SPACING_M = 300.0


def _oof_errors() -> dict[str, float]:
    """|out-of-fold prediction - label| per labelled image (ml/cache/oof_table.csv,
    written by the ml/ pipeline); only confident road images."""
    out: dict[str, float] = {}
    try:
        with OOF_TABLE.open() as fh:
            for row in csv.DictReader(fh):
                try:
                    if float(row.get("is_road_prob") or 1.0) < EXAMPLE_MIN_ROAD_PROB:
                        continue
                    out[row["image_filename"]] = abs(float(row["err"]))
                except (KeyError, ValueError):
                    continue
    except OSError:
        pass
    return out


def label_examples(db: Session, per_class: int = 1) -> list[tuple[int, int, str]]:
    """(level, point id, filename) of clear labelled exemplars for every level.

    Integer labels only. "Clear" = the honest out-of-fold model prediction
    agrees best with the human label (ml/cache/oof_table.csv); levels the model
    was not trained on (Nagyon rossz) fall back to the live model score, so the
    most severe-looking labelled frame wins instead of a mislabelled non-road
    image. Several examples of one level are EXAMPLE_SPACING_M apart.
    """
    per_class = max(1, min(int(per_class), 6))
    rows = db.execute(text(
        "SELECT td.manual_rqi, svi.id, td.image_filename, svi.latitude, svi.longitude, "
        "svi.analysis_metadata->>'dino_score' "
        "FROM training_data td "
        "JOIN street_view_images svi ON svi.image_url = 'images/' || td.image_filename "
        "WHERE td.manual_rqi = ANY(:levels) "
        "ORDER BY td.created_at, td.id"
    ), {"levels": [float(v) for v in VALID_RQI]}).all()
    files = image_files()
    errors = _oof_errors()
    cache = load_score_cache()
    by_class: dict[int, list[tuple[float, int, int, str, float, float]]] = {
        r: [] for r in VALID_RQI}
    for order, (rqi, pid, name, lat, lon, score) in enumerate(rows):
        if name not in files:
            continue
        # Honest OOF agreement first (|severity difference| is direction-free);
        # the live model score (in-sample for training images, so optimistic)
        # only ranks frames without an OOF row, e.g. every Nagyon rossz label.
        gap = errors.get(name)
        if gap is None:
            s = _float(score)
            if s is None and name in cache:
                s = cache[name][0]
            gap = 10.0 + (abs(canonical_score(s) - rqi) if s is not None else 9.0)
        by_class[int(rqi)].append((gap, order, pid, name, lat, lon))
    out = []
    for rqi in VALID_RQI:
        taken = lq.PointIndex(EXAMPLE_SPACING_M)
        n = 0
        for _, _, pid, name, lat, lon in sorted(by_class[rqi]):
            if n >= per_class:
                break
            if lat is not None and lon is not None:
                if taken.near(lat, lon, EXAMPLE_SPACING_M):
                    continue
                taken.add(lat, lon)
            out.append((rqi, pid, name))
            n += 1
    return out
