import traceback
from app.core.timeutil import utcnow
from app.services.job_service import update_job, JobStatus

def refresh_road_segments(job_id: str, since=None) -> None:
    """Rebuild the road-segment layer after a job changed the frames.

    `since` given (route job): bbox-limited rebuild around the frames created
    from that moment on. `since=None` (analysis job): scores may have changed
    anywhere, so a full rebuild from the cached OSM data.

    Best effort by design: the segments are a derived view, so nothing here
    may fail the job. Without OSM data for a new area (Overpass unreachable)
    the refresh is logged and skipped; `scripts/build_segments.py` catches up.
    """
    try:
        from app.services import road_segments

        update_job(job_id, message="Útszakaszok frissítése...")
        if since is None:
            road_segments.refresh_segments_full()
        else:
            road_segments.refresh_segments_since(since)
    except Exception:
        print(f"Road-segment refresh skipped: {traceback.format_exc()}")


def run_route_processing(job_id: str, origin: str, destination: str,
                         path: list[tuple[float, float]] | None = None):
    """Run the full route processing pipeline using RouteProcessingService."""
    print(f"DEBUG: Process started for job {job_id}")
    started_at = utcnow()  # frames created from here on belong to this job
    try:
        from app.services.road_quality import road_quality_service
        from app.services.routing import routing_service
        import re

        print(f"DEBUG: Starting job {job_id} processing")
        update_job(job_id, status=JobStatus.RUNNING, message="Háttérfolyamat elindult...")
        
        # Helper to check if string is lat,lng
        def is_coordinate(s: str) -> bool:
            return bool(re.match(r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?$', s.strip()))

        # Geocode if necessary
        final_origin = origin
        final_dest = destination

        if path is None and not is_coordinate(origin):
            update_job(job_id, message=f"Cím feloldása: {origin}...")
            geocoded = routing_service.geocode(origin)
            if geocoded:
                final_origin = geocoded
                print(f"DEBUG: Geocoded origin '{origin}' to '{final_origin}'")
            else:
                print(f"WARNING: Could not geocode origin '{origin}', hoping it works as is.")

        if path is None and not is_coordinate(destination):
            update_job(job_id, message=f"Cím feloldása: {destination}...")
            geocoded = routing_service.geocode(destination)
            if geocoded:
                final_dest = geocoded
                print(f"DEBUG: Geocoded destination '{destination}' to '{final_dest}'")
            else:
                print(f"WARNING: Could not geocode destination '{destination}', hoping it works as is.")

        # One image allowance for the whole job (both passes); the monthly
        # quota is checked on top of it for every single image.
        from app.services.sv_quota import DEFAULT_JOB_CAP, JobBudget, cap_from_env
        budget = JobBudget(cap_from_env("GOOGLE_SV_JOB_CAP", DEFAULT_JOB_CAP))

        # Step 1: Collect points (first pass: one every 50 m)
        print(f"DEBUG: Calling collect_points for job {job_id}")
        if path is None:
            road_quality_service.collect_points(final_origin, final_dest, job_id)
        else:
            road_quality_service.collect_points(final_origin, final_dest, job_id, path=path)
        
        # Step 2: Download images
        print(f"DEBUG: Calling download_images for job {job_id}")
        road_quality_service.download_images(job_id=job_id, budget=budget)
        
        # Step 3: Analyze points.
        # YOLO gives damage polygons/types for the detail card; CLASSIFICATION
        # (frozen DINOv2 + trained ordinal head, see ml/) produces the RQI shown
        # on the map, regardless of the legacy rqi_display_source setting.
        print(f"DEBUG: Calling analyze_points (YOLO) for job {job_id}")
        road_quality_service.analyze_points(job_id=job_id, strategy="YOLO")
        print(f"DEBUG: Calling analyze_points (DINO CLASSIFICATION) for job {job_id}")
        road_quality_service.analyze_points(job_id=job_id, strategy="CLASSIFICATION")

        # Step 4: refresh the road-segment layer for the new area (best effort).
        refresh_road_segments(job_id, started_at)

        # Step 5: second pass — denser frames only where the segments came out
        # with low confidence, then score those and refresh once more.
        from app.services.sv_client import StreetViewFatal
        try:
            added = road_quality_service.densify_low_confidence(job_id, started_at, budget)
        except StreetViewFatal:
            raise  # quota / billing / key signal: the job must say so
        except Exception:
            # The second pass is an improvement, not a requirement.
            print(f"Second pass skipped: {traceback.format_exc()}")
            added = 0
        if added:
            print(f"DEBUG: second pass added {added} frames for job {job_id}")
            road_quality_service.analyze_points(job_id=job_id, strategy="YOLO")
            road_quality_service.analyze_points(job_id=job_id, strategy="CLASSIFICATION")
            refresh_road_segments(job_id, started_at)

        # Complete
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            message="Folyamat sikeresen befejezve",
            completed_at=utcnow(),
            result={"status": "success"}
        )

    except Exception as e:
        try:
            error_msg = str(e)
            print(f"Job failed with exception: {traceback.format_exc()}")
            update_job(
                job_id,
                status=JobStatus.FAILED,
                message=f"Hiba történt: {error_msg}",
                error=error_msg,
                completed_at=utcnow()
            )
        except Exception as update_error:
            print(f"CRITICAL: Failed to update job status after error: {update_error}")

def run_analysis_job(job_id: str, strategy: str, limit: int = 0, reanalyze: bool = False):
    """Run analysis job in background."""
    print(f"DEBUG: Analysis process started for job {job_id} (Strategy: {strategy})")
    try:
        from app.services.road_quality import road_quality_service
        
        update_job(job_id, status=JobStatus.RUNNING, message=f"Elemzés indítása ({strategy})...")
        
        result = road_quality_service.analyze_points(
            strategy=strategy, 
            limit=limit, 
            reanalyze=reanalyze, 
            job_id=job_id
        )
        
        if result.get("status") == "cancelled":
            print(f"DEBUG: Analysis job {job_id} was cancelled, not marking as completed.")
            return

        # New scores → refresh the derived road-segment layer (best effort).
        refresh_road_segments(job_id)

        strategy_used = result.get("strategy_used", strategy)
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            message=f"Elemzés sikeresen befejezve ({strategy_used})",
            completed_at=utcnow(),
            result={"status": "success", "counts": result}
        )

    except Exception as e:
        print(f"Analysis job failed: {traceback.format_exc()}")
        update_job(
            job_id,
            status=JobStatus.FAILED,
            message=f"Hiba az elemzés során: {str(e)}",
            error=str(e),
            completed_at=utcnow()
        )

def run_training_job(job_id: str):
    """Run YOLO model training in the background."""
    print(f"DEBUG: YOLO training process started for job {job_id}")
    try:
        from app.services.training_service import training_service
        
        update_job(job_id, status=JobStatus.RUNNING, message="YOLO modell finomhangolása indítása...")
        
        # Call the real training logic in training_service
        result = training_service.run_training(job_id)
        
        if result.get("status") == "cancelled":
            print(f"DEBUG: Training job {job_id} was cancelled, not marking as completed.")
            return

        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            message=result.get("message", "Modell finomhangolva és élesítve!"),
            completed_at=utcnow(),
            result=result
        )

    except Exception as e:
        print(f"Training job failed: {traceback.format_exc()}")
        update_job(
            job_id,
            status=JobStatus.FAILED,
            message=f"Hiba a tanítás során: {str(e)}",
            error=str(e),
            completed_at=utcnow()
        )
