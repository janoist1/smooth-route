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
from app.services.job_service import update_job, get_job, JobStatus, JobStep

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

    def download_missing_images(self, output_dir: Optional[str] = None, limit: int = 0, job_id: Optional[str] = None) -> Dict[str, int]:
        """
        Check all points and download images that are missing from disk.
        Useful if records exist in DB but files were deleted or never successfully saved.
        """
        if job_id:
            update_job(job_id, current_step=JobStep.DOWNLOADING, message="Hiányzó képek ellenőrzése...")
            
        images_dir = self._get_images_dir()
        if output_dir is not None:
            images_dir = output_dir
            
        os.makedirs(images_dir, exist_ok=True)
        
        db = SessionLocal()
        try:
            # Query ALL points to check disk existence
            query = db.query(StreetViewImage).order_by(StreetViewImage.id)
            if limit > 0:
                query = query.limit(limit)
                
            images = query.all()
            total_count = len(images)
            
            downloaded = 0
            skipped = 0
            errors = 0
            
            for i, img in enumerate(images):
                try:
                    # Resolve expected filepath
                    filename = f"{img.id:05d}_{img.latitude:.6f}_{img.longitude:.6f}_{int(img.heading)}.jpg"
                    filepath = os.path.join(images_dir, filename)
                    
                    # Check if file exists
                    if os.path.exists(filepath):
                        skipped += 1
                        # Ensure DB points to this local path correctly if it was something else
                        expected_rel = f"images/{filename}"
                        if img.image_url != expected_rel:
                            img.image_url = expected_rel
                        continue
                    
                    # MISSING! Need to download.
                    # 1. Get or Generate URL
                    url = img.image_url
                    if not url or not url.startswith("http"):
                        # Regenerate URL using Google Maps Service
                        url = google_maps_service.get_street_view_url(
                            img.latitude, 
                            img.longitude, 
                            heading=img.heading,
                            pitch=img.pitch or 0.0
                        )
                    
                    # 2. Download
                    response = requests.get(url, timeout=30)
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
                    print(f"Error downloading missing image {img.id}: {e}")
                    errors += 1
                
                # Update progress
                if (i + 1) % 10 == 0 or i == total_count - 1:
                    if job_id:
                        update_job(
                            job_id,
                            progress=i + 1,
                            total=total_count,
                            message=f"Képek pótlása: {downloaded} letöltve, {skipped} rendben"
                        )
                    elif (i + 1) % 50 == 0:
                        print(f"Progress: {i+1}/{total_count} (Downloaded: {downloaded}, Skipped: {skipped})")
            
            db.commit()
            
            result = {"downloaded": downloaded, "skipped": skipped, "errors": errors}
            
            if job_id:
                update_job(job_id, message=f"Képek pótolva: {downloaded} letöltve, {errors} hiba")
                
            return result
            
        finally:
            db.close()

    def analyze_points(self, lat: Optional[float] = None, lng: Optional[float] = None, radius: float = 1000.0, 
                      limit: int = 0, strategy: str = "HEURISTIC", job_id: Optional[str] = None, reanalyze: bool = False) -> Dict[str, int]:
        """
        Analyze road points for quality using specified strategy.
        
        Args:
            lat, lng: Center point (optional)
            radius: Radius in meters (default 1000)
            limit: Max points to analyze
            strategy: Strategy to use: "HEURISTIC", "YOLO", or "FUSION"
            job_id: Optional Job ID
            reanalyze: If True, re-analyze points that already have RQI scores. Default False.
            
        Returns:
            Dict with 'analyzed', 'errors' counts.
        """
        if job_id:
            # Map LLM_V1 to YOLO for backward compatibility
            eff_strategy = "YOLO" if strategy == "LLM_V1" else strategy
            
            msg = "Képek elemzése..."
            if eff_strategy == "FUSION":
                msg = "Képek elemzése (Fusion mód)..."
            elif eff_strategy == "YOLO":
                msg = "Képek elemzése (YOLOv8)..."
            update_job(job_id, current_step=JobStep.ANALYZING, message=msg)
            
            # Update strategy for the rest of the logic
            strategy = eff_strategy
            
        db = SessionLocal()
        try:
            from app.models.models import TrainingData
            images_dir = self._get_images_dir()
            
            # Build query - filter for LOCAL paths (not http URLs)
            local_file_filter = not_(StreetViewImage.image_url.like("http%"))
            
            filters = [local_file_filter]
            
            # Filter out already analyzed images unless reanalyze is True
            if not reanalyze:
                filters.append(StreetViewImage.rqi_score.is_(None))
            
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
            
            if job_id:
                update_job(job_id, total=total_images, message=f"Feldolgozás megkezdése: {total_images} kép ({strategy})")

            if total_images == 0:
                return {"analyzed": 0, "errors": 0, "total": 0, "skipped_manual": 0, "strategy_used": strategy}

            analyzed = 0
            errors = 0
            skipped_manual = 0
            
            # Build filename -> TrainingData map for manual annotation checks
            # Note: For large datasets, this might be slow, but for training review it's manageable.
            # We only CARE about points that have manual annotations.
            trained_entries = db.query(TrainingData).filter(TrainingData.manual_rqi.isnot(None)).all()
            manual_map = {t.image_filename: t for t in trained_entries}
            
            for i, img in enumerate(images):
                # Check for cancellation every 5 images
                if job_id and i % 5 == 0:
                    try:
                        self._check_cancellation(job_id)
                    except StopIteration:
                        print(f"DEBUG: Job {job_id} cancelled during analysis.")
                        return {"analyzed": analyzed, "errors": errors, "total": total_images, "skipped_manual": skipped_manual, "status": "cancelled"}

                try:
                    # Resolve filename
                    fname = self._resolve_filename(img.image_url)
                    
                    # PROTECTION: If point has manual RQI, SKIP it!
                    if fname in manual_map:
                        skipped_manual += 1
                        continue

                    # Resolve image path
                    image_path = self._resolve_image_path(img.image_url, images_dir)
                    
                    if not os.path.exists(image_path):
                        errors += 1
                        continue
                        
                    if strategy == "HEURISTIC":
                        result = road_quality_service.analyze_image_simple(image_path)
                    elif strategy == "YOLO":
                        result = road_quality_service.analyze_image(image_path)
                    elif strategy == "FUSION":
                        # Run both and fuse results
                        h_res = road_quality_service.analyze_image_simple(image_path)
                        y_res = road_quality_service.analyze_image(image_path)
                        
                        # Fusion logic: weighted average of RQI
                        y_weight = 0.9 if y_res.damage_count > 0 else 0.7
                        h_weight = 1.0 - y_weight
                        
                        fused_rqi = (h_res.rqi_score * h_weight) + (y_res.rqi_score * y_weight)
                        
                        meta = h_res.analysis_metadata or {}
                        meta["fusion"] = {
                            "heuristic_rqi": h_res.rqi_score,
                            "yolo_rqi": y_res.rqi_score,
                            "yolo_damage_count": y_res.damage_count,
                            "yolo_detections": [
                                {"type": d.damage_type, "conf": d.confidence} 
                                for d in y_res.detections
                            ]
                        }
                        
                        from app.services.road_quality import RoadQualityResult
                        result = RoadQualityResult(
                            rqi_score=round(fused_rqi, 2),
                            damage_count=y_res.damage_count,
                            damage_types=y_res.damage_types,
                            detections=y_res.detections,
                            analysis_metadata=meta
                        )
                    else:
                        raise ValueError(f"Unknown strategy: {strategy}")
                        
                    img.rqi_score = result.rqi_score
                    img.damage_count = result.damage_count
                    img.damage_types = result.damage_types
                    img.analysis_metadata = result.analysis_metadata
                    analyzed += 1
                    
                except Exception as e:
                    print(f"Error analyzing image {img.id}: {e}")
                    errors += 1
                
                # Update progress
                if job_id and ((i + 1) % 10 == 0 or i == total_images - 1):
                    db.commit() # Commit periodically for SSE visibility
                    update_job(
                        job_id,
                        progress=i + 1,
                        total=total_images,
                        message=f"Elemzés ({strategy}): {i+1}/{total_images} kép kész"
                    )
            
            db.commit()
            
            print(f"DEBUG: analyze_points - finished. Analyzed: {analyzed}, Errors: {errors}, Skipped Manual: {skipped_manual}, Total Query: {total_images}")
            
            result_stats = {
                "analyzed": analyzed, 
                "errors": errors, 
                "total": total_images, 
                "skipped_manual": skipped_manual,
                "strategy_used": strategy
            }
            
            return result_stats
            
        finally:
            db.close()

    def run_training(self, job_id: str) -> Dict[str, Any]:
        """
        Export annotated data and run YOLO fine-tuning.
        """
        import shutil
        import yaml
        from PIL import Image
        from app.models.models import TrainingData
        from ultralytics import YOLO
        
        update_job(job_id, current_step=JobStep.TRAINING, message="Adatok előkészítése a tanításhoz...")
        
        db = SessionLocal()
        try:
            # 1. Fetch data
            annotated_data = db.query(TrainingData).all()
            if not annotated_data:
                raise ValueError("Nincs annotált adat a tanításhoz!")
            
            # Setup paths
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(backend_dir)
            train_dir = os.path.join(project_root, "data", "training")
            images_dir = self._get_images_dir()
            
            # Clean/Create training structure
            if os.path.exists(train_dir):
                shutil.rmtree(train_dir)
            
            os.makedirs(os.path.join(train_dir, "images"), exist_ok=True)
            os.makedirs(os.path.join(train_dir, "labels"), exist_ok=True)
            
            # Class mapping
            classes = ["long_crack", "trans_crack", "alligator_crack", "pothole", "patch", "cracks"]
            class_map = {
                "D00": 0, "longitudinal_crack": 0, "long_crack": 0,
                "D10": 1, "transverse_crack": 1, "trans_crack": 1,
                "D20": 2, "alligator_crack": 2,
                "D40": 3, "pothole": 3,
                "patch": 4, 
                "cracks": 5 # Generic cracks
            }
            
            exported_count = 0
            
            for i, td in enumerate(annotated_data):
                if job_id and i % 10 == 0:
                    try:
                        self._check_cancellation(job_id)
                    except StopIteration:
                        print(f"DEBUG: Job {job_id} cancelled during data prep.")
                        return {"status": "cancelled"}

                src_path = os.path.join(images_dir, td.image_filename)
                if not os.path.exists(src_path):
                    continue
                
                # Copy image
                dest_img_path = os.path.join(train_dir, "images", td.image_filename)
                shutil.copy(src_path, dest_img_path)
                
                # Generate labels
                label_filename = td.image_filename.rsplit('.', 1)[0] + ".txt"
                label_path = os.path.join(train_dir, "labels", label_filename)
                
                with open(label_path, 'w') as f:
                    # Get image size for normalization
                    with Image.open(src_path) as img:
                        w_img, h_img = img.size
                    
                    for ann in (td.annotations or []):
                        cls_name = ann.get('label', 'pothole')
                        cls_id = class_map.get(cls_name, 3) # default to pothole
                        
                        # Convert pixel coords to YOLO normalized format (cx, cy, w, h)
                        x, y, w, h = ann['x'], ann['y'], ann['w'], ann['h']
                        
                        cx = (x + w/2) / w_img
                        cy = (y + h/2) / h_img
                        nw = w / w_img
                        nh = h / h_img
                        
                        f.write(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")
                
                exported_count += 1
                if (i + 1) % 10 == 0:
                    db.commit() # Required for SSE visibility
                    update_job(job_id, progress=i+1, total=len(annotated_data), message=f"Adatok exportálása: {i+1}/{len(annotated_data)} kész")

            db.commit()
            update_job(job_id, progress=len(annotated_data), total=len(annotated_data), message=f"Adatok exportálása sikeres: {len(annotated_data)} kép")

            # 2. Create dataset.yaml
            dataset_config = {
                "path": train_dir,
                "train": "images",
                "val": "images", # Use same for now since we have small data
                "names": {i: name for i, name in enumerate(classes)}
            }
            
            with open(os.path.join(train_dir, "dataset.yaml"), 'w') as f:
                yaml.dump(dataset_config, f)
            
            # 3. RUN TRAINING
            update_job(job_id, progress=0.1, total=10, message="YOLO modell betöltése (ez eltarthat egy ideig)...")
            
            model = YOLO("yolov8m.pt")
            update_job(job_id, progress=0.2, total=10, message="YOLO inicializálása és tanítási környezet felépítése...")

            # Add callback for epoch progress
            def on_train_epoch_end(trainer):
                epoch = trainer.epoch + 1
                update_job(job_id, progress=epoch, total=10, message=f"Kész: Epoch {epoch}/10")
            
            # Add callback for more granular batch progress
            def on_train_batch_end(trainer):
                try:
                    # Defensive check for attributes
                    ni = getattr(trainer, 'ni', None)
                    nb = getattr(trainer, 'nb', None)
                    if nb is None and hasattr(trainer, 'train_loader'):
                        nb = len(trainer.train_loader)
                    
                    if ni is not None and nb:
                        current_batch = (ni % nb) + 1
                        # Update every 5 batches to avoid DB spam
                        if current_batch % 5 == 0:
                            epoch = getattr(trainer, 'epoch', 0) + 1
                            # Granular progress: epoch - 1 + (current_batch / total_batches)
                            # This makes the progress bar move smoothly between epochs
                            granular_progress = round(epoch - 1 + (current_batch / nb), 2)
                            update_job(
                                job_id, 
                                progress=granular_progress,
                                total=10,
                                message=f"Tanítás: Epoch {epoch}/10 | Batch {current_batch}/{nb}"
                            )
                except Exception as e:
                    # Don't let progress reporting crash the training
                    print(f"Warning: Progress callback failed: {e}")
            
            model.add_callback("on_train_epoch_end", on_train_epoch_end)
            model.add_callback("on_train_batch_end", on_train_batch_end)

            results = model.train(
                data=os.path.join(train_dir, "dataset.yaml"),
                epochs=10, # 10 epochs for faster training in demo
                imgsz=640,
                project=os.path.join(project_root, "data", "runs"),
                name="smooth_route_yolo",
                verbose=False,
                exist_ok=True # Overwrite previous runs
            )
            
            update_job(job_id, progress=10, total=10, message="Modell mentése és élesítése...")
            db.commit()
            
            # 4. Save final model
            best_model = os.path.join(project_root, "data", "runs", "smooth_route_yolo", "weights", "best.pt")
            final_dest = os.path.join(project_root, "data", "models", "trained_yolo.pt")
            os.makedirs(os.path.dirname(final_dest), exist_ok=True)
            shutil.copy(best_model, final_dest)
            
            return {"status": "success", "exported": exported_count, "model_path": final_dest}
            
        finally:
            db.close()

    def _check_cancellation(self, job_id: Optional[str]):
        """Check if the job has been cancelled and raise an exception if so."""
        if not job_id:
            return
        
        # We don't want to query DB too often, but for these loops once every 5-10 items is fine
        job = get_job(job_id)
        if job and job.status == JobStatus.CANCELLED:
            raise StopIteration("Job cancelled by user")

    def _resolve_filename(self, path: str) -> str:
        """Extract filename from any path format."""
        if not path: return ""
        if path.startswith("images/"): return path.replace("images/", "")
        if "/data/images/" in path: return path.split("/data/images/")[-1]
        return os.path.basename(path)

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
