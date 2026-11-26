"""Map coverage & data-quality report: where to collect and label next.

Usage (from backend/):
    ../.venv/bin/python scripts/coverage_report.py [--top 20] [--cell-km 1] [--no-write]

Prints the report and writes it to ``data/reports/coverage_<date>.md``.
Per area (the four collection areas of ``label_queue.AREAS`` + "other", and
Budapest split into approximate district sectors):

- frames: total / usable / unusable (``frame_quality.usable``), human-labelled;
- capture-date age: share of dated frames older than 3 and 5 years;
- segments and km by class (canonical RQI scale, ``app.core.rqi_scale``);
- confidence mix (high / medium / low) and the ``unlabelled_area`` share;
- the top one-km cells with many usable frames but no human label at all.

The database is only read (the transaction is opened READ ONLY). The
aggregation helpers are pure and unit-tested (tests/test_coverage_report.py).
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.rqi_scale import SCALE  # noqa: E402  (stdlib only)
from app.services.label_queue import AREAS, OTHER_AREA, area_of, haversine_km  # noqa: E402

Bbox = tuple[float, float, float, float]  # south, west, north, east

# No district boundaries are cached, so Budapest is split into APPROXIMATE
# sectors by plain bounding boxes (first match wins; the Danube is taken as
# lon 19.05). Good enough to say "Buda north has frames but no labels"; not a
# substitute for real district polygons.
BUDAPEST = "budapest"
BUDAPEST_SECTORS: tuple[tuple[str, Bbox], ...] = (
    ("inner (V-IX)", (47.475, 19.045, 47.515, 19.095)),
    ("Buda north (II, III)", (47.515, -180.0, 90.0, 19.05)),
    ("Buda south (I, XI, XII, XXII)", (-90.0, -180.0, 47.515, 19.05)),
    ("Pest north (IV, XIII-XVI)", (47.50, 19.05, 90.0, 180.0)),
    ("Pest south (X, XVII-XXI, XXIII)", (-90.0, 19.05, 47.50, 180.0)),
)
AREA_ORDER: tuple[str, ...] = (*AREAS, OTHER_AREA)
TOTAL = "TOTAL"
UNSCORED = "unscored"
LEVELS = ("high", "medium", "low")
AGE_YEARS = (3, 5)

_KM_PER_DEG = 111.32
_REF_LAT = 47.2  # Hungary; fixes the east-west size of a grid cell


# --------------------------------------------------------------------------
# Records (what the pure helpers work on)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FrameRec:
    lat: float
    lon: float
    usable: bool = True
    labelled: bool = False
    capture_date: Optional[dt.date] = None


@dataclass(frozen=True)
class SegmentRec:
    lat: float          # midpoint
    lon: float
    length_m: float
    rqi: Optional[int]  # canonical RQI level, None = not scored
    level: str          # "high" | "medium" | "low"
    unlabelled_area: bool = False


@dataclass
class AreaStats:
    frames: int = 0
    usable: int = 0
    unusable: int = 0
    labelled: int = 0
    dated: int = 0
    older: dict[int, int] = field(default_factory=lambda: {y: 0 for y in AGE_YEARS})
    segments: int = 0
    km: float = 0.0
    segments_by_class: Counter = field(default_factory=Counter)
    km_by_class: Counter = field(default_factory=Counter)
    segments_by_level: Counter = field(default_factory=Counter)
    km_by_level: Counter = field(default_factory=Counter)
    unlabelled_segments: int = 0
    unlabelled_km: float = 0.0


@dataclass(frozen=True)
class Cell:
    lat: float          # cell centre
    lon: float
    area: str
    frames: int         # usable frames in the cell
    nearest_label_km: Optional[float]


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------
def share(part: float, whole: float) -> float:
    """part / whole, 0 when there is nothing to divide by."""
    return part / whole if whole else 0.0


def budapest_sector(lat: float, lon: float) -> str:
    for name, (south, west, north, east) in BUDAPEST_SECTORS:
        if south <= lat < north and west <= lon < east:
            return name
    return "elsewhere"


def area_keys(lat: float, lon: float) -> tuple[str, ...]:
    """Every report row a position counts in: its area, plus the Budapest
    sector row ("budapest / <sector>") when it is in Budapest."""
    area = area_of(lat, lon)
    if area == BUDAPEST:
        return area, f"{BUDAPEST} / {budapest_sector(lat, lon)}"
    return (area,)


def row_order(keys: Iterable[str]) -> list[str]:
    """Areas in collection order, each Budapest sector under Budapest, TOTAL last."""
    present = set(keys)
    out: list[str] = []
    for area in AREA_ORDER:
        if area in present:
            out.append(area)
        if area == BUDAPEST:
            out += [k for k in (f"{BUDAPEST} / {n}" for n, _ in (*BUDAPEST_SECTORS, ("elsewhere", None)))
                    if k in present]
    if TOTAL in present:
        out.append(TOTAL)
    return out


def age_years(capture: dt.date, today: dt.date) -> float:
    return (today - capture).days / 365.25


def summarize(frames: Iterable[FrameRec], segments: Iterable[SegmentRec],
              today: dt.date) -> dict[str, AreaStats]:
    """Per-row totals (areas, Budapest sectors, TOTAL)."""
    stats: dict[str, AreaStats] = {}

    def rows(lat: float, lon: float) -> list[AreaStats]:
        return [stats.setdefault(k, AreaStats()) for k in (*area_keys(lat, lon), TOTAL)]

    for f in frames:
        for s in rows(f.lat, f.lon):
            s.frames += 1
            if f.usable:
                s.usable += 1
            else:
                s.unusable += 1
            if f.labelled:
                s.labelled += 1
            if f.capture_date is not None:
                s.dated += 1
                age = age_years(f.capture_date, today)
                for y in AGE_YEARS:
                    if age > y:
                        s.older[y] += 1
    for g in segments:
        km = g.length_m / 1000.0
        cls = UNSCORED if g.rqi is None else int(g.rqi)
        for s in rows(g.lat, g.lon):
            s.segments += 1
            s.km += km
            s.segments_by_class[cls] += 1
            s.km_by_class[cls] += km
            s.segments_by_level[g.level] += 1
            s.km_by_level[g.level] += km
            if g.unlabelled_area:
                s.unlabelled_segments += 1
                s.unlabelled_km += km
    return stats


def cell_of(lat: float, lon: float, cell_km: float = 1.0) -> tuple[int, int]:
    """Index of the ~cell_km x cell_km grid cell holding the position."""
    return (math.floor(lat * _KM_PER_DEG / cell_km),
            math.floor(lon * _KM_PER_DEG * math.cos(math.radians(_REF_LAT)) / cell_km))


def cell_centre(cell: tuple[int, int], cell_km: float = 1.0) -> tuple[float, float]:
    return ((cell[0] + 0.5) * cell_km / _KM_PER_DEG,
            (cell[1] + 0.5) * cell_km / (_KM_PER_DEG * math.cos(math.radians(_REF_LAT))))


def unlabelled_cells(frames: Iterable[FrameRec], labelled_points: Sequence[tuple[float, float]],
                     top: int = 20, cell_km: float = 1.0) -> list[Cell]:
    """Cells with the most usable frames and no human label in them — the
    best places to label next. ``labelled_points`` are label positions (they
    also cover legacy labels that have no frame row); a labelled frame in
    ``frames`` counts too. Ties: south-west first, so the order is stable."""
    counts: Counter = Counter()
    labelled = {cell_of(lat, lon, cell_km) for lat, lon in labelled_points}
    for f in frames:
        cell = cell_of(f.lat, f.lon, cell_km)
        if f.labelled:
            labelled.add(cell)
        if f.usable:
            counts[cell] += 1
    ranked = sorted(((n, c) for c, n in counts.items() if c not in labelled),
                    key=lambda nc: (-nc[0], nc[1]))[:max(0, top)]
    out = []
    for n, cell in ranked:
        lat, lon = cell_centre(cell, cell_km)
        nearest = min((haversine_km(lat, lon, a, b) for a, b in labelled_points), default=None)
        out.append(Cell(lat=lat, lon=lon, area=area_keys(lat, lon)[-1],
                        frames=n, nearest_label_km=nearest))
    return out


def _pct(part: float, whole: float) -> str:
    return f"{100 * share(part, whole):.0f}%" if whole else "-"


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def class_columns(stats: dict[str, AreaStats]) -> list[object]:
    """Class columns best -> worst (canonical scale), then "unscored" if any."""
    seen = set().union(*(s.segments_by_class for s in stats.values())) if stats else set()
    cols: list[object] = [v for v in SCALE.values if v in seen]
    if UNSCORED in seen:
        cols.append(UNSCORED)
    return cols


def class_label(cls: object) -> str:
    return UNSCORED if cls == UNSCORED else f"{cls} {SCALE.label(cls, 'hu')}"


def headline(stats: dict[str, AreaStats]) -> list[str]:
    t = stats.get(TOTAL, AreaStats())
    lines = [
        f"frames: {t.frames} ({t.usable} usable, {t.unusable} unusable), "
        f"human-labelled: {t.labelled} ({_pct(t.labelled, t.frames)})",
        f"capture date: {t.dated} dated frames, "
        + ", ".join(f"{_pct(t.older[y], t.dated)} older than {y} y" for y in AGE_YEARS),
        f"segments: {t.segments} ({t.km:.1f} km); by class: "
        + ", ".join(f"{class_label(c)} {t.km_by_class[c]:.1f} km" for c in class_columns(stats)),
        "confidence (km): "
        + ", ".join(f"{lv} {_pct(t.km_by_level[lv], t.km)}" for lv in LEVELS)
        + f"; unlabelled_area: {t.unlabelled_segments} segments, "
          f"{t.unlabelled_km:.1f} km ({_pct(t.unlabelled_km, t.km)})",
    ]
    return lines


def render(stats: dict[str, AreaStats], cells: Sequence[Cell], today: dt.date,
           cell_km: float = 1.0, label_points: Optional[int] = None) -> str:
    """The whole report as Markdown."""
    keys = row_order(stats)
    classes = class_columns(stats)
    out = [f"# Coverage & data-quality report — {today.isoformat()}", "", "## Headline", ""]
    out += [f"- {line}" for line in headline(stats)]
    out += ["", "## Frames by area", ""]
    out += _table(
        ["area", "frames", "usable", "unusable", "labelled", "labelled %", "dated",
         *(f"> {y} y" for y in AGE_YEARS)],
        ([k, s.frames, s.usable, s.unusable, s.labelled, _pct(s.labelled, s.frames), s.dated,
          *(_pct(s.older[y], s.dated) for y in AGE_YEARS)] for k, s in ((k, stats[k]) for k in keys)))
    out += ["", "Age shares are of the frames with a known capture date. Budapest "
            "sectors are approximate bounding boxes, not district boundaries.", "",
            f"## Segments and km by class ({SCALE.best} = {SCALE.label(SCALE.best, 'hu')})", ""]
    out += _table(
        ["area", "segments", "km", *(f"{class_label(c)} (seg / km)" for c in classes)],
        ([k, stats[k].segments, f"{stats[k].km:.1f}",
          *(f"{stats[k].segments_by_class[c]} / {stats[k].km_by_class[c]:.1f}" for c in classes)]
         for k in keys))
    out += ["", "## Confidence mix (share of km)", ""]
    out += _table(
        ["area", *LEVELS, "unlabelled_area seg", "unlabelled_area km", "unlabelled_area %"],
        ([k, *(_pct(stats[k].km_by_level[lv], stats[k].km) for lv in LEVELS),
          stats[k].unlabelled_segments, f"{stats[k].unlabelled_km:.1f}",
          _pct(stats[k].unlabelled_km, stats[k].km)] for k in keys))
    out += ["", f"## Top {len(cells)} cells ({cell_km:g} km) with frames but no label", ""]
    out += _table(
        ["#", "centre (lat, lon)", "area", "usable frames", "nearest label km"],
        ([i, f"{c.lat:.4f}, {c.lon:.4f}", c.area, c.frames,
          "-" if c.nearest_label_km is None else f"{c.nearest_label_km:.1f}"]
         for i, c in enumerate(cells, 1)))
    if label_points is not None:
        out += ["", f"A cell counts as labelled when any of the {label_points} label positions "
                "(labelled frames + legacy labels without a frame row) falls in it."]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Database (read only)
# --------------------------------------------------------------------------
def frames_from_rows(rows: Iterable, usable_fn: Callable[[object], bool]) -> list[FrameRec]:
    """(latitude, longitude, usable, labelled, capture_date) rows -> records. Pure."""
    return [FrameRec(lat=float(r[0]), lon=float(r[1]),
                     usable=usable_fn({"frame_quality": {"usable": r[2]}}),
                     labelled=bool(r[3]), capture_date=r[4]) for r in rows]


def load(db) -> tuple[list[FrameRec], list[SegmentRec], list[tuple[float, float]]]:
    from sqlalchemy import text

    from app.services.road_segments import load_labelled_points
    from app.services.segment_aggregation import confidence_level, frame_usable, load_config

    db.execute(text("SET TRANSACTION READ ONLY"))
    cfg = load_config()
    frames = frames_from_rows(db.execute(text(
        """
        SELECT svi.latitude, svi.longitude,
               svi.analysis_metadata->'frame_quality'->>'usable' AS usable,
               EXISTS (SELECT 1 FROM training_data td
                       WHERE td.manual_rqi IS NOT NULL
                         AND 'images/' || td.image_filename = svi.image_url) AS labelled,
               svi.capture_date
        FROM street_view_images svi
        WHERE svi.latitude IS NOT NULL AND svi.longitude IS NOT NULL
        """
    )).fetchall(), frame_usable)
    segments = [
        SegmentRec(lat=float(r.lat), lon=float(r.lon), length_m=float(r.length_m or 0.0),
                   rqi=r.rqi, level=confidence_level(float(r.confidence or 0.0), int(r.n_images or 0), cfg),
                   unlabelled_area=bool(r.unlabelled_area))
        for r in db.execute(text(
            """
            SELECT ST_Y(ST_LineInterpolatePoint(geom, 0.5)) AS lat,
                   ST_X(ST_LineInterpolatePoint(geom, 0.5)) AS lon,
                   length_m, rqi, confidence, n_images, unlabelled_area
            FROM road_segments
            """
        )).fetchall()
    ]
    return frames, segments, load_labelled_points(db)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top", type=int, default=20, help="how many unlabelled cells to list")
    ap.add_argument("--cell-km", type=float, default=1.0, help="grid cell size")
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args()

    from app.core.database import SessionLocal
    from app.core.paths import data_path

    today = dt.date.today()
    db = SessionLocal()
    try:
        frames, segments, labelled_points = load(db)
    finally:
        db.rollback()
        db.close()

    report = render(summarize(frames, segments, today),
                    unlabelled_cells(frames, labelled_points, args.top, args.cell_km),
                    today, args.cell_km, label_points=len(labelled_points))
    print(report)
    if not args.no_write:
        out = data_path("reports", f"coverage_{today.isoformat()}.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"written: {out}")


if __name__ == "__main__":
    main()
