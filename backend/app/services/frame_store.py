"""DB + disk side of frame collection: storing new frames, and picking the
segments a second, denser pass should revisit.

``DbFrameStore`` is the ``FrameStore`` the collection loop
(``network_collector.run_plan``) writes through: duplicate checks against the
stored frames in memory, and one ``street_view_images`` row + one JPEG under
``data/images/`` per new frame — the same shape route collection has always
produced (``images/sv_<id>_<hex>.jpg``, pano id, capture month, unscored).
No Street View URL (and so no API key) is ever stored.
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Sequence

from sqlalchemy import text

from app.services.map_matching import LineIndex
from app.services.network_collector import NewFrame
from app.services.network_sampling import DENSIFY_LOW_CONFIDENCE, SamplingConfig
from app.services.route_quality import SegmentRef
from app.services.segment_aggregation import LEVEL_LOW
from app.services.segment_geometry import haversine_m


class DbFrameStore:
    """Stored frames: duplicate checks in memory, new frames to DB + disk."""

    def __init__(self, db, images_dir: Path | str):
        self.db = db
        self.images_dir = Path(images_dir)
        rows = db.execute(text(
            "SELECT id, latitude, longitude, heading, pano_id FROM street_view_images "
            "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        )).fetchall()
        self.frames = [SimpleNamespace(id=r.id, lat=r.latitude, lon=r.longitude, heading=r.heading)
                       for r in rows]
        self.panos = {r.pano_id for r in rows if r.pano_id}
        self._grid: dict = defaultdict(list)
        for f in self.frames:
            self._grid[self._cell(f.lat, f.lon)].append((f.lat, f.lon))

    @staticmethod
    def _cell(lat: float, lon: float) -> tuple[int, int]:
        return (math.floor(lat / 0.0002), math.floor(lon / 0.0003))   # ~22 m cells

    def has_pano(self, pano_id: str) -> bool:
        return pano_id in self.panos

    def near_existing(self, lat: float, lon: float, radius_m: float) -> bool:
        cy, cx = self._cell(lat, lon)
        for y in (cy - 1, cy, cy + 1):
            for x in (cx - 1, cx, cx + 1):
                for other in self._grid.get((y, x), ()):
                    if haversine_m((lat, lon), other) <= radius_m:
                        return True
        return False

    def save(self, frame: NewFrame, jpeg: bytes) -> int:
        from app.models.models import StreetViewImage, street_view_location

        row: Any = StreetViewImage(  # ORM row: legacy Column models type as Column[...] (see DEVELOPMENT.md)
            latitude=frame.lat, longitude=frame.lon, heading=frame.heading, pitch=frame.pitch,
            location=street_view_location(frame.lat, frame.lon),
            pano_id=frame.pano_id, capture_date=frame.capture_date,
            image_url=None, rqi_score=None,       # pending analysis
            analysis_metadata={"imagery": frame.imagery} if frame.imagery else None,
        )
        self.db.add(row)
        self.db.flush()                            # assigns the id the file name needs
        prefix = "mly" if frame.imagery else "sv"
        filename = f"{prefix}_{row.id}_{uuid.uuid4().hex[:8]}.jpg"
        path = self.images_dir / filename
        try:
            self.images_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpeg)
            row.image_url = f"images/{filename}"
            self.db.commit()
        except Exception:
            self.db.rollback()
            path.unlink(missing_ok=True)
            raise
        self.panos.add(frame.pano_id)
        self.frames.append(SimpleNamespace(id=row.id, lat=frame.lat, lon=frame.lon,
                                           heading=frame.heading))
        self._grid[self._cell(frame.lat, frame.lon)].append((frame.lat, frame.lon))
        return row.id


def segments_to_densify(
    segments: Sequence, frames: Iterable, sampling: SamplingConfig
) -> dict:
    """Second-pass targets (pure): the segments that carry at least one of
    ``frames`` (objects with lat / lon / heading) AND match a rule of
    ``sampling.densify_if``, as line objects keyed by segment id.

    Rules: ``"low_confidence"`` — every segment whose confidence level is
    low; or any ``confidenceReason`` value (``"few_images"``,
    ``"disagreement"``, ``"near_threshold"``, ``"old_images"``) — segments
    that are not high-confidence for exactly that reason. (More frames help
    against few_images and disagreement; they cannot move a score that truly
    sits on a class boundary, nor make old imagery newer.)

    ``segments`` are ``segment_read.SegmentRecord``-like: id, path, rqi,
    score, confidence_level, confidence_reason.
    """
    rules = set(sampling.densify_if)
    if not rules:
        return {}

    def wanted(segment) -> bool:
        if DENSIFY_LOW_CONFIDENCE in rules and segment.confidence_level == LEVEL_LOW:
            return True
        return getattr(segment, "confidence_reason", None) in rules
    index = LineIndex([SegmentRef(s.id, s.path, s.rqi, s.score) for s in segments])
    touched = set()
    for frame in frames:
        match = index.snap((frame.lat, frame.lon), frame.heading)
        if match is not None:
            touched.add(match.line_id)
    return {
        s.id: SimpleNamespace(id=s.id, coords=s.path)
        for s in segments
        if s.id in touched and wanted(s)
    }


def low_confidence_lines(db, bounds, frame_ids: Sequence[int], sampling: SamplingConfig) -> dict:
    """``segments_to_densify`` for the stored segments in ``bounds``
    (south, west, north, east) and the stored frames with ``frame_ids``."""
    from app.services.segment_read import fetch_segments_in_boxes

    if not sampling.densify_if or not frame_ids:
        return {}
    south, west, north, east = bounds
    segments = fetch_segments_in_boxes(db, [(west, south, east, north)])
    rows = db.execute(
        text("SELECT latitude, longitude, heading FROM street_view_images WHERE id = ANY(:ids)"),
        {"ids": list(frame_ids)},
    ).fetchall()
    frames = [SimpleNamespace(lat=r.latitude, lon=r.longitude, heading=r.heading) for r in rows]
    return segments_to_densify(segments, frames, sampling)
