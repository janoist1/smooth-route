"""
Image download: fetch the actual Street View JPEGs for pending points and
rewrite their image_url to the local path.
"""
import datetime as dt
import os
import uuid
from typing import Any, Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.services.capture_date import parse_capture_date
from app.services.job_service import JobStep, update_job
from app.services.sv_client import StreetViewError, StreetViewFatal, default_client
from app.services.sv_quota import DEFAULT_JOB_CAP, JobBudget, QuotaExceeded, cap_from_env


def get_capture_metadata(img: Any, lookup=None) -> tuple[str, Optional[dt.date]]:
    """Resolve the exact panorama before fetching its image.

    Stored ids never fall back to a location lookup. Legacy rows without an
    id first resolve one by position, then download that id. A missing date
    stays unknown; a failed or mismatched lookup must leave the row queued.
    """
    if lookup is None:
        lookup = default_client().metadata
    if img.pano_id:
        meta = lookup(pano_id=img.pano_id)
    else:
        if img.latitude is None or img.longitude is None:
            raise StreetViewError("Street View metadata: no panorama id or position")
        meta = lookup(img.latitude, img.longitude)
    meta = meta or {}
    pano_id = meta.get("pano_id")
    if not isinstance(pano_id, str) or not pano_id:
        raise StreetViewError("Street View metadata: panorama unavailable")
    if img.pano_id and pano_id != img.pano_id:
        raise StreetViewError("Street View metadata: panorama id mismatch")
    return pano_id, parse_capture_date(meta.get("date"))


def download_images(job_id: str, budget: Optional[JobBudget] = None):
    """Step 2: download images for points whose image_url is still an http(s) URL.

    ``budget`` is the job's image allowance; pass the same object to every
    step of a job so the per-job cap covers the job as a whole."""
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

        # Every image goes through the shared client: booked on the monthly
        # quota counter and this job's own cap BEFORE it is requested, paced
        # at the steady rate, and a quota / billing signal ends the job.
        client = default_client()
        if budget is None:
            budget = JobBudget(cap_from_env("GOOGLE_SV_JOB_CAP", DEFAULT_JOB_CAP))
        stop_reason = None

        img: Any  # ORM row: legacy Column models type as Column[...] (see DEVELOPMENT.md)
        for i, img in enumerate(pending_images):
            try:
                pano_id, capture_date = get_capture_metadata(img, lookup=client.metadata)
                body = client.image_from_url(img.image_url, job=budget, pano_id=pano_id)
            except (QuotaExceeded, StreetViewFatal) as stop:
                stop_reason = str(stop)
                break
            except StreetViewError as e:
                # Never print the stored URL: it carries the API key.
                print(f"Image for point {img.id} skipped: {e}")
            except Exception as e:
                print(f"Error downloading image {img.id}: {type(e).__name__}")
            else:
                filename = f"sv_{img.id}_{uuid.uuid4().hex[:8]}.jpg"
                with open(os.path.join(save_dir, filename), 'wb') as f:
                    f.write(body)
                img.image_url = f"images/{filename}"
                img.pano_id = pano_id
                img.capture_date = capture_date
                downloaded_count += 1

            if i % 5 == 0:
                update_job(job_id, progress=30 + int((i / total) * 20),  # 30% -> 50%
                           message=f"Letöltés: {i + 1}/{total}")
                db.commit()  # periodic commit

        db.commit()
        if stop_reason:
            # Points not fetched keep their queued URL, so a later job resumes
            # exactly where this one stopped.
            raise RuntimeError(
                f"Street View download stopped after {downloaded_count} of {total} images: "
                f"{stop_reason}"
            )
        update_job(job_id, progress=50, message=f"{downloaded_count} kép letöltve.")
    finally:
        db.close()
