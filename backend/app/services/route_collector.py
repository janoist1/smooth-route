"""
Route collection: turn an origin/destination into interpolated Street View
measurement points and persist the new ones (deduped by proximity).
"""
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.services.google_maps import google_maps_service
from app.services.job_service import JobStep, update_job


def collect_points(origin: str, destination: str, job_id: str):
    """Step 1: collect points along the route and store pending measurements."""
    update_job(job_id, current_step=JobStep.COLLECTING, progress=0, total=100,
               message="Útvonal lekérése...")
    print(f"DEBUG: Collecting points from {origin} to {destination}")

    try:
        route_points_dicts = google_maps_service.get_route(origin, destination)
        if not route_points_dicts:
            print("No route found.")
            return

        route_tuples = [(p['lat'], p['lng']) for p in route_points_dicts]
        update_job(job_id, progress=10,
                   message=f"Útvonalpontok feldolgozása ({len(route_tuples)})...")

        # Interpolate every ~10 meters.
        interpolated = google_maps_service.interpolate_points(route_tuples, interval_meters=10.0)
        update_job(job_id, progress=20,
                   message=f"Street View metaadatok generálása ({len(interpolated)} pont)...")

        metadata_list = google_maps_service.generate_street_view_metadata(interpolated)

        db = SessionLocal()
        saved_count = 0
        try:
            total_meta = len(metadata_list)
            for i, meta in enumerate(metadata_list):
                # Skip if an existing point is within 5 meters (dedupe).
                point_geom = f"POINT({meta['longitude']} {meta['latitude']})"
                exists = db.query(StreetViewImage).filter(
                    func.ST_DistanceSphere(
                        StreetViewImage.location, func.ST_GeomFromText(point_geom, 4326)
                    ) < 5.0
                ).first()

                if not exists:
                    db.add(StreetViewImage(
                        latitude=meta['latitude'],
                        longitude=meta['longitude'],
                        heading=meta['heading'],
                        pitch=meta['pitch'],
                        image_url=meta['image_url'],
                        pano_id=meta.get('pano_id'),  # for the Street View deep-link
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
