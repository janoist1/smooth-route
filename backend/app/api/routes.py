"""
API endpoints for web interface.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.core.config import settings
from sqlalchemy import func
from pydantic import BaseModel

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

@router.get("/api/v1/config")
async def get_config():
    """Get frontend configuration (Google Maps API key)."""
    return {
        "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY or ""
    }

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
