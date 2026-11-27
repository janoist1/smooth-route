"""
Route collection: turn an origin/destination into Street View measurement
points and persist the new ones (deduped by proximity).

Two passes, both spaced by the ``sampling`` block of
``backend/config/segment_aggregation.json`` (the ML recipe):

1. ``collect_points`` — one point every ``base_spacing_m`` (50 m) along the
   route. Enough to place every ~200 m segment in a class.
2. ``densify_low_confidence`` — after scoring and the segment rebuild, extra
   points every ``dense_spacing_m`` (30 m), but only on the segments of this
   job whose confidence came out low. Images are spent where they change
   the answer, not everywhere.

Every image request is booked on the monthly quota and the job's budget
before it is sent (``sv_client``).
"""
from sqlalchemy import func, text

from app.core.database import SessionLocal
from app.models.models import StreetViewImage, street_view_location
from app.services.google_maps import google_maps_service
from app.services.routing import routing_service
from app.services.job_service import JobStep, update_job
from app.services.network_sampling import load_sampling, sample_route


def collect_points(origin: str, destination: str, job_id: str,
                   path: list[tuple[float, float]] | None = None):
    """Step 1: collect points along the route and store pending measurements."""
    update_job(job_id, current_step=JobStep.COLLECTING, progress=0, total=100,
               message="Útvonal lekérése...")
    print(f"DEBUG: Collecting points from {origin} to {destination}")

    try:
        # A planned alternative already has geometry: reuse it without Directions.
        if path is None:
            route_points_dicts = routing_service.get_route(origin, destination)
            route_tuples = [(p['lat'], p['lng']) for p in route_points_dicts]
        else:
            route_tuples = path
        if not route_tuples:
            print("No route found.")
            return

        update_job(job_id, progress=10,
                   message=f"Útvonalpontok feldolgozása ({len(route_tuples)})...")

        # First pass: one point every base_spacing_m (50 m) along the route.
        interpolated = sample_route(route_tuples, load_sampling().base_spacing_m)
        update_job(job_id, progress=20,
                   message=f"Street View metaadatok generálása ({len(interpolated)} pont)...")

        metadata_list = google_maps_service.generate_street_view_metadata(interpolated)

        db = SessionLocal()
        saved_count = 0
        try:
            total_meta = len(metadata_list)
            for i, meta in enumerate(metadata_list):
                # Preserve proximity-only dedupe: heading is intentionally ignored,
                # even for opposite views. Fall back for rows predating the backfill.
                point_geom = f"POINT({meta['longitude']} {meta['latitude']})"
                exists = db.query(StreetViewImage).filter(
                    func.ST_DistanceSphere(
                        func.coalesce(
                            StreetViewImage.location,
                            func.ST_SetSRID(func.ST_MakePoint(
                                StreetViewImage.longitude, StreetViewImage.latitude,
                            ), 4326),
                        ),
                        func.ST_GeomFromText(point_geom, 4326),
                    ) < 5.0
                ).first()

                if not exists:
                    db.add(StreetViewImage(
                        latitude=meta['latitude'],
                        longitude=meta['longitude'],
                        location=street_view_location(meta['latitude'], meta['longitude']),
                        heading=meta['heading'],
                        pitch=meta['pitch'],
                        image_url=meta['image_url'],
                        pano_id=meta.get('pano_id'),  # for the Street View deep-link
                        capture_date=meta.get('capture_date'),  # how old the imagery is
                        rqi_score=None,  # pending analysis
                    ))
                    saved_count += 1

                if i % 20 == 0:
                    db.commit()  # periodic commit
                    update_job(job_id, progress=20 + int((i / total_meta) * 10))  # 20% -> 30%

            db.commit()
            print(f"DEBUG: Saved {saved_count} new points.")
            update_job(job_id, progress=30, message=f"{saved_count} új mérési pont rögzítve.")
        finally:
            db.close()

    except Exception as e:
        print(f"Error collecting points: {e}")
        raise


def densify_low_confidence(job_id: str, since, budget=None) -> int:
    """Second pass of a route job: dense points on the low-confidence
    segments that carry frames created since ``since``. Returns the number of
    frames added (already downloaded; they still need scoring).

    Stops quietly at the budget; raises on a quota / billing / key signal so
    the job is reported as failed rather than silently incomplete.
    """
    from app.core.paths import data_path
    from app.services.frame_store import DbFrameStore, low_confidence_lines
    from app.services.network_collector import STOP_TROUBLE, ResumeLog, run_plan
    from app.services.network_sampling import plan_collection
    from app.services.sv_client import StreetViewFatal, default_client

    sampling = load_sampling()
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id, latitude, longitude FROM street_view_images "
                 "WHERE created_at >= :since AND latitude IS NOT NULL AND longitude IS NOT NULL"),
            {"since": since},
        ).fetchall()
        if not rows:
            return 0
        pad = 0.001  # ~100 m around the job's frames
        bounds = (min(r.latitude for r in rows) - pad, min(r.longitude for r in rows) - pad,
                  max(r.latitude for r in rows) + pad, max(r.longitude for r in rows) + pad)
        lines = low_confidence_lines(db, bounds, [r.id for r in rows], sampling)
        if not lines:
            return 0
        update_job(job_id, message=f"Sűrítés: {len(lines)} bizonytalan szakasz...")
        store = DbFrameStore(db, data_path("images"))
        plan = plan_collection(lines, store.frames, sampling.dense_spacing_m)
        resume = ResumeLog(data_path("collect", f"job_{job_id}_dense.jsonl"))
        result = run_plan(
            plan, client=default_client(), store=store, lines=lines, resume=resume,
            job=budget, radius_m=sampling.dense_spacing_m / 2.0,
        )
        print(f"DEBUG: densify pass: {result.stop} {result.detail} {dict(result.counts)}")
        if result.stop == STOP_TROUBLE:
            raise StreetViewFatal(f"Street View second pass stopped: {result.detail}")
        return result.counts.get("saved", 0)
    finally:
        db.close()
