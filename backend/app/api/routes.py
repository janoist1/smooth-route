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
import asyncio

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
    image_url: Optional[str]
    image_path: Optional[str]  # Relative path for serving
    created_at: str
    
    class Config:
        from_attributes = True

@router.get("/api/v1/config")
async def get_config():
    """Get frontend configuration (Google Maps API key)."""
    return {
        "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY or ""
    }

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
        if point.image_url.startswith('/Users/') or point.image_url.startswith('/home/') or '/data/images/' in point.image_url:
            # Extract filename
            if '/data/images/' in point.image_url:
                filename = point.image_url.split('/data/images/')[-1]
                image_path = f"/api/v1/images/{filename}"
            elif os.path.exists(point.image_url):
                # Try to find relative path
                data_dir = settings.DATA_DIR
                if not os.path.isabs(data_dir):
                    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    project_root = os.path.dirname(backend_dir)
                    data_dir = os.path.join(project_root, data_dir)
                images_dir = os.path.join(data_dir, "images")
                if point.image_url.startswith(images_dir):
                    filename = os.path.basename(point.image_url)
                    image_path = f"/api/v1/images/{filename}"
        elif point.image_url.startswith('http'):
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
        image_url=point.image_url,
        image_path=image_path,
        created_at=point.created_at.isoformat() if point.created_at else ""
    )

@router.get("/api/v1/points", response_model=List[PointResponse])
async def get_points(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: float = 5000.0,
    db: Session = Depends(get_db)
):
    """
    Get road points with RQI scores.
    
    If lat/lng provided, returns points within radius.
    Otherwise returns all points.
    """
    if lat is not None and lng is not None:
        # Area-based query
        center_point = f"POINT({lng} {lat})"
        query = db.query(StreetViewImage).filter(
            func.ST_DistanceSphere(
                StreetViewImage.location,
                func.ST_GeomFromText(center_point, 4326)
            ) < radius
        ).order_by(StreetViewImage.id)
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
            rqi_score=p.rqi_score
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
    request: ProcessRouteRequest,
    background_tasks: BackgroundTasks
):
    """
    Start processing a route: collect points, download images, analyze.
    Returns a job ID for tracking progress.
    """
    job_id = create_job()
    
    # Format coordinates as strings for CLI
    origin = f"{request.origin_lat},{request.origin_lng}"
    destination = f"{request.destination_lat},{request.destination_lng}"
    
    # Start background task
    background_tasks.add_task(
        run_route_processing,
        job_id,
        origin,
        destination
    )
    
    return ProcessRouteResponse(
        job_id=job_id,
        status="pending",
        message="Job started"
    )

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
        "result": job.result
    }

async def run_route_processing(job_id: str, origin: str, destination: str):
    """Run the full route processing pipeline."""
    from app.services.google_maps import google_maps_service
    from app.services.road_quality import road_quality_service
    from app.models.models import StreetViewImage
    import os
    from sqlalchemy import func, or_
    from datetime import datetime
    
    try:
        update_job(job_id, status=JobStatus.RUNNING, current_step=JobStep.COLLECTING, message="Pontok begyűjtése...")
        
        # Step 1: Collect points
        db = SessionLocal()
        try:
            polyline = google_maps_service.get_route(origin, destination)
            if not polyline:
                raise ValueError("Route not found")
            
            points = google_maps_service.decode_polyline(polyline)
            dense_points = google_maps_service.interpolate_points(points, interval_meters=10.0)
            images_metadata = google_maps_service.generate_street_view_metadata(dense_points)
            
            reused_count = 0
            new_count = 0
            
            for i, meta in enumerate(images_metadata):
                lat, lng = meta['latitude'], meta['longitude']
                heading = meta['heading']
                point_wkt = f"POINT({lng} {lat})"
                
                existing_img = db.query(StreetViewImage).filter(
                    func.ST_DistanceSphere(
                        StreetViewImage.location,
                        func.ST_GeomFromText(point_wkt, 4326)
                    ) < settings.DEDUPLICATION_RADIUS_METERS,
                    func.abs(StreetViewImage.heading - heading) < settings.DEDUPLICATION_HEADING_TOLERANCE
                ).first()
                
                if existing_img:
                    reused_count += 1
                else:
                    new_img = StreetViewImage(
                        latitude=lat,
                        longitude=lng,
                        heading=heading,
                        pitch=meta['pitch'],
                        image_url=meta['image_url'],
                        location=point_wkt
                    )
                    db.add(new_img)
                    new_count += 1
                
                # Update progress
                update_job(job_id, progress=i+1, total=len(images_metadata), 
                          message=f"Pontok begyűjtése: {i+1}/{len(images_metadata)}")
            
            db.commit()
            update_job(job_id, message=f"Pontok begyűjtve: {new_count} új, {reused_count} újrahasznosítva")
        finally:
            db.close()
        
        # Step 2: Download images
        update_job(job_id, current_step=JobStep.DOWNLOADING, message="Képek letöltése...")
        
        db = SessionLocal()
        try:
            data_dir = settings.DATA_DIR
            if not os.path.isabs(data_dir):
                backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                project_root = os.path.dirname(backend_dir)
                data_dir = os.path.join(project_root, data_dir)
            
            output_dir = os.path.join(data_dir, "images")
            os.makedirs(output_dir, exist_ok=True)
            
            query = db.query(StreetViewImage).filter(
                StreetViewImage.image_url.like('http%')
            ).order_by(StreetViewImage.id)
            
            images = query.all()
            total_images = len(images)
            
            import requests
            downloaded = 0
            skipped = 0
            
            for i, img in enumerate(images):
                filename = f"{img.id:05d}_{img.latitude:.6f}_{img.longitude:.6f}_{int(img.heading)}.jpg"
                filepath = os.path.join(output_dir, filename)
                
                if os.path.exists(filepath):
                    skipped += 1
                    if img.image_url != filepath:
                        img.image_url = filepath
                    continue
                
                if not img.image_url or not (img.image_url.startswith('http://') or img.image_url.startswith('https://')):
                    skipped += 1
                    continue
                
                try:
                    response = requests.get(img.image_url, timeout=30)
                    if response.status_code == 200:
                        content_type = response.headers.get('content-type', '')
                        if 'image' in content_type:
                            with open(filepath, 'wb') as f:
                                f.write(response.content)
                            img.image_url = filepath
                            downloaded += 1
                except Exception as e:
                    pass  # Continue on error
                
                update_job(job_id, progress=i+1, total=total_images,
                          message=f"Képek letöltése: {downloaded} letöltve, {skipped} kihagyva")
            
            db.commit()
            update_job(job_id, message=f"Képek letöltve: {downloaded} új, {skipped} már létezett")
        finally:
            db.close()
        
        # Step 3: Analyze points
        update_job(job_id, current_step=JobStep.ANALYZING, message="Képek elemzése...")
        
        db = SessionLocal()
        try:
            images_dir = os.path.join(data_dir, "images")
            data_patterns = [
                f"%/data/images/%",
                f"{images_dir}%",
            ]
            
            query = db.query(StreetViewImage).filter(
                or_(*[StreetViewImage.image_url.like(pattern) for pattern in data_patterns])
            ).order_by(StreetViewImage.id)
            
            images = query.all()
            total_images = len(images)
            analyzed = 0
            
            for i, img in enumerate(images):
                image_path = img.image_url
                if image_path.startswith('/Users/') or image_path.startswith('/home/'):
                    if '/data/images/' in image_path:
                        rel_path = image_path.split('/data/images/')[-1]
                        image_path = os.path.join(images_dir, rel_path)
                
                if not os.path.exists(image_path):
                    continue
                
                try:
                    result = road_quality_service.analyze_image_simple(image_path)
                    img.rqi_score = result.rqi_score
                    analyzed += 1
                except Exception as e:
                    pass  # Continue on error
                
                update_job(job_id, progress=i+1, total=total_images,
                          message=f"Képek elemzése: {analyzed}/{total_images}")
            
            db.commit()
            update_job(job_id, message=f"Elemzés kész: {analyzed} pont elemzve")
        finally:
            db.close()
        
        # Complete
        from datetime import datetime
        update_job(job_id, status=JobStatus.COMPLETED, 
                  message="Folyamat sikeresen befejezve",
                  completed_at=datetime.utcnow(),
                  result={"analyzed_points": analyzed})
        
    except Exception as e:
        import traceback
        from datetime import datetime
        error_msg = str(e)
        update_job(job_id, status=JobStatus.FAILED, error=error_msg,
                  completed_at=datetime.utcnow(),
                  message=f"Hiba: {error_msg}")
