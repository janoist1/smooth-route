"""Seed a tiny, deterministic fixture database for the Playwright E2E smoke suite.

Used by .github/workflows/e2e.yml (and runnable locally against a throwaway
PostGIS). It refuses to touch a database that already holds frames.

    cd backend
    DATABASE_URL=postgresql://postgres:postgres@localhost:5440/e2e \\
        DATA_DIR=/tmp/e2e-data python scripts/seed_e2e_fixture.py

What it creates (around the E2E suite's BUDAPEST centre, 47.5007 / 19.0517):
- schema via Alembic (head),
- ~40 scored, usable frames on three short roads through the centre, with a
  JPEG each under DATA_DIR/images (plain colour tiles, no Google imagery),
- road segments (~150 m pieces) over those roads, rated, confident,
- one human-labelled frame (training_data), so the quick-rate page has history.
Scores use the live scale: 5 = Kiváló (best) … 1 = Nagyon rossz.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRE = (47.5007, 19.0517)
# (name, osm way id, start (lat, lng), end (lat, lng), frames)
ROADS = [
    ("Teszt utca", 9_000_001, (47.5007, 19.0447), (47.5007, 19.0587), 16),
    ("Próba körút", 9_000_002, (47.4967, 19.0517), (47.5047, 19.0517), 14),
    ("Minta út", 9_000_003, (47.4977, 19.0467), (47.5037, 19.0567), 12),
]
SEGMENT_LENGTH_M = 150.0


def haversine_m(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def bearing(a, b):
    y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0]))
    x = math.cos(math.radians(a[0])) * math.sin(math.radians(b[0])) - math.sin(
        math.radians(a[0])
    ) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1]))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def class_for(score: float) -> int:
    return max(1, min(5, int(round(score))))


def write_jpeg(path: Path, rqi: int) -> None:
    from PIL import Image

    colours = {5: (70, 90, 120), 4: (90, 110, 130), 3: (150, 130, 80), 2: (160, 100, 70), 1: (150, 60, 60)}
    img = Image.new("RGB", (600, 400), colours[rqi])
    # A lighter "road" band in the lower part so the frame is not one flat colour.
    road = Image.new("RGB", (600, 160), tuple(min(255, c + 40) for c in colours[rqi]))
    img.paste(road, (0, 240))
    img.save(path, "JPEG", quality=70)


def main() -> None:
    from sqlalchemy import text

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.core.migrations import ensure_database_schema

    ensure_database_schema()
    images_dir = Path(settings.resolve_data_dir()) / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        if db.execute(text("SELECT count(*) FROM street_view_images")).scalar():
            sys.exit("refusing to seed: street_view_images is not empty (use a throwaway database)")
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        frame_id = 0
        frames_by_road: dict[int, list[tuple[int, float, dt.date]]] = {}
        for road_idx, (name, way, start, end, n) in enumerate(ROADS):
            heading = bearing(start, end)
            for i in range(n):
                frame_id += 1
                lat, lng = lerp(start, end, i / (n - 1))
                # Deterministic spread over classes 2..5, one stale capture per road.
                score = 2.2 + ((frame_id * 7) % 30) / 10.0
                rqi = class_for(score)
                p_bad = round(max(0.0, min(1.0, (3.5 - score) / 1.5 + 0.5)), 3)
                capture = dt.date(2015, 6, 1) if i == 0 else dt.date(2024 + (i % 2), 1 + (i % 12), 1)
                filename = f"e2e_{frame_id:03d}.jpg"
                write_jpeg(images_dir / filename, rqi)
                meta = {
                    "dino_score": round(score, 3),
                    "dino_p_bad": p_bad,
                    "dino_strategy": "DINO Classification",
                    "frame_quality": {"usable": True, "reasons": [], "version": 1},
                }
                db.execute(
                    text(
                        """INSERT INTO street_view_images
                           (id, latitude, longitude, heading, pitch, image_url, location, created_at,
                            rqi_score, dino_rqi_score, damage_count, damage_types, analysis_metadata,
                            pano_id, capture_date)
                           VALUES (:id, :lat, :lng, :heading, -20, :url,
                                   ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :now,
                                   :rqi, :rqi, 0, '{}', CAST(:meta AS json), :pano, :capture)"""
                    ),
                    {"id": frame_id, "lat": lat, "lng": lng, "heading": heading, "url": f"images/{filename}",
                     "now": now, "rqi": float(rqi), "meta": json.dumps(meta),
                     "pano": f"E2E_PANO_{frame_id:03d}", "capture": capture},
                )
                frames_by_road.setdefault(road_idx, []).append((frame_id, score, capture))

            # Segments: ~150 m pieces along the straight road.
            length = haversine_m(start, end)
            pieces = max(1, round(length / SEGMENT_LENGTH_M))
            frames = frames_by_road[road_idx]
            for p in range(pieces):
                a, b = lerp(start, end, p / pieces), lerp(start, end, (p + 1) / pieces)
                mid = lerp(a, b, 0.5)
                own = frames[int(p / pieces * len(frames)): int((p + 1) / pieces * len(frames))] or frames[:1]
                scores = sorted(s for _, s, _ in own)
                score = scores[len(scores) // 2]
                dates = sorted(c for _, _, c in own)
                db.execute(
                    text(
                        """INSERT INTO road_segments
                           (id, osm_way_id, piece_index, geom, length_m, road_name, highway, n_images,
                            score, rqi, p_bad, confidence, capture_date_min, capture_date_max,
                            updated_at, unlabelled_area, maxspeed_kmh)
                           VALUES (:id, :way, :piece,
                                   ST_SetSRID(ST_MakeLine(ARRAY[ST_MakePoint(:alng, :alat),
                                                                ST_MakePoint(:mlng, :mlat),
                                                                ST_MakePoint(:blng, :blat)]), 4326),
                                   :len, :name, 'primary', :n, :score, :rqi, :pbad, :conf,
                                   :dmin, :dmax, :now, false, 50)"""
                    ),
                    {"id": f"{way}:{p}", "way": way, "piece": p, "alat": a[0], "alng": a[1],
                     "mlat": mid[0], "mlng": mid[1], "blat": b[0], "blng": b[1],
                     "len": haversine_m(a, b), "name": name, "n": len(own), "score": round(score, 3),
                     "rqi": class_for(score), "pbad": round(max(0.0, min(1.0, (3.5 - score) / 1.5 + 0.5)), 3),
                     "conf": 0.6 + 0.1 * (p % 3), "dmin": dates[0], "dmax": dates[-1], "now": now},
                )

        # One human label, so label history / quick-rate have something to show.
        db.execute(
            text("""INSERT INTO training_data (image_filename, manual_rqi, created_at, updated_at)
                    VALUES ('e2e_001.jpg', 4, :now, :now)"""),
            {"now": now},
        )
        db.execute(text("SELECT setval(pg_get_serial_sequence('street_view_images', 'id'), :m)"), {"m": frame_id})
        db.commit()
        segs = db.execute(text("SELECT count(*) FROM road_segments")).scalar()
        print(f"seeded {frame_id} frames, {segs} segments, 1 label; images in {images_dir}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
