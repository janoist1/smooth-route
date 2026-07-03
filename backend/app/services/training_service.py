import os
import shutil
import json
import yaml
import random
from datetime import datetime
from typing import Any, Dict

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import TrainingData
from app.services.job_service import update_job, JobStep, JobStatus
from app.core.settings_manager import settings_manager
from app.services.training import TrainingConfig

class TrainingService:
    """Service for managing model training workflows."""

    # Pipeline 2.0 Taxonomy (Matched with RoadQualityService)
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

    def run_training(self, job_id: str) -> Dict:
        """Run YOLO model training using the configured provider."""
        print(f"DEBUG: Starting YOLO training for job {job_id}")
        
        try:
            # 1. Export training data
            dataset_path = self.export_yolo_data(job_id)
            
            # 2. Get training configuration
            update_job(job_id, status=JobStatus.RUNNING, current_step=JobStep.TRAINING, progress=10, total=100, message="Konfiguráció betöltése...")
            
            # Get settings using manager directly
            provider_name = settings_manager.get_setting("training_provider", "local")
            
            model_name = settings_manager.get_setting("yolo_model", "yolov8m-seg.pt") or "yolov8m-seg.pt"
            epochs = int(settings_manager.get_setting("yolo_training_epochs", 50))
            batch_size = int(settings_manager.get_setting("yolo_training_batch_size", 16))
            
            workers = int(settings_manager.get_setting("training_workers", 4))
            patience = int(settings_manager.get_setting("yolo_training_patience", 50))
            data_dir = settings.resolve_data_dir()
            
            # Create config
            def progress_callback(progress: int, message: str):
                update_job(job_id, progress=progress, message=message)
            
            config = TrainingConfig(
                job_id=job_id,
                data_yaml_path=dataset_path, 
                model_name=model_name,
                epochs=epochs,
                batch_size=batch_size,
                workers=workers,
                device='',  # Auto-detect
                data_dir=data_dir,
                patience=patience,
                output_dir=os.path.join(data_dir, "runs", "detect"),
                progress_callback=progress_callback
            )

            # Get provider
            from app.services.training import LocalTrainingProvider, ColabTrainingProvider
            
            if provider_name == "google_colab":
                provider = ColabTrainingProvider()
            else:
                provider = LocalTrainingProvider()
                
            # Run
            update_job(job_id, message=f"Tanítás indítása ({provider_name})...")
            return provider.run(config)
            
        except Exception as e:
            print(f"Error executing training: {e}")
            raise e

    def export_yolo_data(self, job_id: str) -> str:
        """
        Export annotated training data to YOLO format.
        Returns path to dataset.yaml.
        """
        update_job(job_id, message="Adatok exportálása YOLO formátumba...")
        
        data_dir = settings.resolve_data_dir()
        dataset_dir = os.path.join(data_dir, "training_dataset")
        
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

            str_to_id = {v: k for k, v in self.DAMAGE_CLASSES.items()}

            processed_count = 0
            
            for item in items:
                split = "train" if random.random() < 0.8 else "val"
                
                src_path = os.path.join(data_dir, "images", item.image_filename)
                if not os.path.exists(src_path):
                     # Try absolute path logic if filename is actually full path
                     if os.path.exists(item.image_filename):
                         src_path = item.image_filename
                
                if not os.path.exists(src_path):
                    continue
                    
                # Copy image
                dst_img_path = os.path.join(dataset_dir, "images", split, item.image_filename)
                shutil.copy2(src_path, dst_img_path)
                
                # Generate label file
                label_filename = os.path.splitext(item.image_filename)[0] + ".txt"
                dst_label_path = os.path.join(dataset_dir, "labels", split, label_filename)
                
                # Read image dimensions
                import cv2
                img = cv2.imread(src_path)
                if img is None: continue
                h, w = img.shape[:2]
                
                with open(dst_label_path, "w") as f:
                    annotations = item.annotations
                    if isinstance(annotations, str):
                        annotations = json.loads(annotations)
                        
                    for ann in annotations:
                        label = ann.get("label")
                        if label not in str_to_id:
                            continue
                        
                        cls_id = str_to_id[label]
                        
                        if "points" in ann and ann["points"]:
                            # Segmentation logic
                            points = ann["points"]
                            line = f"{cls_id}"
                            for pt in points:
                                nx = pt[0] / w
                                ny = pt[1] / h
                                line += f" {nx:.6f} {ny:.6f}"
                            f.write(line + "\n")
                        # Add bbox logic if needed, but usually we use segmentation for Polygons
                            
                processed_count += 1

            # Create dataset.yaml
            yaml_content = {
                "path": dataset_dir,
                "train": "images/train",
                "val": "images/val",
                "names": self.DAMAGE_CLASSES
            }
            
            yaml_path = os.path.join(dataset_dir, "dataset.yaml")
            with open(yaml_path, "w") as f:
                yaml.dump(yaml_content, f)
                
            print(f"DEBUG: Exported {processed_count} images for training")
            return yaml_path
            
        finally:
            db.close()

training_service = TrainingService()
