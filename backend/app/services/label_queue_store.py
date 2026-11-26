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
        _rows_cache.update(at=now, rows=[_severity_row(r) for r in rows])
    return _rows_cache["rows"]


def _severity_row(row) -> tuple:
    """analysis_metadata.dino_score is stored on the CANONICAL scale (since the
    0006 direction flip); the queue logic, cut-points and the frame_scores.csv
    cache are in the model's severity orientation (1 = best). Convert here,
    once, so nothing downstream mixes the two."""
    (fid, url, lat, lon, heading, pitch, pano, cdate, score, p_bad) = row
    score = _float(score)
    return (fid, url, lat, lon, heading, pitch, pano, cdate,
            None if score is None else float(SCALE.to_severity(score)), p_bad)


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


AUDIT_CSV = ("vlm", "label_audit.csv")  # under data/: suspicious human labels


def _audit_order() -> list[str]:
    """Filenames from data/vlm/label_audit.csv, highest priority first."""
    try:
        with data_path(*AUDIT_CSV).open() as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return []
    rows.sort(key=lambda r: -(_float(r.get("priority")) or 0.0))
    return [r["image_filename"] for r in rows if r.get("image_filename")]


def build_recheck(db: Session, limit: int, exclude_ids: Iterable[int] = ()):
    """Re-check queue: labelled frames not re-checked yet (the old label is
    never returned), suspicious ones first, then a level-stratified sample."""
    labels = {
        name: (_float(rqi), bool(done)) for name, rqi, done in db.execute(text(
            "SELECT image_filename, manual_rqi, (meta_data::jsonb) ? 'relabel_history' "
            "FROM training_data WHERE manual_rqi IS NOT NULL"))
    }
    files = image_files()
    cache = load_score_cache()
    frames: list[lq.Frame] = []
    info: dict[int, FrameInfo] = {}
    level_of: dict[int, int] = {}
    id_of: dict[str, int] = {}
    for (fid, url, lat, lon, heading, pitch, pano, cdate, score, p_bad) in _frame_rows(db):
        name = _filename(url)
        if name not in labels or name not in files:
            continue
        old, done = labels[name]
        if done:
            continue
        score, p_bad = _float(score), _float(p_bad)
        if score is None and name in cache:
            score, p_bad = cache[name]
        frames.append(lq.Frame(id=fid, lat=lat, lon=lon, pano_id=pano, score=score, p_bad=p_bad))
        info[fid] = FrameInfo(filename=name, heading=heading, pitch=pitch,
                              pano_id=pano, capture_date=cdate)
        level_of[fid] = int(SCALE.nearest(old))
        id_of[name] = fid
    suspicious = [id_of[n] for n in _audit_order() if n in id_of]
    best_to_worst = sorted(SCALE.values, key=SCALE.worst_first_key, reverse=True)
    items = lq.pick_recheck(frames, level_of, suspicious, max(0, min(int(limit), lq.MAX_LIMIT)),
                            best_to_worst, exclude_ids)
    result = lq.QueueResult(items=items, eligible=len(frames),
                            scored=sum(1 for f in frames if f.score is not None))
    return result, info, cut_points()


def build(db: Session, strategy: str, limit: int, exclude_ids: Iterable[int] = ()):
    if strategy == lq.Strategy.RECHECK.value:
        return build_recheck(db, limit, exclude_ids)
    candidates, labelled, info = load_inputs(db)
    cuts = cut_points()
    result = lq.build_queue(candidates, labelled, strategy, limit,
                            cut_points=cuts, exclude_ids=exclude_ids)
    return result, info, cuts


def build_pairs(db: Session, limit: int, exclude_ids: Iterable[int] = ()):
    """Pairs over every frame with an image and a model score (labelled or
    not), skipping pairs judged before and frames marked unusable."""
    from app.models.models import PairJudgment

    judged = [(a, b) for a, b in db.query(PairJudgment.frame_a_id, PairJudgment.frame_b_id)]
    files = image_files()
    cache = load_score_cache()
    unusable = {i for (i,) in db.execute(text(
        "SELECT id FROM street_view_images "
        "WHERE (analysis_metadata::jsonb)->'frame_quality'->>'usable' = 'false'"))}
    frames, info = [], {}
    for (fid, url, lat, lon, heading, pitch, pano, cdate, score, p_bad) in _frame_rows(db):
        name = _filename(url)
        if not name or name not in files or fid in unusable:
            continue
        score, p_bad = _float(score), _float(p_bad)
        if score is None and name in cache:
            score, p_bad = cache[name]
        if score is None:
            continue
        frames.append(lq.Frame(id=fid, lat=lat, lon=lon, pano_id=pano, score=score, p_bad=p_bad))
        info[fid] = FrameInfo(filename=name, heading=heading, pitch=pitch,
                              pano_id=pano, capture_date=cdate)
    pairs = lq.pick_pairs(frames, max(0, min(int(limit), 50)), judged, exclude_ids)
    return pairs, info, cut_points(), len(judged)


PAIR_RESULTS = ("A", "B", "EQUAL")


def save_pair(db: Session, client_id: str, a_id: int, b_id: int, result: str, *,
              labeller: Optional[str] = None, meta: Optional[dict] = None) -> bool:
    """Store one judgment; a repeated client_id is a no-op (retry-safe)."""
    from app.models.models import PairJudgment

    if result not in PAIR_RESULTS:
        raise QuickLabelError(f"result must be one of {PAIR_RESULTS}")
    if a_id == b_id:
        raise QuickLabelError("a pair needs two different frames")
    if db.query(PairJudgment.id).filter(PairJudgment.client_id == client_id).first():
        return False
    db.add(PairJudgment(client_id=client_id, frame_a_id=a_id, frame_b_id=b_id,
                        result=result, labeller=labeller, meta=meta or {}))
    db.commit()
    return True


def undo_pair(db: Session, client_id: str) -> bool:
    from app.models.models import PairJudgment

    n = db.query(PairJudgment).filter(PairJudgment.client_id == client_id).delete()
    db.commit()
    return bool(n)


# --- stats ----------------------------------------------------------------------

def _local_midnight_utc() -> datetime:
    """Start of 'today' on the server's clock (the owner's machine), as naive
    UTC like the DB timestamps."""
    local_now = datetime.now().astimezone()
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc).replace(tzinfo=None)


def sprint_count(db: Session) -> int:
    """New labels written in sprint mode (an undo removes its quick_label)."""
    return int(db.execute(text(
        "SELECT count(*) FROM training_data WHERE manual_rqi IS NOT NULL "
        "AND (meta_data::jsonb)->'quick_label'->>'strategy' = 'sprint' "
        "AND ((meta_data::jsonb)->'quick_label'->>'created_row')::boolean")).scalar() or 0)


def label_counts(db: Session) -> tuple[int, int]:
    """(all manual labels, quick labels written today)."""
    total = db.execute(text(
        "SELECT count(*) FROM training_data WHERE manual_rqi IS NOT NULL")).scalar() or 0
    today = db.execute(text(
        "SELECT count(*) FROM training_data WHERE manual_rqi IS NOT NULL "
        "AND updated_at >= :since AND (meta_data::jsonb) ? 'quick_label'"),
        {"since": _local_midnight_utc()}).scalar() or 0
    return int(total), int(today)


def recheck_consistency(db: Session) -> dict:
    rows = db.execute(text(
        "SELECT meta_data->'relabel_history' FROM training_data "
        "WHERE (meta_data::jsonb) ? 'relabel_history'")).all()
    # The random control sample only: the honest self-consistency (see lq).
    return lq.consistency_stats((h for (h,) in rows), SCALE, reason="recheck_sample")


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
        previous = meta.get("quick_label") or {}
        added = row.manual_rqi is not None
        if added:
            # Overwriting a label (re-check): keep the old value. Values are
            # stored with the scale direction they were written in, so a later
            # flip (SCALE.convert) cannot misread them.
            meta["relabel_history"] = [*meta.get("relabel_history", []), {
                "timestamp": stamp, "old": row.manual_rqi, "new": float(rqi),
                "strategy": (context or {}).get("strategy"),
                "reason": (context or {}).get("reason"),
                "direction": SCALE.direction,
            }]
        # One-step undo: back to the value this save replaced.
        meta["quick_label"] = {**ql, "created_row": previous.get("created_row", False),
                               "previous_rqi": row.manual_rqi, "history_added": added}
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
    if (ql.get("created_row") and ql.get("previous_rqi") is None
            and not row.annotations and not row.tags and not row.comment):
        db.delete(row)
    else:
        meta.pop("quick_label", None)
        if ql.get("history_added") and meta.get("relabel_history"):
            history = meta["relabel_history"][:-1]
            if history:
                meta["relabel_history"] = history
            else:
                meta.pop("relabel_history")
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


EXAMPLE_AGREE_MAX_GAP = 0.5   # |model - human| in levels for "the model agrees"
EXAMPLE_MIN_AGREEING = 3      # fewer agreeing labels -> no example for that level


def pick_examples(cands: dict[int, list[tuple]], per_class: int,
                  min_agreeing: int = EXAMPLE_MIN_AGREEING,
                  max_gap: float = EXAMPLE_AGREE_MAX_GAP,
                  spacing_m: float = EXAMPLE_SPACING_M) -> list[tuple[int, int, str]]:
    """Pure selection. ``cands[level]`` = (tier, gap, order, pid, name, lat, lon)
    with tier 0 = honest OOF gap, 1 = live-model gap. Only frames whose label
    the model agrees with (gap <= max_gap) can be examples, and a level needs at
    least ``min_agreeing`` of them, else it gets none (the UI says "még nincs
    példa") rather than a misleading picture."""
    out = []
    for level, rows in cands.items():
        agreeing = sorted(r for r in rows if r[1] is not None and r[1] <= max_gap)
        if len(agreeing) < min_agreeing:
            continue
        taken = lq.PointIndex(spacing_m)
        n = 0
        for _tier, _gap, _order, pid, name, lat, lon in agreeing:
            if n >= per_class:
                break
            if lat is not None and lon is not None:
                if taken.near(lat, lon, spacing_m):
                    continue
                taken.add(lat, lon)
            out.append((level, pid, name))
            n += 1
    return out


def label_examples(db: Session, per_class: int = 1) -> list[tuple[int, int, str]]:
    """(level, point id, filename) of clear labelled exemplars per level.

    Integer labels only. "Clear" = the model agrees with the human label: the
    honest out-of-fold prediction (ml/cache/oof_table.csv) when available,
    else the live model score. Levels with too few agreeing labels (today:
    the extreme level the model never predicts) get no example — see
    pick_examples. Several examples of one level are EXAMPLE_SPACING_M apart.
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
    cands: dict[int, list[tuple]] = {r: [] for r in VALID_RQI}
    for order, (rqi, pid, name, lat, lon, score) in enumerate(rows):
        if name not in files:
            continue
        gap, tier = errors.get(name), 0  # |severity difference|: direction-free
        if gap is None:
            s = _float(score)  # stored canonical (see _severity_row)
            if s is None and name in cache:
                s = canonical_score(cache[name][0])  # cache is severity
            gap, tier = (abs(s - rqi) if s is not None else None), 1
        cands[int(rqi)].append((tier, gap, order, pid, name, lat, lon))
    return pick_examples(cands, per_class)
