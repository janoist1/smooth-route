import os
import shutil
import json
import yaml
import random
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.database import SessionLocal
from app.models.models import TrainingData
from app.services.job_service import update_job, JobStep, JobStatus
from app.core.settings_manager import settings_manager
from app.services.training import TrainingConfig
from app.services.dino_service import dino_service
from app.services.preprocessing import road_preprocessor

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

    def run_training(self, job_id: str, model_type: str = "YOLO") -> Dict:
        """
        Run model training using the configured provider.
        """
        print(f"DEBUG: Starting training for job {job_id} (Type: {model_type})")
        
        try:
        # 1. Export training data
            if model_type == "DINO":
                dataset_path = self.export_dino_data(job_id)
            else:
                dataset_path = self.export_yolo_data(job_id)
            
            # 2. Get training configuration
            update_job(job_id, status=JobStatus.RUNNING, current_step=JobStep.TRAINING, progress=10, total=100, message="Konfiguráció betöltése...")
            
            # Get settings using manager directly
            provider_name = settings_manager.get_setting("training_provider", "local")
            
            if model_type == "DINO":
                model_name = "dinov2_vits14" # settings_manager.get_setting("dino_model_name", "dinov2_vits14")
                epochs = int(settings_manager.get_setting("dino_training_epochs", 20))
                batch_size = int(settings_manager.get_setting("dino_training_batch_size", 32))
            else:
                model_name = settings_manager.get_setting("yolo_model", "yolov8m-seg.pt") or "yolov8m-seg.pt"
                # Fallback to old 'ai_model' if 'yolo_model' missing during migration? 
                # Better to just set defaults.
                epochs = int(settings_manager.get_setting("yolo_training_epochs", 50))
                batch_size = int(settings_manager.get_setting("yolo_training_batch_size", 16))
            
            workers = int(settings_manager.get_setting("training_workers", 4))
            patience = int(settings_manager.get_setting("yolo_training_patience", 50))
            
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
                base_dir=os.getcwd(),
                patience=patience,
                output_dir=os.path.join(os.getcwd(), "runs", "detect"),
                model_type=model_type,
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
        
        # Setup directories
        base_dir = os.getcwd() # Use CWD for smoother path handling
        if not os.path.exists(os.path.join(base_dir, "app")):
             # Fallback if CWD is not project root
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

            str_to_id = {v: k for k, v in self.DAMAGE_CLASSES.items()}

            processed_count = 0
            
            for item in items:
                split = "train" if random.random() < 0.8 else "val"
                
                # Resilient image path resolution
                src_path = os.path.join(base_dir, "data", "images", item.image_filename)
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

    def export_dino_data(self, job_id: str) -> str:
        """
        Export data for DINO classification training.
        Returns path to dataset directory.
        """
        update_job(job_id, status=JobStatus.RUNNING, message="Adatok exportálása DINO (Classifikáció) formátumba...")
        
        base_dir = os.getcwd()
        if not os.path.exists(os.path.join(base_dir, "app")):
             base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        export_dir = os.path.join(base_dir, "data", "dino_dataset")
        
        if os.path.exists(export_dir):
            shutil.rmtree(export_dir)
            
        # Create class folders 1-5
        for i in range(1, 6):
            os.makedirs(os.path.join(export_dir, str(i)), exist_ok=True)
            
        db = SessionLocal()
        try:
            items = db.query(TrainingData).filter(TrainingData.manual_rqi != None).all()
            print(f"DEBUG: Found {len(items)} items for DINO export")
            
            if not items:
                raise ValueError("Nincs DINO RQI besorolással rendelkező adat!")

            processed_count = 0
            total_items = len(items)
            
            # Initialize progress for Export phase
            update_job(job_id, progress=0, total=total_items, message=f"Adatok exportálása... (Összesen: {total_items} db)")
            
            for i, item in enumerate(items):
                # Update progress every 5 items to show movement
                if i % 5 == 0:
                    update_job(job_id, progress=i, total=total_items, message=f"Adatok előkészítése (FastSAM): {i}/{total_items}...")
                
                src_path = os.path.join(base_dir, "data", "images", item.image_filename)
                if not os.path.exists(src_path):
                     if os.path.exists(item.image_filename):
                         src_path = item.image_filename
                
                if not os.path.exists(src_path):
                    continue
                    
                rqi_folder = str(int(round(item.manual_rqi)))
                if rqi_folder not in ["1", "2", "3", "4", "5"]:
                    continue
                    
                dst_path = os.path.join(export_dir, rqi_folder, item.image_filename)
                
                # Use Preprocessing (YOLO Segmentation + ROI)
                # FORCE Smart ROI (FastSAM) as it is the primary approved method
                process_options = {
                    "smart_roi": True,
                    "use_mask": False, # Experimental
                    "use_roi": False,  # Experimental
                    "remove_shadows_1": False,
                    "remove_shadows_2": False
                }
                try:
                    road_preprocessor.process_and_save(src_path, dst_path, options=process_options)
                except Exception as e:
                    print(f"Warning: Preprocessing failed for {src_path}, using raw image. Error: {e}")
                    shutil.copy2(src_path, dst_path)
                    
                processed_count += 1
                
            return export_dir
            
        finally:
            db.close()

training_service = TrainingService()
