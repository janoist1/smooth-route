"""Road-segment builder: frames + OSM ways → the ``road_segments`` table.

Pipeline (write side; the GraphQL read side is ``segment_read.py``):

1. load the OSM ways of every tile that holds frames (``osm_overpass``,
   disk-cached — a rebuild normally needs no network),
2. stitch consecutive ways of the same road into longer lines
   (``osm_chains``) — OSM ways are often only tens of metres long,
3. snap every scored Street View frame to the nearest bearing-compatible
   line (``map_matching``),
4. cut each line that received frames into equal pieces of about
   ``segment_length_m`` and assign its frames by linear referencing,
5. aggregate per piece (``segment_aggregation``) and replace the stored rows.

Only pieces with at least one frame are stored: roads (and stretches) we
never photographed are simply absent. A stored row's ``osm_way_id`` is the
line's anchor — the smallest OSM way id of the stitched road — and
``piece_index`` counts the pieces along it.

Full vs. bbox rebuild: the road network and the cut are ALWAYS computed from
all tiles, so a bbox rebuild produces exactly the rows a full rebuild would —
it just re-reads frames and rewrites rows only for the lines touching the
bbox. That shortcut is valid only while the inputs of the stored rows (tile
set, aggregation config, engine version) are unchanged; they are fingerprinted
on the table, and on a mismatch a bbox rebuild silently becomes a full one.

``build_rows`` is pure and unit-tested; the functions below it do the DB I/O.
Everything here is local/offline code — it must never run on the request
path of the read-only deploy.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional, Sequence

from sqlalchemy import text

from app.services.map_matching import (
    DEFAULT_MAX_BEARING_DIFF_DEG,
    DEFAULT_MAX_DISTANCE_M,
    LineIndex,
)
from app.services.osm_chains import merge_ways
from app.services.osm_overpass import (
    PAD_M,
    OverpassClient,
    OverpassError,
    Tile,
    Way,
    cache_path,
    pad_bounds,
    tile_of,
    tiles_for_points,
)
from app.core.rqi_scale import SCALE
from app.services.segment_aggregation import (
    FrameObs,
    SegmentConfig,
    aggregate_frames,
    apply_unlabelled_area,
    confidence_level,
    config_to_dict,
    frame_p_bad,
    frame_score,
    frame_usable,
    load_config,
)
from app.services.segment_geometry import (
    LatLon,
    cumulative_lengths,
    line_substring,
    piece_index_for_offset,
    split_count,
)

logger = logging.getLogger(__name__)

# Serializes rebuilds (CLI vs. the job hook). App-unique advisory-lock key,
# next to MIGRATION_LOCK_KEY in app/core/migrations.py.
REBUILD_LOCK_KEY = 7245002

# Bump when the matching / stitching / cutting logic changes in a way that
# alters the rows: stored rows built by an older engine then force a full
# rebuild instead of being mixed with new ones by a bbox rebuild.
ENGINE_VERSION = 3  # 3: unlabelled_area cap + column

Bounds = tuple[float, float, float, float]  # (south, west, north, east)


@dataclass(frozen=True)
class Frame:
    """One scored Street View frame as the builder needs it."""

    id: int
    lat: float
    lon: float
    heading: Optional[float]
    score: float
    p_bad: Optional[float] = None
    capture_date: Optional[dt.date] = None


@dataclass
class BuildStats:
    mode: str = "full"
    tiles: int = 0
    tiles_missing: int = 0      # occupied but not cached (cached-only build)
    frames_no_osm: int = 0      # frames in those tiles, left out
    ways_loaded: int = 0
    lines: int = 0              # after stitching ways into roads
    lines_with_frames: int = 0
    pieces: int = 0             # all pieces of the lines with frames
    segments: int = 0           # pieces with data = stored rows
    frames_total: int = 0
    frames_unscored: int = 0
    frames_unusable: int = 0    # frame_quality.usable == false
    frames_matched: int = 0
    frames_unmatched: int = 0
    classes: tuple[int, ...] = ()      # class labels of the configured scale
    class_counts: dict[int, int] = field(default_factory=dict)
    class_km: dict[int, float] = field(default_factory=dict)
    level_counts: dict[str, int] = field(default_factory=dict)
    level_km: dict[str, float] = field(default_factory=dict)
    labelled_points: Optional[int] = None   # None = unlabelled-area rule off
    capped_segments: int = 0
    capped_km: float = 0.0
    km: float = 0.0
    median_length_m: float = 0.0
    median_images: float = 0.0
    seconds: float = 0.0
    written: bool = False

    def report(self) -> list[str]:
        scored = self.frames_matched + self.frames_unmatched
        pct = 100.0 * self.frames_matched / scored if scored else 0.0
        out = [
            f"mode:                {self.mode}",
            f"OSM ways:            {self.ways_loaded} from {self.tiles} tiles "
            f"→ {self.lines} lines after stitching",
            *([f"  PARTIAL:           {self.tiles_missing} tiles not cached — "
               f"{self.frames_no_osm} frames there left out"] if self.tiles_missing else []),
            f"lines with frames:   {self.lines_with_frames}",
            f"segments with data:  {self.segments} ({self.km:.1f} km; "
            f"median {self.median_length_m:.0f} m, {self.median_images:.0f} frames) — "
            f"{self.pieces - self.segments} frame-less pieces not stored",
            f"frames:              {self.frames_total} total, "
            f"{self.frames_unscored} unscored + {self.frames_unusable} unusable (skipped)",
            f"  matched:           {self.frames_matched} ({pct:.1f} % of scored)",
            f"  unmatched:         {self.frames_unmatched}",
            "class distribution:",
        ]
        for rqi in self.classes:
            n = self.class_counts.get(rqi, 0)
            share = 100.0 * n / self.segments if self.segments else 0.0
            out.append(
                f"  RQI {rqi}: {n:6d} segments ({share:5.1f} %), "
                f"{self.class_km.get(rqi, 0.0):7.1f} km"
            )
        out.append(
            "confidence:          "
            + ", ".join(
                f"{lvl} {self.level_counts.get(lvl, 0)} ({self.level_km.get(lvl, 0.0):.1f} km)"
                for lvl in ("high", "medium", "low")
            )
        )
        if self.labelled_points is not None:
            out.append(
                f"unlabelled area:     {self.capped_segments} segments "
                f"({self.capped_km:.1f} km) capped — no human label nearby "
                f"({self.labelled_points} labelled frames)"
            )
        out.append(f"written to DB:       {'yes' if self.written else 'no (dry run)'}")
        out.append(f"duration:            {self.seconds:.1f} s")
        return out


# --------------------------------------------------------------------------
# Pure core
# --------------------------------------------------------------------------

class LabelIndex:
    """Grid hash of human-labelled frame positions: "is any label within
    ``radius_km`` of this point?" in O(1) per query."""

    def __init__(self, points: Iterable[LatLon], radius_km: float):
        self.r_m = radius_km * 1000.0
        self.cell = max(self.r_m, 1.0)
        self.grid: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
        for lat, lon in points:
            x, y = self._xy(lat, lon)
            self.grid[(int(x // self.cell), int(y // self.cell))].append((x, y))

    @staticmethod
    def _xy(lat: float, lon: float) -> tuple[float, float]:
        return (lon * 111_320.0 * math.cos(math.radians(47.0)), lat * 111_320.0)

    def any_within(self, lat: float, lon: float) -> bool:
        x, y = self._xy(lat, lon)
        cx, cy = int(x // self.cell), int(y // self.cell)
        r2 = self.r_m * self.r_m
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for px, py in self.grid.get((i, j), ()):
                    if (px - x) ** 2 + (py - y) ** 2 <= r2:
                        return True
        return False


def segment_id(osm_way_id: int, piece_index: int) -> str:
    return f"{osm_way_id}:{piece_index}"


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def build_rows(
    lines: Mapping[int, Way],
    frames: Sequence[Frame],
    cfg: SegmentConfig,
    today: Optional[dt.date] = None,
    *,
    only_ids: Optional[set[int]] = None,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    max_bearing_diff_deg: float = DEFAULT_MAX_BEARING_DIFF_DEG,
    labelled: Optional[Sequence[LatLon]] = None,
) -> tuple[list[dict], BuildStats]:
    """Snap ``frames`` to ``lines``, cut and aggregate. Returns (rows, stats).

    ``lines`` are the roads to cut (stitched ways, or raw ways). One row per
    piece that received frames.

    ``only_ids`` limits which lines are turned into rows (bbox rebuild);
    matching still considers EVERY line, so a frame is never pulled onto a
    target line just because its true, nearer line is not being rebuilt.

    ``labelled`` = positions of human-labelled frames for the unlabelled-area
    cap (``cfg.unlabelled_area``); None leaves the rule off.
    """
    today = today or dt.date.today()
    stats = BuildStats(lines=len(lines), frames_total=len(frames))
    label_index = None
    if labelled is not None and cfg.unlabelled_area.radius_km > 0:
        label_index = LabelIndex(labelled, cfg.unlabelled_area.radius_km)
        stats.labelled_points = len(labelled)
    index = LineIndex(lines.values())

    by_line: dict[int, list[tuple[float, Frame]]] = defaultdict(list)
    for frame in frames:
        match = index.snap(
            (frame.lat, frame.lon), frame.heading,
            max_distance_m=max_distance_m, max_bearing_diff_deg=max_bearing_diff_deg,
        )
        if match is None:
            stats.frames_unmatched += 1
            continue
        stats.frames_matched += 1
        by_line[match.line_id].append((match.offset_m, frame))

    rows: list[dict] = []
    class_counts: Counter = Counter()
    class_km: Counter = Counter()
    level_counts: Counter = Counter()
    level_km: Counter = Counter()
    for line_id in sorted(by_line):
        if only_ids is not None and line_id not in only_ids:
            continue
        line = lines[line_id]
        stats.lines_with_frames += 1
        cum = cumulative_lengths(line.coords)
        total = cum[-1]
        n_pieces = split_count(total, cfg.segment_length_m)
        piece_len = total / n_pieces
        stats.pieces += n_pieces

        buckets: dict[int, list[FrameObs]] = defaultdict(list)
        # Sorted by frame id so the aggregate does not depend on input order.
        for offset, frame in sorted(by_line[line_id], key=lambda item: item[1].id):
            buckets[piece_index_for_offset(offset, total, n_pieces)].append(
                FrameObs(frame.score, frame.p_bad, frame.capture_date)
            )

        for i in sorted(buckets):
            agg = aggregate_frames(buckets[i], cfg, today)
            coords = (
                list(line.coords) if n_pieces == 1
                else line_substring(line.coords, cum, i * piece_len, (i + 1) * piece_len)
            )
            confidence, capped = agg.confidence, False
            if label_index is not None:
                mid_lat = sum(c[0] for c in coords) / len(coords)
                mid_lon = sum(c[1] for c in coords) / len(coords)
                confidence, capped = apply_unlabelled_area(
                    agg.confidence, label_index.any_within(mid_lat, mid_lon), cfg)
            if capped:
                stats.capped_segments += 1
                stats.capped_km += piece_len / 1000.0
            rows.append({
                "id": segment_id(line_id, i),
                "osm_way_id": line_id,
                "piece_index": i,
                "coords": coords,
                "length_m": piece_len,
                "road_name": line.name,
                "highway": line.highway,
                "n_images": agg.n_images,
                "score": agg.score,
                "rqi": agg.rqi,
                "p_bad": agg.p_bad,
                "confidence": confidence,
                "unlabelled_area": capped,
                "capture_date_min": agg.capture_date_min,
                "capture_date_max": agg.capture_date_max,
            })
            level = confidence_level(confidence, agg.n_images, cfg)
            class_counts[agg.rqi] += 1
            class_km[agg.rqi] += piece_len / 1000.0
            level_counts[level] += 1
            level_km[level] += piece_len / 1000.0

    stats.segments = len(rows)
    stats.classes = cfg.scale.ascending
    stats.km = sum(r["length_m"] for r in rows) / 1000.0
    stats.median_length_m = _median([r["length_m"] for r in rows])
    stats.median_images = _median([r["n_images"] for r in rows])
    stats.class_counts = dict(class_counts)
    stats.class_km = dict(class_km)
    stats.level_counts = dict(level_counts)
    stats.level_km = dict(level_km)
    return rows, stats


def linestring_wkt(coords: Sequence[LatLon]) -> str:
    """WKT LineString (lon lat order) from ``(lat, lon)`` vertices."""
    return "LINESTRING(" + ", ".join(f"{lon:.7f} {lat:.7f}" for lat, lon in coords) + ")"


def bounds_of(points: Iterable[LatLon]) -> Optional[Bounds]:
    lats, lons = [], []
    for lat, lon in points:
        lats.append(lat)
        lons.append(lon)
    if not lats:
        return None
    return (min(lats), min(lons), max(lats), max(lons))


def bounds_intersect(a: Bounds, b: Bounds) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def build_fingerprint(
    tiles: Mapping[Tile, int], cfg: SegmentConfig, merge: bool
) -> str:
    """Hash of everything the stored rows depend on besides the frames:
    the OSM tiles (id + cached size), the aggregation config, whether ways
    were stitched, and the engine version.
    """
    payload = {
        "engine": ENGINE_VERSION,
        "merge": bool(merge),
        "config": config_to_dict(cfg),
        "tiles": sorted([t[0], t[1], size] for t, size in tiles.items()),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------
# DB I/O
# --------------------------------------------------------------------------

def occupied_tiles(db, tile_deg: float) -> set[Tile]:
    """Tiles that contain at least one frame (scored or not)."""
    rows = db.execute(
        text(
            "SELECT latitude, longitude FROM street_view_images "
            "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        )
    ).fetchall()
    return tiles_for_points(((r[0], r[1]) for r in rows), tile_deg)


@dataclass
class FrameLoad:
    frames: list[Frame]
    unscored: int = 0      # no RQI yet
    unusable: int = 0      # frame_quality.usable == false


def load_frames(db, cfg: SegmentConfig, bounds: Optional[Bounds] = None) -> FrameLoad:
    """The frames the builder may use (optionally inside ``bounds``), plus how
    many were skipped as unscored / marked unusable. Only the metadata keys we
    need are pulled out of the (large) analysis_metadata JSON, server-side.
    """
    where = ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    params: dict = {}
    if bounds is not None:
        where.append("latitude BETWEEN :south AND :north")
        where.append("longitude BETWEEN :west AND :east")
        params.update(south=bounds[0], west=bounds[1], north=bounds[2], east=bounds[3])
    rows = db.execute(
        text(
            f"""
            SELECT id, latitude, longitude, heading, dino_rqi_score, capture_date,
                   analysis_metadata->>'dino_score' AS dino_score,
                   analysis_metadata->>'dino_p_bad' AS dino_p_bad,
                   analysis_metadata->'frame_quality'->>'usable' AS usable
            FROM street_view_images
            WHERE {" AND ".join(where)}
            ORDER BY id
            """
        ),
        params,
    ).fetchall()

    return frames_from_rows(rows, cfg)


def frames_from_rows(rows: Iterable, cfg: SegmentConfig) -> FrameLoad:
    """Rows (id, latitude, longitude, heading, dino_rqi_score, capture_date,
    dino_score, dino_p_bad, usable) → usable, scored frames. Pure."""
    load = FrameLoad(frames=[])
    for r in rows:
        meta = {
            "dino_score": r.dino_score,
            "dino_p_bad": r.dino_p_bad,
            "frame_quality": {"usable": r.usable},
        }
        if not frame_usable(meta):
            load.unusable += 1
            continue
        score = frame_score(r.dino_rqi_score, meta)
        if score is None:
            load.unscored += 1
            continue
        load.frames.append(Frame(
            id=r.id, lat=r.latitude, lon=r.longitude, heading=r.heading,
            score=score, p_bad=frame_p_bad(r.dino_rqi_score, meta, cfg.scale),
            capture_date=r.capture_date,
        ))
    return load


_LEGACY_NAME_RE = re.compile(r"^\d+_(-?\d+\.\d+)_(-?\d+\.\d+)_")


def load_labelled_points(db) -> list[LatLon]:
    """Positions of every human-labelled frame (training_data.manual_rqi set).

    Same join as ml/export_labels.sh (street_view_images.image_url =
    'images/' || image_filename); legacy ``<seq>_<lat>_<lon>_<heading>.jpg``
    files without a DB row carry their position in the name.
    """
    rows = db.execute(text(
        """
        SELECT td.image_filename, svi.latitude, svi.longitude
        FROM training_data td
        LEFT JOIN street_view_images svi ON svi.image_url = 'images/' || td.image_filename
        WHERE td.manual_rqi IS NOT NULL
        """
    )).fetchall()
    return labelled_points_from_rows(rows)


def labelled_points_from_rows(rows: Iterable) -> list[LatLon]:
    """(image_filename, latitude, longitude) rows → positions. Pure."""
    out: list[LatLon] = []
    for name, lat, lon in rows:
        if lat is not None and lon is not None:
            out.append((float(lat), float(lon)))
            continue
        m = _LEGACY_NAME_RE.match(name or "")
        if m:
            out.append((float(m.group(1)), float(m.group(2))))
    return out


_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{40}$")
_COMMENT_PREFIX = "build:"


def stored_fingerprint(db) -> Optional[str]:
    """Fingerprint of the last FULL rebuild (kept as the table comment so it
    lives and dies with the rows; None when never built)."""
    comment = db.execute(
        text("SELECT obj_description('road_segments'::regclass, 'pg_class')")
    ).scalar()
    if comment and comment.startswith(_COMMENT_PREFIX):
        value = comment[len(_COMMENT_PREFIX):]
        if _FINGERPRINT_RE.match(value):
            return value
    return None


_INSERT = text(
    """
    INSERT INTO road_segments
        (id, osm_way_id, piece_index, geom, length_m, road_name, highway,
         n_images, score, rqi, p_bad, confidence, unlabelled_area,
         capture_date_min, capture_date_max, updated_at)
    VALUES
        (:id, :osm_way_id, :piece_index, ST_GeomFromText(:wkt, 4326), :length_m,
         :road_name, :highway, :n_images, :score, :rqi, :p_bad, :confidence,
         :unlabelled_area, :capture_date_min, :capture_date_max, now())
    """
)


def write_rows(
    db,
    rows: Sequence[dict],
    only_ids: Optional[set[int]] = None,
    fingerprint: Optional[str] = None,
) -> None:
    """Replace the stored segments in ONE transaction (readers keep seeing the
    old rows until the commit). ``only_ids=None`` → the whole table, and the
    fingerprint is recorded; otherwise only the rows of those lines.
    """
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": REBUILD_LOCK_KEY})
        if only_ids is None:
            db.execute(text("DELETE FROM road_segments"))
        elif only_ids:
            db.execute(
                text("DELETE FROM road_segments WHERE osm_way_id = ANY(:ids)"),
                {"ids": sorted(only_ids)},
            )
        payload = [
            {**{k: v for k, v in row.items() if k != "coords"},
             "wkt": linestring_wkt(row["coords"])}
            for row in rows
        ]
        for start in range(0, len(payload), 1000):
            db.execute(_INSERT, payload[start:start + 1000])
        if only_ids is None and fingerprint is not None:
            if not _FINGERPRINT_RE.match(fingerprint):
                raise ValueError("fingerprint must be a sha1 hex digest")
            # COMMENT takes no bind parameters; the value is validated hex.
            db.execute(text(
                f"COMMENT ON TABLE road_segments IS '{_COMMENT_PREFIX}{fingerprint}'"
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise


def rebuild_segments(
    db,
    *,
    bbox: Optional[Bounds] = None,
    cfg: Optional[SegmentConfig] = None,
    client: Optional[OverpassClient] = None,
    allow_fetch: bool = True,
    cached_only: bool = False,
    merge: bool = True,
    dry_run: bool = False,
    today: Optional[dt.date] = None,
    log: Callable[[str], None] = print,
) -> BuildStats:
    """Rebuild the segment table — fully, or only the lines touching ``bbox``
    (``(south, west, north, east)``). Idempotent: same inputs → same rows.

    ``merge=False`` cuts every OSM way on its own (no stitching).

    ``cached_only=True`` builds from the OSM tiles already on disk and leaves
    out the frames of tiles that are not (a partial layer while Overpass is
    slow or unreachable). The next normal build sees a different tile set and
    rebuilds everything.

    Raises ``OverpassError`` when a needed tile is neither cached nor
    fetchable; nothing is written in that case.
    """
    started = time.monotonic()
    cfg = cfg or load_config()
    if client is None:
        from app.core.paths import data_path

        client = OverpassClient(data_path("osm"), log=log)

    tiles = occupied_tiles(db, client.tile_deg)
    missing: set[Tile] = set()
    if cached_only:
        missing = {t for t in tiles if not client.is_cached(t)}
        tiles -= missing
    ways = client.load_ways(tiles, allow_fetch=allow_fetch and not cached_only)
    lines = merge_ways(ways) if merge else dict(ways)
    fingerprint = build_fingerprint(
        {t: cache_path(client.cache_dir, t, client.tile_deg).stat().st_size for t in tiles},
        cfg, merge,
    )

    only_ids: Optional[set[int]] = None
    if bbox is not None and not dry_run and stored_fingerprint(db) != fingerprint:
        log("road segments: OSM tiles / config / engine changed since the last "
            "full rebuild — doing a full rebuild instead of the bbox one")
        bbox = None

    if bbox is None:
        load = load_frames(db, cfg)
    else:
        area = pad_bounds(bbox, PAD_M)
        only_ids = {
            line_id for line_id, line in lines.items()
            if bounds_intersect(bounds_of(line.coords), area)
        }
        # A line reaches beyond the bbox, and so do its frames: load every
        # frame around the target lines. (Matching runs against ALL lines.)
        extent = bounds_of(p for line_id in only_ids for p in lines[line_id].coords)
        if extent is None:
            load = FrameLoad(frames=[])
        else:
            load = load_frames(db, cfg, pad_bounds(extent, 2 * DEFAULT_MAX_DISTANCE_M))
    frames = load.frames

    no_osm = 0
    if missing:
        covered = [f for f in frames if tile_of(f.lat, f.lon, client.tile_deg) not in missing]
        no_osm = len(frames) - len(covered)
        frames = covered

    labelled = (load_labelled_points(db) if cfg.unlabelled_area.radius_km > 0
                else None)
    rows, stats = build_rows(lines, frames, cfg, today, only_ids=only_ids,
                             labelled=labelled)
    stats.mode = "full" if bbox is None else f"bbox {bbox} ({len(only_ids or ())} lines)"
    stats.tiles = len(tiles)
    stats.tiles_missing = len(missing)
    stats.frames_no_osm = no_osm
    stats.ways_loaded = len(ways)
    stats.frames_unscored = load.unscored
    stats.frames_unusable = load.unusable
    stats.frames_total = len(frames) + load.unscored + load.unusable + no_osm

    if not dry_run:
        write_rows(db, rows, only_ids, fingerprint)
        stats.written = True
    stats.seconds = time.monotonic() - started
    return stats


def _refresh(
    describe: str,
    pick_bbox: Callable[[object], tuple[Optional[Bounds], bool]],
    log: Callable[[str], None],
    db=None,
) -> Optional[BuildStats]:
    """Shared body of the job hooks. Never raises — the segment layer is a
    derived view and must not fail the job that produced the data. Overpass
    gets ONE quick attempt per uncached tile; if it is unreachable the refresh
    is skipped (the next ``build_segments.py`` run catches up).
    """
    from app.core.paths import data_path

    if db is None:
        from app.core.database import SessionLocal

        db = SessionLocal()
    try:
        bbox, proceed = pick_bbox(db)
        if not proceed:
            log(f"road segments: {describe}: nothing to refresh")
            return None
        client = OverpassClient(data_path("osm"), retries=0, timeout_s=60.0, log=log)
        stats = rebuild_segments(db, bbox=bbox, client=client, log=log)
        log(
            f"road segments: {describe}: {stats.segments} segments on "
            f"{stats.lines_with_frames} lines rewritten ({stats.mode}, {stats.seconds:.1f} s)"
        )
        return stats
    except OverpassError as exc:
        log(f"road segments: Overpass unavailable, refresh skipped ({exc})")
        return None
    except Exception:  # noqa: BLE001 — a derived view must never fail the job
        logger.exception("road segments: refresh failed, skipped")
        return None
    finally:
        db.close()


def refresh_segments_since(
    since: dt.datetime, log: Callable[[str], None] = print, db=None
) -> Optional[BuildStats]:
    """Route-job hook: bbox rebuild around the frames created since ``since``."""

    def pick(session) -> tuple[Optional[Bounds], bool]:
        row = session.execute(
            text(
                """
                SELECT min(latitude) AS south, min(longitude) AS west,
                       max(latitude) AS north, max(longitude) AS east, count(*) AS n
                FROM street_view_images
                WHERE created_at >= :since
                  AND latitude IS NOT NULL AND longitude IS NOT NULL
                """
            ),
            {"since": since},
        ).one()
        if not row.n:
            return None, False
        return (row.south, row.west, row.north, row.east), True

    return _refresh("new frames", pick, log, db)


def refresh_segments_full(log: Callable[[str], None] = print, db=None) -> Optional[BuildStats]:
    """Analysis-job hook: scores changed anywhere → full rebuild (from cache)."""
    return _refresh("scores changed", lambda _session: (None, True), log, db)
