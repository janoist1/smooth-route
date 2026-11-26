"""
Image download: fetch the actual Street View JPEGs for pending points and
rewrite their image_url to the local path.
"""
import os
import shutil
import uuid

import requests

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.services.capture_date import parse_capture_date
from app.services.job_service import JobStep, update_job


def fill_capture_metadata(img: StreetViewImage, lookup=None) -> None:
    """Fill pano_id / capture_date right after the image was fetched.

    Points collected by the current route_collector already carry both; this
    covers older pending points. The lookup happens at download time, so the
    live panorama IS the one in the image we just stored (unlike a later
    backfill, which has to guard against Google replacing the pano).
    """
    if img.capture_date is not None:
        return
    if lookup is None:
        from app.services.google_maps import google_maps_service
        lookup = google_maps_service.get_panorama_metadata
    try:
        if img.pano_id:
            meta = lookup(pano_id=img.pano_id)
        else:
            meta = lookup(img.latitude, img.longitude)
    except Exception as e:  # metadata is best-effort; never fail the download
        print(f"capture-date lookup failed for {img.id}: {e}")
        return
    if not meta:
        return
    img.capture_date = parse_capture_date(meta.get("date"))
    if not img.pano_id and meta.get("pano_id"):
        img.pano_id = meta["pano_id"]


def download_images(job_id: str):
    """Step 2: download images for points whose image_url is still an http(s) URL."""
    update_job(job_id, current_step=JobStep.DOWNLOADING, progress=30, total=100,
               message="Képek letöltése...")

    db = SessionLocal()
    try:
        pending_images = db.query(StreetViewImage).filter(
            StreetViewImage.image_url.like("http%")
        ).all()
        total = len(pending_images)
        print(f"DEBUG: Found {total} images to download.")

        if total == 0:
            update_job(job_id, progress=50, message="Nincs új letöltendő kép.")
            return

        downloaded_count = 0
        save_dir = os.path.join(settings.resolve_data_dir(), "images")
        os.makedirs(save_dir, exist_ok=True)

        for i, img in enumerate(pending_images):
            try:
                filename = f"sv_{img.id}_{uuid.uuid4().hex[:8]}.jpg"
                filepath = os.path.join(save_dir, filename)

                response = requests.get(img.image_url, stream=True, timeout=10)
                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        shutil.copyfileobj(response.raw, f)
                    img.image_url = f"images/{filename}"
                    downloaded_count += 1
                    fill_capture_metadata(img)
                else:
                    print(f"Failed to download {img.image_url}: {response.status_code}")
            except Exception as e:
                print(f"Error downloading image {img.id}: {e}")

            if i % 5 == 0:
                update_job(job_id, progress=30 + int((i / total) * 20),  # 30% -> 50%
                           message=f"Letöltés: {i + 1}/{total}")
                db.commit()  # periodic commit

        db.commit()
        update_job(job_id, progress=50, message=f"{downloaded_count} kép letöltve.")
    finally:
        db.close()
