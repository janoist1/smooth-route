"""
Unified service for route processing logic (collection, download, analysis).
Used by both CLI and API to ensure consistency.
"""
import os
import time
import requests
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, not_
from geoalchemy2 import Geometry

from app.core.database import SessionLocal
from app.models.models import StreetViewImage
from app.core.config import settings
from app.services.google_maps import google_maps_service
from app.services.road_quality import road_quality_service
from app.services.job_service import update_job, JobStatus, JobStep

class RouteProcessingService:
    """Service handling the core logic for route processing pipeline."""
    
    def collect_points(self, origin: str, destination: str, job_id: Optional[str] = None) -> Dict[str, int]:
        """
        Collect road points along a route.
        
        Args:
            origin: Start location
            destination: End location
            job_id: Optional Job ID for progress updates
            
        Returns:
            Dict with 'new' and 'reused' counts.
        """
        if job_id:
            update_job(job_id, status=JobStatus.RUNNING, current_step=JobStep.COLLECTING, message="Pontok begyűjtése...")
            
        db = SessionLocal()
        try:
            # 1. Get Route
            if job_id:
                update_job(job_id, message="Útvonal keresése Google Maps-en...")
            
            polyline = google_maps_service.get_route(origin, destination)
            if not polyline:
                raise ValueError("Route not found")

            # 2. Decode & Interpolate
            if job_id:
                update_job(job_id, message="Útvonal feldolgozása és pontok interpolálása...")
                
            points = google_maps_service.decode_polyline(polyline)
            dense_points = google_maps_service.interpolate_points(points, interval_meters=10.0)
            
            # 3. Generate Metadata
            if job_id:
                update_job(job_id, message=f"{len(dense_points)} pont előkészítése...")
                
            images_metadata = google_maps_service.generate_street_view_metadata(dense_points)
            
            reused_count = 0
            new_count = 0
            total_points = len(images_metadata)
            
            for i, meta in enumerate(images_metadata):
                lat, lng = meta['latitude'], meta['longitude']
                heading = meta['heading']
                point_wkt = f"POINT({lng} {lat})"
                
                # Check for existing image within radius and heading tolerance
                # Use ST_DistanceSphere for approximate meters distance
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
                    # Create new point
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
                
                # Update progress periodically
                if job_id and ((i + 1) % 5 == 0 or i == total_points - 1):
                    # Small delay to allow DB/API polling if needed, but keep it fast
                    # time.sleep(0.01) 
                    update_job(
                        job_id,
                        progress=i + 1,
                        total=total_points,
                        message=f"Pontok begyűjtése: {i+1}/{total_points}"
                    )
            
            db.commit()
            
            result = {"new": new_count, "reused": reused_count, "total": total_points}
            
            if job_id:
                update_job(job_id, message=f"Pontok begyűjtve: {new_count} új, {reused_count} újrahasznosítva")
                
            return result
            
        finally:
            db.close()

    def download_images(self, output_dir: Optional[str] = None, limit: int = 0, job_id: Optional[str] = None) -> Dict[str, int]:
        """
        Download images for points that have URLs but no local files.
        
        Args:
            output_dir: Directory to save images (default: configured DATA_DIR/images)
            limit: Max number of images to download (0 = all)
            job_id: Optional Job ID for progress updates
            
        Returns:
            Dict with 'downloaded', 'skipped', 'errors' counts.
        """
        if job_id:
            update_job(job_id, current_step=JobStep.DOWNLOADING, message="Képek letöltése...")
            
        # Determine output directory (for saving files)
        images_dir = self._get_images_dir()
        if output_dir is not None:
            images_dir = output_dir
            
        os.makedirs(images_dir, exist_ok=True)
        
        db = SessionLocal()
        try:
            # Query points that need downloading (start with http)
            query = db.query(StreetViewImage).filter(
                StreetViewImage.image_url.like("http%")
            ).order_by(StreetViewImage.id)
            
            if limit > 0:
                query = query.limit(limit)
                
            images = query.all()
            total_images = len(images)
            
            if total_images == 0 and job_id:
                update_job(job_id, message="Nincs letöltendő kép.")
                return {"downloaded": 0, "skipped": 0, "errors": 0}

            downloaded = 0
            skipped = 0
            errors = 0
            
            for i, img in enumerate(images):
                try:
                    # Use consistent filename format
                    filename = f"{img.id:05d}_{img.latitude:.6f}_{img.longitude:.6f}_{int(img.heading)}.jpg"
                    filepath = os.path.join(images_dir, filename)
                    
                    # Check if file already exists
                    if os.path.exists(filepath):
                        skipped += 1
                        # Store RELATIVE path (just filename) for portability
                        img.image_url = f"images/{filename}"
                        continue
                    
                    # Download
                    response = requests.get(img.image_url, timeout=30)
                    if response.status_code == 200:
                        content_type = response.headers.get('content-type', '')
                        if 'image' in content_type:
                            with open(filepath, 'wb') as f:
                                f.write(response.content)
                            # Store RELATIVE path for portability
                            img.image_url = f"images/{filename}"
                            downloaded += 1
                        else:
                            errors += 1
                    else:
                        errors += 1
                        
                except Exception as e:
                    print(f"Error downloading image {img.id}: {e}")
                    errors += 1
                
                # Update progress
                if job_id and ((i + 1) % 5 == 0 or i == total_images - 1):
                    update_job(
                        job_id,
                        progress=i + 1,
                        total=total_images,
                        message=f"Képek letöltése: {downloaded} letöltve, {skipped} kihagyva"
                    )
            
            db.commit()
            
            result = {"downloaded": downloaded, "skipped": skipped, "errors": errors}
            
            if job_id:
                update_job(job_id, message=f"Képek letöltve: {downloaded} új, {skipped} már létezett")
                
            return result
            
        finally:
            db.close()

    def analyze_points(self, lat: Optional[float] = None, lng: Optional[float] = None, radius: float = 1000.0, 
                      limit: int = 0, simple: bool = False, job_id: Optional[str] = None) -> Dict[str, int]:
        """
        Analyze road points for quality.
        
        Args:
            lat, lng: Center point (optional)
            radius: Radius in meters (default 1000)
            limit: Max points to analyze
            simple: Use simple heuristic instead of full model
            job_id: Optional Job ID
            
        Returns:
            Dict with 'analyzed', 'errors' counts.
        """
        if job_id:
            update_job(job_id, current_step=JobStep.ANALYZING, message="Képek elemzése...")
            
        db = SessionLocal()
        try:
            images_dir = self._get_images_dir()
            
            # Build query - filter for LOCAL paths (not http URLs)
            # Matches: "images/xxx.jpg", "/app/data/images/xxx.jpg", "/Users/.../data/images/xxx.jpg"
            local_file_filter = not_(StreetViewImage.image_url.like("http%"))
            
            filters = [local_file_filter]
            
            if lat is not None and lng is not None:
                center_point = f"POINT({lng} {lat})"
                filters.append(
                    func.ST_DistanceSphere(
                        StreetViewImage.location,
                        func.ST_GeomFromText(center_point, 4326)
                    ) < radius
                )
                
            query = db.query(StreetViewImage).filter(*filters).order_by(StreetViewImage.id)
            
            if limit > 0:
                query = query.limit(limit)
                
            images = query.all()
            total_images = len(images)
            
            analyzed = 0
            errors = 0
            
            for i, img in enumerate(images):
                try:
                    # Resolve image path (handles relative, Docker, and local absolute paths)
                    image_path = self._resolve_image_path(img.image_url, images_dir)
                    
                    if not os.path.exists(image_path):
                        # File doesn't exist - count as error but continue
                        errors += 1
                        continue
                        
                    if simple:
                        result = road_quality_service.analyze_image_simple(image_path)
                    else:
                        result = road_quality_service.analyze_image(image_path)
                        
                    img.rqi_score = result.rqi_score
                    img.damage_count = result.damage_count
                    img.damage_types = result.damage_types
                    img.analysis_metadata = result.analysis_metadata
                    analyzed += 1
                    
                except Exception as e:
                    print(f"Error analyzing image {img.id}: {e}")
                    errors += 1
                
                # Update progress
                if job_id and ((i + 1) % 5 == 0 or i == total_images - 1):
                    update_job(
                        job_id,
                        progress=i + 1,
                        total=total_images,
                        message=f"Képek elemzése: {analyzed}/{total_images}"
                    )
            
            db.commit()
            
            result = {"analyzed": analyzed, "errors": errors, "total": total_images}
            
            if job_id:
                update_job(job_id, message=f"Elemzés kész: {analyzed} pont elemzve")
                
            return result
            
        finally:
            db.close()

    def _get_images_dir(self) -> str:
        """Get the absolute path to images directory, handling Docker/Local differences."""
        if os.path.exists('/app'):
            # Running in Docker
            return '/app/data/images'
        else:
            # Running locally - find project root (where data/ folder is)
            # settings.DATA_DIR is typically "data" (relative)
            data_dir = settings.DATA_DIR
            if not os.path.isabs(data_dir):
                # Go up from app/services/ to find project root
                current_file = os.path.abspath(__file__)  # .../app/services/processing_service.py
                app_dir = os.path.dirname(os.path.dirname(current_file))  # .../app
                backend_dir = os.path.dirname(app_dir)  # .../backend
                project_root = os.path.dirname(backend_dir)  # .../smooth-route
                data_dir = os.path.join(project_root, data_dir)
            return os.path.join(data_dir, "images")

    def _resolve_image_path(self, db_path: str, images_dir: str) -> str:
        """
        Resolve DB path to actual filesystem path.
        
        Handles:
        - Relative paths: "images/xxx.jpg" -> /full/path/to/images/xxx.jpg
        - Docker paths: "/app/data/images/xxx.jpg" -> local equivalent
        - Local paths: "/Users/.../data/images/xxx.jpg" -> Docker equivalent or direct
        """
        # If it's a relative path (our new format)
        if db_path.startswith("images/"):
            filename = db_path.replace("images/", "")
            return os.path.join(images_dir, filename)
        
        # If file exists at the exact path, use it directly
        if os.path.exists(db_path):
            return db_path
        
        # Handle absolute Docker paths when running locally
        if db_path.startswith('/app/data/images/'):
            filename = db_path.replace('/app/data/images/', '')
            return os.path.join(images_dir, filename)
        
        # Handle absolute local paths - extract filename and use images_dir
        if '/data/images/' in db_path:
            filename = db_path.split('/data/images/')[-1]
            return os.path.join(images_dir, filename)
        
        # Fallback: assume it's a filename and join with images_dir
        if not db_path.startswith('/'):
            return os.path.join(images_dir, db_path)
            
        return db_path

# Singleton instance
processing_service = RouteProcessingService()
