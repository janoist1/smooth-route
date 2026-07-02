"""
API endpoints for web interface.
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.core.config import settings
from app.services.job_service import create_job, get_job, update_job, get_active_job, JobStatus, JobStep
from sqlalchemy import func
from pydantic import BaseModel
import threading
import time
import asyncio
import json
from sse_starlette.sse import EventSourceResponse

# Alias for clarity
PydanticBaseModel = BaseModel

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PointResponse(BaseModel):
    id: int
    latitude: float
    longitude: float
    heading: float
    rqi_score: Optional[float]

    class Config:
        from_attributes = True


class PointDetailResponse(BaseModel):
    id: int
    latitude: float
    longitude: float
    heading: float
    pitch: Optional[float]
    rqi_score: Optional[float]
    damage_count: int
    damage_types: Optional[dict]
    analysis_metadata: Optional[dict]  # Detailed analysis info
    image_url: Optional[str]
    image_path: Optional[str]  # Relative path for serving
    created_at: str

    class Config:
        from_attributes = True


@router.get("/api/v1/config")
async def get_config():
    """Get frontend configuration (Google Maps API key)."""
    return {"google_maps_api_key": settings.GOOGLE_MAPS_API_KEY or ""}


@router.get("/api/v1/points/{point_id}", response_model=PointDetailResponse)
async def get_point_detail(point_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific point."""
    import os

    point = db.query(StreetViewImage).filter(StreetViewImage.id == point_id).first()
    if not point:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Point not found")

    # Convert image path to relative URL if it's a local file
    image_path = None
    if point.image_url:
        # Handle new relative format: images/xxx.jpg
        if point.image_url.startswith("images/"):
            filename = point.image_url.replace("images/", "")
            image_path = f"/images/{filename}"
        elif (
            point.image_url.startswith("/Users/")
            or point.image_url.startswith("/home/")
            or point.image_url.startswith("/app/")
            or "/data/images/" in point.image_url
        ):
            # Extract filename from absolute paths
            if "/data/images/" in point.image_url:
                filename = point.image_url.split("/data/images/")[-1]
            else:
                filename = os.path.basename(point.image_url)
            image_path = f"/images/{filename}"
        elif point.image_url.startswith("http"):
            image_path = point.image_url

    return PointDetailResponse(
        id=point.id,
        latitude=point.latitude,
        longitude=point.longitude,
        heading=point.heading,
        pitch=point.pitch,
        rqi_score=point.rqi_score,
        damage_count=point.damage_count or 0,
        damage_types=point.damage_types,
        analysis_metadata=point.analysis_metadata,
        image_url=point.image_url,
        image_path=image_path,
        created_at=point.created_at.isoformat() if point.created_at else "",
    )


@router.get("/api/v1/points", response_model=List[PointResponse])
async def get_points(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: float = 5000.0,
    db: Session = Depends(get_db),
):
    """
    Get road points with RQI scores.

    If lat/lng provided, returns points within radius.
    Otherwise returns all points.
    """
    if lat is not None and lng is not None:
        # Area-based query
        center_point = f"POINT({lng} {lat})"
        query = (
            db.query(StreetViewImage)
            .filter(
                func.ST_DistanceSphere(
                    StreetViewImage.location, func.ST_GeomFromText(center_point, 4326)
                )
                < radius
            )
            .order_by(StreetViewImage.id)
        )
    else:
        # All points
        query = db.query(StreetViewImage).order_by(StreetViewImage.id)

    points = query.all()

    return [
        PointResponse(
            id=p.id,
            latitude=p.latitude,
            longitude=p.longitude,
            heading=p.heading,
            rqi_score=p.rqi_score,
        )
        for p in points
    ]


class ProcessRouteRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float


class ProcessRouteResponse(BaseModel):
    job_id: str
    status: str
    message: str


@router.post("/api/v1/process-route", response_model=ProcessRouteResponse)
async def process_route(
    request: ProcessRouteRequest, background_tasks: BackgroundTasks
):
    """
    Start processing a route: collect points, download images, analyze.
    Returns a job ID for tracking progress.
    """
    from app.services.job_runner import job_runner
    from app.services.tasks import run_route_processing

    job_id = create_job()

    # Format coordinates as strings for CLI
    origin = f"{request.origin_lat},{request.origin_lng}"
    destination = f"{request.destination_lat},{request.destination_lng}"

    # Start background task
    job_runner.run_background_task(
        target=run_route_processing, 
        args=(job_id, origin, destination)
    )

    return ProcessRouteResponse(job_id=job_id, status="pending", message="Job started")


@router.get("/api/v1/job/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and progress."""
    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}

    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "current_step": job.current_step.value if job.current_step else None,
        "progress": job.progress,
        "total": job.total,
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "result": job.result,
    }


@router.get("/api/v1/job/{job_id}/stream")
async def stream_job_status(job_id: str):
    """Stream job status and progress using SSE."""

    async def event_generator():
        last_progress = -1
        last_status = None

        while True:
            job = get_job(job_id)
            if not job:
                yield {"event": "error", "data": "Job not found"}
                break

            # Only send update if something changed
            if job.progress != last_progress or job.status != last_status:
                last_progress = job.progress
                last_status = job.status

                yield {
                    "data": json.dumps(
                        {
                            "job_id": job.job_id,
                            "status": job.status.value,
                            "current_step": job.current_step.value
                            if job.current_step
                            else None,
                            "progress": job.progress,
                            "total": job.total,
                            "message": job.message,
                            "error": job.error,
                            "result": job.result,
                        }
                    )
                }

            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break

            await asyncio.sleep(0.1)  # Faster heartbeat for rapid tasks

    return EventSourceResponse(event_generator())


@router.post("/api/v1/job/{job_id}/stop")
async def stop_job(job_id: str):
    """Stop/cancel a running job."""
    job = get_job(job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        return {"status": "already_stopped", "message": f"Job is already {job.status}"}
    
    update_job(job_id, status=JobStatus.CANCELLED, message="Folyamat leállítva a felhasználó által.")
    return {"status": "stopped", "message": "Stopping job..."}


@router.get("/api/v1/jobs/active")
async def get_current_active_job():
    """Get the currently active job (for reconnection)."""
    job = get_active_job()
    if not job:
        return {"job": None}
    
    return {
        "job": {
            "job_id": job.job_id,
            "status": job.status.value,
            "current_step": job.current_step.value if job.current_step else None,
            "progress": job.progress,
            "total": job.total,
            "message": job.message,
            "error": job.error,
            "result": job.result
        }
    }






class DetectRequest(BaseModel):
    filename: str
    conf_threshold: float = 0.25


@router.post("/api/v1/inference/detect")
async def detect_objects(request: DetectRequest):
    """
    Run YOLO inference on a specific image and return polygons.
    """
    from app.services.inference import inference_service
    import os
    from fastapi import HTTPException
    
    # Resolve image path with fallbacks
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    project_root = os.path.dirname(backend_dir)
    
    candidates = [
        settings.resolve_data_dir(),
        os.path.join(project_root, "data"),
        os.path.join(backend_dir, "data")
    ]
    
    image_path = None
    for base_dir in candidates:
        cand = os.path.join(base_dir, "images", request.filename)
        if os.path.exists(cand):
             image_path = cand
             break
             
    if not image_path:
        raise HTTPException(status_code=404, detail=f"Image {request.filename} not found")
        
    try:
        # Run inference (cpu/gpu auto-selected by ultralytics)
        predictions = inference_service.detect_objects(image_path, request.conf_threshold)
        return {"predictions": predictions}
    except Exception as e:
        print(f"Inference error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
