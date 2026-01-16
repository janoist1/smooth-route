"""
Road Quality Analysis Service using YOLO for damage detection.
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import json
import cv2
import numpy as np
import shutil
import yaml
import random
import os
import requests
from ultralytics import YOLO
from datetime import datetime
import torch

from app.services.job_service import update_job, JobStep, JobStatus
from app.core.database import SessionLocal, engine
from app.models.models import StreetViewImage, Job, TrainingData
from app.core.config import settings
from app.services.google_maps import google_maps_service
import uuid
from pathlib import Path


@dataclass
class DamageDetection:
    """Represents a detected road damage."""

    damage_type: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    area: float  # Relative area (0-1)


@dataclass
class RoadQualityResult:
    """Result of road quality analysis."""

    rqi_score: float  # 1-5 scale
    damage_count: int
    damage_types: Dict[str, int]  # {type: count}
    detections: List[DamageDetection]
    # Detailed analysis metadata (for simple analysis)
    analysis_metadata: Optional[Dict] = (
        None  # Contains edge_density, variance, damage_score, etc.
    )


class RoadQualityService:
    """Service for analyzing road quality from Street View images."""

    # Pipeline 2.0 Taxonomy
    DAMAGE_CLASSES = {
        0: "long_crack",
        1: "trans_crack",
        2: "alligator_crack",
        3: "pothole",
        4: "patch",
        5: "degradation",
        6: "shadow",
        7: "manhole",
        8: "marking"
    }

    DAMAGE_NAMES = {
        "long_crack": "Longitudinal Crack",
        "trans_crack": "Transverse Crack",
        "alligator_crack": "Alligator Crack",
        "pothole": "Pothole",
        "patch": "Asphalt Patch",
        "degradation": "Surface Degradation",
        "shadow": "Shadow",
        "manhole": "Manhole",
        "marking": "Road Marking"
    }



    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize the service.

        Args:
            model_path: Path to custom YOLO model. If None, uses pre-trained RDD model.
        """
        self.model = None
        self.model_path = model_path
        self._loaded = False

    def _get_setting(self, key: str, default: float) -> float:
        """Get a setting value from file-based SettingsManager."""
        from app.core.settings_manager import settings_manager
        return settings_manager.get_setting(key, default)




    def _load_model(self):
        """Lazy load or reload the YOLO model if settings changed."""
        from app.core.settings_manager import settings_manager
        target_model = settings_manager.get_setting("ai_model", "yolov12s-seg.pt")
        
        # Determine actual path if it's just a filename
        actual_model_path = target_model
        if not os.path.isabs(target_model):
            project_root = os.getcwd()
            cand = os.path.join(project_root, "data", "models", target_model)
            if os.path.exists(cand):
                actual_model_path = cand
        
        # Skip if already loaded same model
        if hasattr(self, 'current_model_path') and self.current_model_path == actual_model_path and self._loaded:
            return

        from ultralytics import YOLO
        print(f"RoadQualityService: Loading YOLO model from {actual_model_path}...")
        
        try:
            self.model = YOLO(actual_model_path)
            self._loaded = True
            self.current_model_path = actual_model_path
            
            # Check if it's a segmentation model
            self.is_segmentation = hasattr(self.model, 'task') and self.model.task == 'segment'
            print(f"Model loaded. Task: {self.model.task if hasattr(self.model, 'task') else 'unknown'}. Device: {self.model.device}")
        except Exception as e:
            print(f"Error loading model {actual_model_path}: {e}")
            if not hasattr(self, 'model'):
                self.model = YOLO("yolov8m-seg.pt") # Final fallback
                self._loaded = True

    def analyze_image(
        self, image_path: str, confidence_threshold: Optional[float] = None
    ) -> RoadQualityResult:
        """
        Analyze a single image for road damage using Segmentation and ROI masking.
        """
        import numpy as np
        import cv2
        self._load_model()
        
        if confidence_threshold is None:
            confidence_threshold = self._get_setting("ai_inference_conf", 0.25)

        # Run inference
        results = self.model(image_path, conf=confidence_threshold, verbose=False)

        # Process detections
        detections = []
        damage_counts: Dict[str, int] = {}
        total_damage_pixels = 0
        
        # Define classes (Must match processing_service taxonomy)
        classes = ["long_crack", "trans_crack", "alligator_crack", "pothole", "patch", "degradation", "shadow", "manhole", "marking"]

        img_h, img_w = 0, 0
        roi_area_pixels = 0
        roi_mask = None

        for result in results:
            img_h, img_w = result.orig_shape
            
            # ROI Mask (trapezoid like in processing_service)
            roi_mask = np.zeros((img_h, img_w), dtype=np.uint8)
            mask_poly = np.array([
                [img_w * 0.1, img_h],      # Bottom-left
                [img_w * 0.9, img_h],      # Bottom-right
                [img_w * 0.65, img_h * 0.5],# Top-right
                [img_w * 0.35, img_h * 0.5] # Top-left
            ], dtype=np.int32)
            cv2.fillPoly(roi_mask, [mask_poly], 255)
            roi_area_pixels = np.sum(roi_mask > 0)

            # Segmentation Masks
            if hasattr(result, 'masks') and result.masks is not None:
                for i, mask_obj in enumerate(result.masks.data):
                    conf = float(result.boxes.conf[i])
                    cls_id = int(result.boxes.cls[i])
                    label = classes[cls_id] if cls_id < len(classes) else "unknown"
                    
                    # Convert mask to numpy and resize to original image
                    mask = mask_obj.cpu().numpy()
                    mask = cv2.resize(mask, (img_w, img_h))
                    
                    # Apply ROI: damage must be on the road
                    effective_mask = cv2.bitwise_and(mask, mask, mask=roi_mask)
                    damage_pixels = np.sum(effective_mask > 0.5)
                    
                    if damage_pixels > 0:
                        rel_area = damage_pixels / roi_area_pixels
                        
                        # Get bounding box for the detection object
                        x1, y1, x2, y2 = result.boxes.xyxy[i].tolist()
                        
                        detections.append(
                            DamageDetection(
                                damage_type=label,
                                confidence=conf,
                                bbox=(x1, y1, x2, y2),
                                area=rel_area,
                            )
                        )
                        
                        # Weight pixel count for RQI
                        # Negative classes (shadow, manhole, marking) don't count towards damage
                        if cls_id <= 5: # long_crack to degradation
                            total_damage_pixels += damage_pixels
                            damage_counts[label] = damage_counts.get(label, 0) + 1

            elif result.boxes is not None:
                # Fallback to Bounding Boxes
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    label = classes[cls_id] if cls_id < len(classes) else "unknown"

                    cx, cy = (x1+x2)/2, (y1+y2)/2
                    if cy > img_h * 0.5:
                        box_area = (x2-x1) * (y2-y1)
                        rel_area = box_area / (img_h * img_w)
                        
                        detections.append(
                            DamageDetection(
                                damage_type=label,
                                confidence=conf,
                                bbox=(x1, y1, x2, y2),
                                area=rel_area,
                            )
                        )
                        if cls_id <= 5:
                            damage_counts[label] = damage_counts.get(label, 0) + 1

        # Updated RQI calculation
        total_damage_percent = (total_damage_pixels / roi_area_pixels) * 100 if roi_area_pixels > 0 else 0
        
        if total_damage_percent < 0.5: rqi_score = 1.0
        elif total_damage_percent < 2.0: rqi_score = 2.0
        elif total_damage_percent < 5.0: rqi_score = 3.0
        elif total_damage_percent < 10.0: rqi_score = 4.0
        else: rqi_score = 5.0

        return RoadQualityResult(
            rqi_score=rqi_score,
            damage_count=len(damage_counts),
            damage_types=damage_counts,
            detections=detections,
            analysis_metadata={"damage_percent": round(total_damage_percent, 2)}
        )




    # workflow methods required by routes.py
    
    def collect_points(self, origin: str, destination: str, job_id: str):
        """Step 1: Collect points along the route."""
        from app.services.job_service import update_job, JobStep
        from app.models.models import StreetViewImage
        from app.core.database import SessionLocal
        from sqlalchemy import func
        
        update_job(job_id, current_step= JobStep.COLLECTING, progress=0, total=100, message="Útvonal lekérése...")
        print(f"DEBUG: Collecting points from {origin} to {destination}")
        
        try:
            # 1. Get raw route points
            route_points_dicts = google_maps_service.get_route(origin, destination)
            if not route_points_dicts:
                print("No route found.")
                return

            # Convert to tuples for interpolation
            route_tuples = [(p['lat'], p['lng']) for p in route_points_dicts]
            
            update_job(job_id, progress=10, message=f"Útvonalpontok feldolgozása ({len(route_tuples)})...")

            # 2. Interpolate (every ~10 meters - closer)
            interpolated = google_maps_service.interpolate_points(route_tuples, interval_meters=10.0)
            
            update_job(job_id, progress=20, message=f"Street View metaadatok generálása ({len(interpolated)} pont)...")
            
            # 3. Generate Metadata (calculate heading)
            metadata_list = google_maps_service.generate_street_view_metadata(interpolated)
            
            # 4. Save to DB
            db = SessionLocal()
            saved_count = 0
            try:
                total_meta = len(metadata_list)
                for i, meta in enumerate(metadata_list):
                    # Check for existing point nearby (within 5 meters)
                    # uses simple distance query to prevent duplicates
                    point_geom = f"POINT({meta['longitude']} {meta['latitude']})"
                    exists = db.query(StreetViewImage).filter(
                        func.ST_DistanceSphere(
                            StreetViewImage.location, func.ST_GeomFromText(point_geom, 4326)
                        ) < 5.0
                    ).first()
                    
                    if not exists:
                        new_point = StreetViewImage(
                            latitude=meta['latitude'],
                            longitude=meta['longitude'],
                            heading=meta['heading'],
                            pitch=meta['pitch'],
                            image_url=meta['image_url'],
                            rqi_score=None # Pending analysis
                        )
                        db.add(new_point)
                        saved_count += 1
                    
                    if i % 20 == 0:
                        db.commit() # Periodic commit
                        prog = 20 + int((i / total_meta) * 10) # 20% -> 30%
                        update_job(job_id, progress=prog)
                
                db.commit()
                print(f"DEBUG: Saved {saved_count} new points.")
                update_job(job_id, progress=30, message=f"{saved_count} új mérési pont rögzítve.")
                
            finally:
                db.close()

        except Exception as e:
            print(f"Error collecting points: {e}")
            raise e
        
    def download_images(self, job_id: str):
        """Step 2: Download images for pending points."""
        from app.services.job_service import update_job, JobStep
        from app.models.models import StreetViewImage
        from app.core.database import SessionLocal
        import requests
        import os
        
        update_job(job_id, current_step=JobStep.DOWNLOADING, progress=30, total=100, message="Képek letöltése...")
        
        db = SessionLocal()
        try:
            # Find images with HTTP/HTTPS url (not local)
            pending_images = db.query(StreetViewImage).filter(StreetViewImage.image_url.like("http%")).all()
            total = len(pending_images)
            print(f"DEBUG: Found {total} images to download.")
            
            if total == 0:
                 update_job(job_id, progress=50, message="Nincs új letöltendő kép.")
                 return

            downloaded_count = 0
            
            # Ensure directory exists
            # Ensure directory exists
            data_dir = settings.resolve_data_dir()
            save_dir = os.path.join(data_dir, "images")
            
            os.makedirs(save_dir, exist_ok=True)

            for i, img in enumerate(pending_images):
                try:
                    # Generic filename using ID or UUID
                    filename = f"sv_{img.id}_{uuid.uuid4().hex[:8]}.jpg"
                    filepath = os.path.join(save_dir, filename)
                    
                    response = requests.get(img.image_url, stream=True, timeout=10)
                    if response.status_code == 200:
                        with open(filepath, 'wb') as f:
                            shutil.copyfileobj(response.raw, f)
                        
                        # Update DB record
                        img.image_url = f"images/{filename}"
                        downloaded_count += 1
                    else:
                        print(f"Failed to download {img.image_url}: {response.status_code}")
                
                except Exception as e:
                    print(f"Error downloading image {img.id}: {e}")
                
                # Update progress
                if i % 5 == 0:
                    prog = 30 + int((i / total) * 20) # 30% -> 50%
                    update_job(job_id, progress=prog, message=f"Letöltés: {i+1}/{total}")
                    db.commit() # Periodic commit

            db.commit()
            update_job(job_id, progress=50, message=f"{downloaded_count} kép letöltve.")
            
        finally:
            db.close()

    def analyze_points(
        self, 
        job_id: str = None, 
        strategy: str = "HEURISTIC", 
        limit: int = 0, 
        reanalyze: bool = False
    ) -> Dict:
        """Step 3: Analyze points using selected strategy."""
        from app.services.job_service import update_job, JobStep
        if job_id:
             update_job(job_id, current_step=JobStep.ANALYZING, progress=50, total=100, message=f"Elemzés futtatása ({strategy})...")
             
        print(f"DEBUG: Analyzing points with strategy {strategy}")
        
        # Real analysis logic: iterate over images in DB
        from app.core.database import SessionLocal
        from app.models.models import StreetViewImage
        import os
        
        db = SessionLocal()
        try:
            query = db.query(StreetViewImage)
            if not reanalyze:
                query = query.filter(StreetViewImage.rqi_score == None)
                
            images = query.limit(limit).all() if limit > 0 else query.all()
            total = len(images)
            analyzed_count = 0
            
            for i, img in enumerate(images):
                 if job_id:
                     # Update progress periodically
                     if i % 5 == 0:
                         prog_percent = 50 + int((i / total) * 49) # Go up to 99%
                         update_job(job_id, progress=prog_percent)
                         
                 # Construct absolute path
                 # Assuming relative path in DB or just filename
                 # This logic needs to match how routes.py expects paths
                 # Using basic heuristic for now
                 if img.image_url:
                     if img.image_url.startswith("images/"):
                         fname = img.image_url.replace("images/", "")
                     else:
                         fname = os.path.basename(img.image_url)
                         
                     # Try to find file using centralized logic
                     data_dir = settings.resolve_data_dir()
                     path = os.path.join(data_dir, "images", fname)
                     
                     if not os.path.exists(path):
                         # Fallback check for legacy data
                         services_dir = os.path.dirname(os.path.abspath(__file__))
                         app_dir = os.path.dirname(services_dir)
                         backend_dir = os.path.dirname(app_dir)
                         project_root = os.path.dirname(backend_dir)
                         legacy_path = os.path.join(project_root, "data", "images", fname)
                         if os.path.exists(legacy_path):
                             path = legacy_path
                         
                     if not os.path.exists(path):
                         # Try alternate
                         path = os.path.join(os.getcwd(), "data", "images", fname)
                         
                     if os.path.exists(path):
                         # Run analysis (Force YOLO as per user request)
                         result = self.analyze_image(path)
                             
                         # Save result
                         img.rqi_score = result.rqi_score
                         img.damage_count = result.damage_count
                         img.damage_types = result.damage_types
                         img.analysis_metadata = result.analysis_metadata
                         analyzed_count += 1
            
            db.commit()
            return {"status": "success", "analyzed": analyzed_count, "strategy_used": strategy}
            
        except Exception as e:
            print(f"Error during analysis: {e}")
            raise e
        finally:
            db.close()

    def _export_training_data(self, job_id: str) -> str:
        """
        Export annotated training data to YOLO format.
        Returns path to dataset.yaml.
        """
        update_job(job_id, message="Adatok exportálása YOLO formátumba...")
        
        # Setup directories
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dataset_dir = os.path.join(base_dir, "data", "training_dataset")
        
        # Clean and recreate
        if os.path.exists(dataset_dir):
            shutil.rmtree(dataset_dir)
            
        dirs = [
            os.path.join(dataset_dir, "images", "train"),
            os.path.join(dataset_dir, "images", "val"),
            os.path.join(dataset_dir, "labels", "train"),
            os.path.join(dataset_dir, "labels", "val")
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            
        db = SessionLocal()
        try:
            items = db.query(TrainingData).all()
            print(f"DEBUG: Found {len(items)} training items")
            
            if not items:
                raise ValueError("No training data found in database!")

            # Class mapping (must match DAMAGE_CLASSES keys/order or be consistent)
            # We use the index of keys in DAMAGE_CLASSES
            class_map = {name: k for k, name in self.DAMAGE_CLASSES.items()} 
            # Reverse map for checking: str -> int
            # But DAMAGE_CLASSES is int -> str. 
            # Let's create a str -> int map based on DAMAGE_NAMES for safety or just use fixed ID?
            # actually DAMAGE_CLASSES is {0: 'long_crack', ...}
            # The annotations are usually strings like 'long_crack'.
            str_to_id = {v: k for k, v in self.DAMAGE_CLASSES.items()}

            processed_count = 0
            
            for item in items:
                # Determine split
                split = "train" if random.random() < 0.8 else "val"
                
                # Source image
                # stored as filename in DB, likely in data/images
                # Try backend/data/images first, then project_root/data/images
                src_path = os.path.join(base_dir, "data", "images", item.image_filename)
                
                if not os.path.exists(src_path):
                     # Try sibling data dir (if base_dir is backend)
                     project_root = os.path.dirname(base_dir)
                     src_path_root = os.path.join(project_root, "data", "images", item.image_filename)
                     if os.path.exists(src_path_root):
                         src_path = src_path_root
                
                if not os.path.exists(src_path):
                    print(f"WARNING: Image {src_path} not found, skipping.")
                    continue
                    
                # Copy image
                dst_img_path = os.path.join(dataset_dir, "images", split, item.image_filename)
                shutil.copy2(src_path, dst_img_path)
                
                # Generate label file
                label_filename = os.path.splitext(item.image_filename)[0] + ".txt"
                dst_label_path = os.path.join(dataset_dir, "labels", split, label_filename)
                
                # Read image dimensions for normalization
                img = cv2.imread(src_path)
                if img is None: continue
                h, w = img.shape[:2]
                
                with open(dst_label_path, "w") as f:
                    # Parse annotations
                    # Expected format: JSON list of dicts
                    # We need to handle different structures if they exist, but assuming standard:
                    # {label: str, x: float, y: float, w: float, h: float} (pixels or normalized?)
                    # OR {label: str, points: [[x,y]...]} (polygons)
                    
                    annotations = item.annotations
                    if isinstance(annotations, str):
                        annotations = json.loads(annotations)
                        
                    for ann in annotations:
                        label = ann.get("label")
                        if label not in str_to_id:
                            continue
                        
                        cls_id = str_to_id[label]
                        
                        # Check for polygon points
                        if "points" in ann and ann["points"]:
                            # YOLO segmentation format: <class-index> <x1> <y1> <x2> <y2> ... <xn> <yn>
                            # Normalized 0-1
                            points = ann["points"]
                            line = f"{cls_id}"
                            for pt in points:
                                nx = pt[0] / w
                                ny = pt[1] / h
                                line += f" {nx:.6f} {ny:.6f}"
                            f.write(line + "\n")
                            
                        # Check for bbox (x, y, w, h) - CENTER based or TopLeft?
                        # Usually annotations from UI are top-left or whatever.
                        # Assuming UI provides x,y (top-left), w, h in pixels.
                        # YOLO detection needs: class x_center y_center width height (normalized)
                        elif "x" in ann:
                            x, y = ann["x"], ann["y"]
                            ww, hh = ann["w"], ann["h"]
                            
                            cx = (x + ww/2) / w
                            cy = (y + hh/2) / h
                            nw = ww / w
                            nh = hh / h
                            
                            f.write(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")
                            
                processed_count += 1
                
            print(f"DEBUG: Processed {processed_count} images for training")
            
            # Create dataset.yaml
            yaml_content = {
                "train": "images/train",
                "val": "images/val",
                "nc": len(self.DAMAGE_CLASSES),
                "names": self.DAMAGE_CLASSES
            }
            
            yaml_path = os.path.join(dataset_dir, "data.yaml")
            with open(yaml_path, "w") as f:
                yaml.dump(yaml_content, f)
                
            return yaml_path
            
        finally:
            db.close()

    def run_training(self, job_id: str) -> Dict:
        """
        Run model training using the configured provider.
        
        Provider is determined by 'training_provider' setting:
        - 'local': Run training on local machine (MPS/CUDA/CPU)
        - 'google_colab': Export notebook and dataset for Colab execution
        """
        print(f"DEBUG: Starting training for job {job_id}")
        
        try:
            # 1. Export training data
            yaml_path = self._export_training_data(job_id)
            
            # 2. Get training configuration from settings
            update_job(job_id, current_step=JobStep.TRAINING, progress=10, total=100, message="Konfiguráció betöltése...")
            
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            # Get provider setting
            provider_name = self._get_setting("training_provider", "local")
            
            # Get training parameters
            model_name = self._get_setting("ai_model", "yolov8m-seg.pt") or "yolov8m-seg.pt"
            epochs = int(self._get_setting("training_epochs", 50))
            batch_size = int(self._get_setting("training_batch_size", 16))
            workers = int(self._get_setting("training_workers", 4))
            patience = int(self._get_setting("training_patience", 50))
            
            # Create config
            from app.services.training import TrainingConfig, TrainingProvider
            from app.services.training import LocalTrainingProvider, ColabTrainingProvider
            
            def progress_callback(progress: int, message: str):
                update_job(job_id, progress=progress, message=message)
            
            config = TrainingConfig(
                job_id=job_id,
                data_yaml_path=yaml_path,
                model_name=model_name,
                epochs=epochs,
                batch_size=batch_size,
                workers=workers,
                device='',  # Auto-detect
                patience=patience,
                base_dir=base_dir,
                output_dir=os.path.join(base_dir, "data", "runs"),
                progress_callback=progress_callback,
            )
            
            # Select provider
            if provider_name == TrainingProvider.GOOGLE_COLAB.value:
                provider = ColabTrainingProvider()
                update_job(job_id, progress=20, message="Colab notebook és dataset exportálása...")
            else:
                provider = LocalTrainingProvider()
                update_job(job_id, progress=20, message=f"Lokális tanítás ({epochs} epoch, batch {batch_size})...")
            
            print(f"DEBUG: Using training provider: {provider.get_provider_name()}")
            
            # 3. Run training via provider
            result = provider.run(config)
            
            # 4. Handle result
            if result["success"]:
                # The provider's 100% progress should be preserved
                
                # Reload model if we have a new path
                if result.get("model_path"):
                    self.model_path = result["model_path"]
                    self._load_model()
                
                return {
                    "status": "success",
                    "model_path": result.get("model_path"),
                    "message": result.get("message"),
                    "metrics": result.get("metrics", {}),
                    "exports": result.get("exports"),  # For Colab
                }
            else:
                raise Exception(result.get("message", "Training failed"))
            
        except Exception as e:
            print(f"Training failed: {e}")
            import traceback
            traceback.print_exc()
            raise e

# Singleton instance
road_quality_service = RoadQualityService()
