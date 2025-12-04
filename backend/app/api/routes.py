from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Tuple, Dict
from sqlalchemy.orm import Session
from app.services.google_maps import google_maps_service
from app.core.database import get_db
from app.models.models import Route, StreetViewImage
from app.core.config import settings
from datetime import datetime

router = APIRouter()

class RouteRequest(BaseModel):
    origin: str
    destination: str

class ImageMetadata(BaseModel):
    latitude: float
    longitude: float
    heading: float
    pitch: float
    image_url: str

class RouteResponse(BaseModel):
    route_id: int
    total_points: int
    images: List[ImageMetadata]

@router.post("/generate-route", response_model=RouteResponse)
async def generate_route(request: RouteRequest, db: Session = Depends(get_db)):
    try:
        # 0. Check Quota (Simple implementation: count images created today)
        # In a real app, we'd query the DB for count of images created today
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = db.query(StreetViewImage).filter(StreetViewImage.captured_at >= today_start).count()
        
        if daily_count >= settings.DAILY_IMAGE_QUOTA:
             raise HTTPException(status_code=429, detail="Daily image quota exceeded")

        # 1. Get Route
        polyline = google_maps_service.get_route(request.origin, request.destination)
        if not polyline:
            raise HTTPException(status_code=404, detail="Route not found")
            
        # 2. Decode Polyline
        points = google_maps_service.decode_polyline(polyline)
        
        # 3. Interpolate
        dense_points = google_maps_service.interpolate_points(points, interval_meters=10.0)
        
        # 4. Generate Metadata
        images_metadata = google_maps_service.generate_street_view_metadata(dense_points)
        
        # 5. Save to DB
        # Create Route
        db_route = Route(
            origin=request.origin,
            destination=request.destination,
            path=f"LINESTRING({', '.join([f'{p[1]} {p[0]}' for p in dense_points])})" # PostGIS format: LON LAT
        )
        db.add(db_route)
        db.commit()
        db.refresh(db_route)
        
        # Create Images
        db_images = []
        for meta in images_metadata:
            db_img = StreetViewImage(
                route_id=db_route.id,
                latitude=meta['latitude'],
                longitude=meta['longitude'],
                heading=meta['heading'],
                pitch=meta['pitch'],
                image_url=meta['image_url'],
                location=f"POINT({meta['longitude']} {meta['latitude']})"
            )
            db_images.append(db_img)
        
        db.add_all(db_images)
        db.commit()
        
        return {
            "route_id": db_route.id,
            "total_points": len(images_metadata),
            "images": images_metadata
        }
        
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
