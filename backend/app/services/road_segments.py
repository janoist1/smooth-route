"""Road-segment builder: frames + OSM ways → the ``road_segments`` table.

Pipeline (write side; the GraphQL read side is ``segment_read.py``):

1. load the scored Street View frames (all, or those relevant to a bbox),
2. load the OSM ways of the tiles those frames occupy (``osm_overpass``,
   disk-cached — a rebuild normally needs no network),
3. snap every frame to the nearest bearing-compatible way (``map_matching``),
4. cut each way that received frames into equal pieces of about
   ``segment_length_m`` and assign its frames by linear referencing,
5. aggregate per piece (``segment_aggregation``) and replace the stored rows.

Only ways with at least one snapped frame are stored. Their frame-less pieces
are kept (``n_images = 0``, class NULL) so a road is drawn without gaps where
the camera skipped a stretch; roads we never drove are simply absent.

``build_rows`` is pure and unit-tested; the functions below it do the DB I/O.
Everything here is local/offline code — it must never run on the request
path of the read-only deploy.
"""
from __future__ import annotations

import datetime as dt
import logging
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
from app.services.osm_overpass import (
    PAD_M,
    OverpassClient,
    OverpassError,
    Way,
    pad_bounds,
    tiles_for_points,
)
from app.services.segment_aggregation import (
    FrameObs,
    SegmentConfig,
    aggregate_frames,
    confidence_level,
    frame_p_bad,
    frame_score,
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
    ways_loaded: int = 0
    ways_with_frames: int = 0
    segments: int = 0
    segments_with_data: int = 0
    frames_total: int = 0
    frames_unscored: int = 0
    frames_matched: int = 0
    frames_unmatched: int = 0
    class_counts: dict[int, int] = field(default_factory=dict)
    class_km: dict[int, float] = field(default_factory=dict)
    level_counts: dict[str, int] = field(default_factory=dict)
    km_with_data: float = 0.0
    seconds: float = 0.0
    written: bool = False

    def lines(self) -> list[str]:
        scored = self.frames_matched + self.frames_unmatched
        pct = 100.0 * self.frames_matched / scored if scored else 0.0
        out = [
            f"mode:                {self.mode}",
            f"OSM ways loaded:     {self.ways_loaded} (from {self.tiles} tiles)",
            f"ways with frames:    {self.ways_with_frames}",
            f"segments:            {self.segments} "
            f"(with data {self.segments_with_data}, "
            f"without {self.segments - self.segments_with_data}; "
            f"{self.km_with_data:.1f} km with data)",
            f"frames:              {self.frames_total} total, "
            f"{self.frames_unscored} unscored (skipped)",
            f"  matched:           {self.frames_matched} ({pct:.1f} % of scored)",
            f"  unmatched:         {self.frames_unmatched}",
            "class distribution (segments with data):",
        ]
        for rqi in (1, 2, 3, 4):
            n = self.class_counts.get(rqi, 0)
            share = 100.0 * n / self.segments_with_data if self.segments_with_data else 0.0
            out.append(
                f"  RQI {rqi}: {n:6d} segments ({share:5.1f} %), "
                f"{self.class_km.get(rqi, 0.0):7.1f} km"
            )
        out.append(
            "confidence:          "
            + ", ".join(f"{lvl} {self.level_counts.get(lvl, 0)}" for lvl in ("high", "medium", "low"))
        )
        out.append(f"written to DB:       {'yes' if self.written else 'no (dry run)'}")
        out.append(f"duration:            {self.seconds:.1f} s")
        return out


# --------------------------------------------------------------------------
# Pure core
# --------------------------------------------------------------------------

def segment_id(osm_way_id: int, piece_index: int) -> str:
    return f"{osm_way_id}:{piece_index}"


def build_rows(
    ways: Mapping[int, Way],
    frames: Sequence[Frame],
    cfg: SegmentConfig,
    today: Optional[dt.date] = None,
    *,
    only_way_ids: Optional[set[int]] = None,
    max_distance_m: float = DEFAULT_MAX_DISTANCE_M,
    max_bearing_diff_deg: float = DEFAULT_MAX_BEARING_DIFF_DEG,
) -> tuple[list[dict], BuildStats]:
    """Snap ``frames`` to ``ways``, cut and aggregate. Returns (rows, stats).

    ``only_way_ids`` limits which ways are turned into rows (bbox rebuild);
    matching still considers EVERY way, so a frame is never pulled onto a
    target way just because its true, nearer way is not being rebuilt.
    """
    today = today or dt.date.today()
    stats = BuildStats(ways_loaded=len(ways), frames_total=len(frames))
    index = LineIndex(ways.values())

    by_way: dict[int, list[tuple[float, Frame]]] = defaultdict(list)
    for frame in frames:
        match = index.snap(
            (frame.lat, frame.lon), frame.heading,
            max_distance_m=max_distance_m, max_bearing_diff_deg=max_bearing_diff_deg,
        )
        if match is None:
            stats.frames_unmatched += 1
            continue
        stats.frames_matched += 1
        by_way[match.line_id].append((match.offset_m, frame))

    rows: list[dict] = []
    class_counts: Counter = Counter()
    class_km: Counter = Counter()
    level_counts: Counter = Counter()
    for way_id in sorted(by_way):
        if only_way_ids is not None and way_id not in only_way_ids:
            continue
        way = ways[way_id]
        stats.ways_with_frames += 1
        cum = cumulative_lengths(way.coords)
        total = cum[-1]
        n_pieces = split_count(total, cfg.segment_length_m)
        piece_len = total / n_pieces

        buckets: list[list[FrameObs]] = [[] for _ in range(n_pieces)]
        for offset, frame in by_way[way_id]:
            buckets[piece_index_for_offset(offset, total, n_pieces)].append(
                FrameObs(frame.score, frame.p_bad, frame.capture_date)
            )

        for i, bucket in enumerate(buckets):
            agg = aggregate_frames(bucket, cfg, today)
            coords = (
                list(way.coords) if n_pieces == 1
                else line_substring(way.coords, cum, i * piece_len, (i + 1) * piece_len)
            )
            rows.append({
                "id": segment_id(way_id, i),
                "osm_way_id": way_id,
                "piece_index": i,
                "coords": coords,
                "length_m": piece_len,
                "road_name": way.name,
                "highway": way.highway,
                "n_images": agg.n_images,
                "score": agg.score,
                "rqi": agg.rqi,
                "p_bad": agg.p_bad,
                "confidence": agg.confidence,
                "capture_date_min": agg.capture_date_min,
                "capture_date_max": agg.capture_date_max,
            })
            if agg.n_images > 0:
                stats.segments_with_data += 1
                stats.km_with_data += piece_len / 1000.0
                class_counts[agg.rqi] += 1
                class_km[agg.rqi] += piece_len / 1000.0
                level_counts[confidence_level(agg.confidence, agg.n_images, cfg)] += 1

    stats.segments = len(rows)
    stats.class_counts = dict(class_counts)
    stats.class_km = dict(class_km)
    stats.level_counts = dict(level_counts)
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


# --------------------------------------------------------------------------
# DB I/O
# --------------------------------------------------------------------------

def load_frames(db, bounds: Optional[Bounds] = None) -> tuple[list[Frame], int]:
    """Scored frames (optionally inside ``bounds``) and the count of unscored
    ones that were skipped. Only the two metadata keys we need are pulled out
    of the (large) analysis_metadata JSON, server-side.
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
                   analysis_metadata->>'dino_p_bad' AS dino_p_bad
            FROM street_view_images
            WHERE {" AND ".join(where)}
            ORDER BY id
            """
        ),
        params,
    ).fetchall()

    frames: list[Frame] = []
    unscored = 0
    for r in rows:
        meta = {"dino_score": r.dino_score, "dino_p_bad": r.dino_p_bad}
        score = frame_score(r.dino_rqi_score, meta)
        if score is None:
            unscored += 1
            continue
        frames.append(Frame(
            id=r.id, lat=r.latitude, lon=r.longitude, heading=r.heading,
            score=score, p_bad=frame_p_bad(r.dino_rqi_score, meta),
            capture_date=r.capture_date,
        ))
    return frames, unscored


_INSERT = text(
    """
    INSERT INTO road_segments
        (id, osm_way_id, piece_index, geom, length_m, road_name, highway,
         n_images, score, rqi, p_bad, confidence,
         capture_date_min, capture_date_max, updated_at)
    VALUES
        (:id, :osm_way_id, :piece_index, ST_GeomFromText(:wkt, 4326), :length_m,
         :road_name, :highway, :n_images, :score, :rqi, :p_bad, :confidence,
         :capture_date_min, :capture_date_max, now())
    """
)


def write_rows(db, rows: Sequence[dict], only_way_ids: Optional[set[int]] = None) -> None:
    """Replace the stored segments in ONE transaction (readers keep seeing the
    old rows until the commit). Full rebuild → the whole table; otherwise only
    the rows of ``only_way_ids``.
    """
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": REBUILD_LOCK_KEY})
        if only_way_ids is None:
            db.execute(text("DELETE FROM road_segments"))
        elif only_way_ids:
            db.execute(
                text("DELETE FROM road_segments WHERE osm_way_id = ANY(:ids)"),
                {"ids": sorted(only_way_ids)},
            )
        payload = [
            {**{k: v for k, v in row.items() if k != "coords"},
             "wkt": linestring_wkt(row["coords"])}
            for row in rows
        ]
        for start in range(0, len(payload), 1000):
            db.execute(_INSERT, payload[start:start + 1000])
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
    dry_run: bool = False,
    today: Optional[dt.date] = None,
    log: Callable[[str], None] = print,
) -> BuildStats:
    """Rebuild the segment table — fully, or for the ways touching ``bbox``
    (``(south, west, north, east)``). Idempotent: same inputs → same rows.

    Raises ``OverpassError`` when a needed tile is neither cached nor
    fetchable; nothing is written in that case.
    """
    started = time.monotonic()
    cfg = cfg or load_config()
    if client is None:
        from app.core.paths import data_path

        client = OverpassClient(data_path("osm"), log=log)

    only_way_ids: Optional[set[int]] = None
    if bbox is None:
        frames, unscored = load_frames(db)
        tiles = tiles_for_points((f.lat, f.lon) for f in frames)
        ways = client.load_ways(tiles, allow_fetch=allow_fetch)
    else:
        # 1) The ways to rebuild: every way near the bbox that the frames in
        #    it could snap to.
        area = pad_bounds(bbox, PAD_M)
        seed, _ = load_frames(db, area)
        seed_ways = client.load_ways(
            tiles_for_points((f.lat, f.lon) for f in seed), allow_fetch=allow_fetch
        )
        only_way_ids = {
            w.id for w in seed_ways.values()
            if bounds_intersect(bounds_of(w.coords), area)
        }
        # 2) A way reaches beyond the bbox, and so do its frames: load every
        #    frame around the target ways and every way those frames could
        #    prefer, so each rebuilt way gets exactly what a full rebuild
        #    would give it.
        extent = bounds_of(p for wid in only_way_ids for p in seed_ways[wid].coords)
        if extent is None:
            frames, unscored, tiles, ways = [], 0, set(), {}
        else:
            frames, unscored = load_frames(db, pad_bounds(extent, 2 * DEFAULT_MAX_DISTANCE_M))
            tiles = tiles_for_points((f.lat, f.lon) for f in frames)
            ways = client.load_ways(tiles, allow_fetch=allow_fetch)

    rows, stats = build_rows(ways, frames, cfg, today, only_way_ids=only_way_ids)
    stats.mode = "full" if bbox is None else f"bbox {bbox}"
    stats.tiles = len(tiles)
    stats.frames_unscored = unscored
    stats.frames_total = len(frames) + unscored

    if not dry_run:
        write_rows(db, rows, only_way_ids)
        stats.written = True
    stats.seconds = time.monotonic() - started
    return stats


def refresh_segments_since(
    since: dt.datetime, log: Callable[[str], None] = print, db=None
) -> Optional[BuildStats]:
    """Job hook: rebuild the segments around the frames created since ``since``.

    Never raises — the segment layer is a derived view and must not fail the
    job that produced the data. Overpass is given ONE quick attempt per
    uncached tile; if it is unreachable the refresh is skipped (the next
    ``build_segments.py`` run catches up). ``db`` is injectable for tests.
    """
    from app.core.paths import data_path

    if db is None:
        from app.core.database import SessionLocal

        db = SessionLocal()
    try:
        row = db.execute(
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
            log("road segments: no new frames, nothing to refresh")
            return None
        client = OverpassClient(data_path("osm"), retries=0, timeout_s=60.0, log=log)
        stats = rebuild_segments(
            db, bbox=(row.south, row.west, row.north, row.east), client=client, log=log
        )
        log(
            f"road segments: refreshed {stats.segments} segments on "
            f"{stats.ways_with_frames} ways around {row.n} new frames "
            f"({stats.seconds:.1f} s)"
        )
        return stats
    except OverpassError as exc:
        logger.warning("road segments: Overpass unavailable, refresh skipped (%s)", exc)
        log(f"road segments: Overpass unavailable, refresh skipped ({exc})")
        return None
    except Exception:  # noqa: BLE001 — a derived view must never fail the job
        logger.exception("road segments: refresh failed, skipped")
        return None
    finally:
        db.close()
