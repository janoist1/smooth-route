import threading
import traceback
from datetime import datetime
from app.services.job_service import update_job, JobStatus, create_job

def run_route_processing(job_id: str, origin: str, destination: str):
    """Run the full route processing pipeline using RouteProcessingService."""
    print(f"DEBUG: Process started for job {job_id}")
    try:
        from app.services.road_quality import road_quality_service
        from app.services.google_maps import google_maps_service
        import re

        print(f"DEBUG: Starting job {job_id} processing")
        update_job(job_id, status=JobStatus.RUNNING, message="Háttérfolyamat elindult...")
        
        # Helper to check if string is lat,lng
        def is_coordinate(s: str) -> bool:
            return bool(re.match(r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?$', s.strip()))

        # Geocode if necessary
        final_origin = origin
        final_dest = destination

        if not is_coordinate(origin):
            update_job(job_id, message=f"Cím feloldása: {origin}...")
            geocoded = google_maps_service.geocode(origin)
            if geocoded:
                final_origin = geocoded
                print(f"DEBUG: Geocoded origin '{origin}' to '{final_origin}'")
            else:
                print(f"WARNING: Could not geocode origin '{origin}', hoping it works as is.")

        if not is_coordinate(destination):
            update_job(job_id, message=f"Cím feloldása: {destination}...")
            geocoded = google_maps_service.geocode(destination)
            if geocoded:
                final_dest = geocoded
                print(f"DEBUG: Geocoded destination '{destination}' to '{final_dest}'")
            else:
                print(f"WARNING: Could not geocode destination '{destination}', hoping it works as is.")

        # Step 1: Collect points
        print(f"DEBUG: Calling collect_points for job {job_id}")
        road_quality_service.collect_points(final_origin, final_dest, job_id)
        
        # Step 2: Download images
        print(f"DEBUG: Calling download_images for job {job_id}")
        road_quality_service.download_images(job_id=job_id)
        
        # Step 3: Analyze points.
        # YOLO gives damage polygons/types for the detail card; CLASSIFICATION
        # (frozen DINOv2 + trained ordinal head, see ml/) produces the RQI shown
        # on the map (rqi_display_source defaults to "dino").
        print(f"DEBUG: Calling analyze_points (YOLO) for job {job_id}")
        road_quality_service.analyze_points(job_id=job_id, strategy="YOLO")
        print(f"DEBUG: Calling analyze_points (DINO CLASSIFICATION) for job {job_id}")
        road_quality_service.analyze_points(job_id=job_id, strategy="CLASSIFICATION")
        
        # Complete
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            message="Folyamat sikeresen befejezve",
            completed_at=datetime.utcnow(),
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
                completed_at=datetime.utcnow()
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

        strategy_used = result.get("strategy_used", strategy)
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            message=f"Elemzés sikeresen befejezve ({strategy_used})",
            completed_at=datetime.utcnow(),
            result={"status": "success", "counts": result}
        )

    except Exception as e:
        print(f"Analysis job failed: {traceback.format_exc()}")
        update_job(
            job_id,
            status=JobStatus.FAILED,
            message=f"Hiba az elemzés során: {str(e)}",
            error=str(e),
            completed_at=datetime.utcnow()
        )

def run_training_job(job_id: str, model_type: str = "YOLO"):
    """Run model training (YOLO or DINO) in background."""
    print(f"DEBUG: Training process started for job {job_id} (Type: {model_type})")
    try:
        from app.services.training_service import training_service
        
        update_job(job_id, status=JobStatus.RUNNING, message=f"{model_type} modell finomhangolása indítása...")
        
        # Call the real training logic in training_service
        result = training_service.run_training(job_id, model_type=model_type)
        
        if result.get("status") == "cancelled":
            print(f"DEBUG: Training job {job_id} was cancelled, not marking as completed.")
            return

        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            message=result.get("message", "Modell finomhangolva és élesítve!"),
            completed_at=datetime.utcnow(),
            result=result
        )

    except Exception as e:
        print(f"Training job failed: {traceback.format_exc()}")
        update_job(
            job_id,
            status=JobStatus.FAILED,
            message=f"Hiba a tanítás során: {str(e)}",
            error=str(e),
            completed_at=datetime.utcnow()
        )
