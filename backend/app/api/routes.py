"""
API endpoints for web interface.
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.core.config import settings
from app.services.job_service import create_job, get_job, update_job, JobStatus, JobStep
from sqlalchemy import func
from pydantic import BaseModel
import threading
import time

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
            image_path = f"/api/v1/images/{filename}"
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
            image_path = f"/api/v1/images/{filename}"
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
    job_id = create_job()

    # Format coordinates as strings for CLI
    origin = f"{request.origin_lat},{request.origin_lng}"
    destination = f"{request.destination_lat},{request.destination_lng}"

    # Start background task in a separate thread
    thread = threading.Thread(
        target=run_route_processing, args=(job_id, origin, destination), daemon=True
    )
    thread.start()

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


def run_route_processing(job_id: str, origin: str, destination: str):
    """Run the full route processing pipeline using RouteProcessingService."""
    print(f"DEBUG: Thread started for job {job_id}")
    try:
        from app.services.processing_service import processing_service
        from app.services.job_service import update_job, JobStatus
        from datetime import datetime
        import traceback

        print(f"DEBUG: Starting job {job_id} processing")
        update_job(job_id, status=JobStatus.RUNNING, message="Háttérfolyamat elindult...")
        
        # Step 1: Collect points
        print(f"DEBUG: Calling collect_points for job {job_id}")
        processing_service.collect_points(origin, destination, job_id)
        
        # Step 2: Download images
        # Note: We download all pending images, not just for this route, 
        # as points are shared.
        print(f"DEBUG: Calling download_images for job {job_id}")
        processing_service.download_images(job_id=job_id)
        
        # Step 3: Analyze points
        # Analyze all downloaded images that haven't been analyzed yet
        print(f"DEBUG: Calling analyze_points for job {job_id}")
        processing_service.analyze_points(job_id=job_id, simple=True)
        
        # Complete
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            message="Folyamat sikeresen befejezve",
            completed_at=datetime.utcnow(),
            result={"status": "success"}
        )

    except Exception as e:
        # We need to import these here in case the outer imports failed
        try:
            from app.services.job_service import update_job, JobStatus
            from datetime import datetime
            import traceback
            
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


# Settings API endpoints

from app.core.settings_manager import settings_manager

class SettingResponse(PydanticBaseModel):
    key: str
    value: float
    description: Optional[str]
    example: Optional[str]
    category: Optional[str]

    class Config:
        from_attributes = True


class SettingUpdateRequest(PydanticBaseModel):
    value: float


@router.get("/api/v1/settings", response_model=List[SettingResponse])
async def get_settings():
    """Get all analysis settings."""
    return settings_manager.get_all_settings()


@router.get("/api/v1/settings/{key}", response_model=SettingResponse)
async def get_setting(key: str):
    """Get a specific setting by key."""
    all_settings = settings_manager.get_all_settings()
    for s in all_settings:
        if s.key == key:
            return s
            
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")


@router.put("/api/v1/settings/{key}", response_model=SettingResponse)
async def update_setting(
    key: str, request: SettingUpdateRequest
):
    """Update a setting value."""
    setting = settings_manager.update_setting(key, request.value)
    if not setting:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return setting
