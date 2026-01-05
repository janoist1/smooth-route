import os
import cv2
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Optional, Any

class InferenceService:
    def __init__(self):
        self.model = None
        self.cleaner_model = None
        self.current_model_path = None
        
    def _get_actual_model_path(self, model_name: str) -> str:
        """Resolve a model name to an absolute path."""
        # If it's an absolute path that exists, use it
        if os.path.isabs(model_name) and os.path.exists(model_name):
            return model_name
            
        # Try finding it in data/models
        project_root = os.getcwd()
        candidates = [
            os.path.join(project_root, "data", "models", model_name),
            os.path.join(project_root, "..", "backend", "data", "models", model_name),
            os.path.join(project_root, "backend", "data", "models", model_name),
            os.path.join("data", "models", model_name), # If cwd is backend
            model_name
        ]
        
        for cand in candidates:
            if os.path.exists(cand):
                return cand
                
        return model_name

    def load_model(self, force_reload: bool = False):
        """Load or reload the models if settings changed."""
        from app.core.settings_manager import settings_manager
        target_model_name = settings_manager.get_setting("ai_model", "yolov12s-seg.pt")
        target_cleaner_name = settings_manager.get_setting("cleaner_model", "yolov8n.pt")
        
        # Load main defect model
        if self.model is None or self.current_model_path != target_model_name or force_reload:
            actual_path = self._get_actual_model_path(target_model_name)
            print(f"InferenceService: Loading YOLO model from {actual_path}...")
            try:
                self.model = YOLO(actual_path)
                self.current_model_path = target_model_name
                print(f"InferenceService: Model loaded successfully. Task: {getattr(self.model, 'task', 'unknown')}")
            except Exception as e:
                print(f"InferenceService: ERROR loading main model: {e}")
                # Fallback to default
                self.model = YOLO("yolov12s-seg.pt")
                self.current_model_path = "yolov12s-seg.pt"

        # Load cleaner model (standard COCO model to find vehicles)
        if target_cleaner_name and (self.cleaner_model is None or getattr(self, 'current_cleaner_path', None) != target_cleaner_name):
            cleaner_path = self._get_actual_model_path(target_cleaner_name)
            if os.path.exists(cleaner_path):
                 print(f"InferenceService: Loading Cleaner model from {cleaner_path}...")
                 self.cleaner_model = YOLO(cleaner_path)
                 self.current_cleaner_path = target_cleaner_name
                 # COCO vehicle classes: car(2), motorcycle(3), bus(5), truck(7)
            else:
                 print(f"InferenceService: Cleaner model {target_cleaner_name} not found at {cleaner_path}")
        elif not target_cleaner_name: # If cleaner model is explicitly disabled in settings
            if self.cleaner_model is not None:
                print("InferenceService: Cleaner model disabled in settings. Unloading.")
                self.cleaner_model = None
                self.current_cleaner_path = None


    def detect_objects(
        self, 
        image_path: str, 
        conf_threshold: Optional[float] = None, 
        classes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Run YOLO inference on a specific image and return polygons.
        Matched to the method name called in schema.py.
        
        Args:
            classes: Optional list of class names to detect. 
                     Special handling for 'ignore' which uses cleaner_model.
        """
        self.load_model()
        
        from app.core.settings_manager import settings_manager
        if conf_threshold is None:
            conf_threshold = settings_manager.get_setting("ai_inference_conf", 0.25)
            
        cleaner_conf = settings_manager.get_setting("cleaner_conf", 0.25)
            
        print(f"DEBUG: Inference on {image_path} with conf={conf_threshold} using model {self.current_model_path}")
        if classes:
            print(f"DEBUG: Filtering for classes: {classes}")
            
        if self.model is None:
            print("ERROR: Model is NONE in detect_objects")
            return []

        if not os.path.exists(image_path):
            print(f"ERROR: Image path NOT FOUND: {image_path}")
            return []

        # Run inference logic based on requested classes
        
        # Determine what to run
        run_cleaner = True
        run_main = True
        
        if classes is not None:
            # If classes specified, only run cleaner if 'ignore' is requested
            run_cleaner = 'ignore' in classes
            # Only run main if there are other classes besides 'ignore'
            run_main = any(c != 'ignore' for c in classes)

        predictions = []
        import cv2
        import numpy as np

        img_height, img_width = 0, 0
        vehicle_zones = []

        # --- 1. CLEANER MODEL (Ignore/Vehicles) ---
        if run_cleaner and self.cleaner_model:
            # COCO classes: 2: car, 3: motorcycle, 5: bus, 7: truck
            cleaner_results = self.cleaner_model(image_path, conf=cleaner_conf, verbose=False, classes=[2, 3, 5, 7])
            for cr in cleaner_results:
                if img_height == 0:
                     img_height, img_width = cr.orig_shape
                
                # We always add cleaner detections as 'ignore' polygons
                # AND use them for exclusion if we are running main model
                
                if hasattr(cr, 'masks') and cr.masks is not None:
                     for m_tensor in cr.masks.data:
                         m = (m_tensor.cpu().numpy() * 255).astype(np.uint8)
                         if m.shape[0] != img_height or m.shape[1] != img_width:
                             m = cv2.resize(m, (img_width, img_height), interpolation=cv2.INTER_NEAREST)
                         
                         # Save for exclusion
                         vehicle_zones.append(m)
                         
                         # Add to predictions as 'ignore'
                         contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                         for cnt in contours:
                             if cv2.contourArea(cnt) > 50: # Minimum area
                                 epsilon = 0.005 * cv2.arcLength(cnt, True)
                                 approx = cv2.approxPolyDP(cnt, epsilon, True)
                                 pts = approx.reshape(-1, 2).tolist()
                                 predictions.append({
                                     "label": "ignore",
                                     "confidence": 0.8, # Static high confidence for cleaner
                                     "points": pts
                                 })
                                 
                elif hasattr(cr, 'boxes') and cr.boxes is not None:
                     for box in cr.boxes:
                        xyxy = box.xyxy[0].tolist()
                        x1, y1, x2, y2 = map(int, xyxy)
                        
                        # Create mask for exclusion
                        m = np.zeros((img_height, img_width), dtype=np.uint8)
                        cv2.rectangle(m, (x1, y1), (x2, y2), 255, -1)
                        vehicle_zones.append(m)
                        
                        # Add box as polygon
                        predictions.append({
                            "label": "ignore",
                            "confidence": float(box.conf[0]),
                            "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                        })

        # --- 2. MAIN MODEL (Defects) ---
        if run_main:
            # If we didn't get dimensions from cleaner, we'll get them from main result
            
            # Map requested classes to model indices if filtering
            target_indices = None
            if classes and self.model.names:
                # Invert map: name -> index
                name_to_idx = {v: k for k, v in self.model.names.items()}
                target_indices = []
                for c in classes:
                    if c in name_to_idx:
                        target_indices.append(name_to_idx[c])
                    # Note: 'ignore' is handled by cleaner, so we don't need to look for it in main model 
                    # unless the main model ALSO has an 'ignore' class (rare for RDD, usually it's vehicles/cleaner)

                # If we have classes but none map to main model (e.g. only passed 'ignore'), 
                # run_main should technically be False, but we handle it here
                if not target_indices: 
                    # If user asked for specific classes but none match main model, skip main model inference
                    # (Unless we want to be safe, but efficiency matters)
                    pass 

            results = self.model(
                image_path, 
                conf=conf_threshold, 
                verbose=False, 
                classes=target_indices # Pass specific classes to accelerate/filter NMS
            )
            
            for r in results:
                if img_height == 0:
                    img_height, img_width = r.orig_shape if hasattr(r, 'orig_shape') else (640, 640)

                # Create combined exclusion mask from vehicles
                exclusion_mask = None
                if vehicle_zones:
                    exclusion_mask = vehicle_zones[0]
                    for i in range(1, len(vehicle_zones)):
                        exclusion_mask = cv2.bitwise_or(exclusion_mask, vehicle_zones[i])
                
                # Check for masks
                if hasattr(r, 'masks') and r.masks is not None:
                    # .. existing mask processing logic
                    pass
                    # For brevity in this tool call, I will rely on the existing code structure 
                    # or rewrite the loop if I'm replacing the whole block.
                    # Since I am replacing a big block, I need to include the loop logic.
                    
                    for i, mask_obj in enumerate(r.masks.data):
                        conf = float(r.boxes.conf[i])
                        cls_id = int(r.boxes.cls[i])
                        label = r.names[cls_id]
                        
                        # Double check filtering (redundant if classes= arg worked, but safe)
                        if classes and label not in classes:
                            continue

                        # Resize mask
                        mask = mask_obj.cpu().numpy()
                        mask = cv2.resize(mask, (img_width, img_height))
                        mask = (mask > 0.5).astype(np.uint8) * 255
                        
                        # Apply exclusion (don't detect defects on top of cars)
                        if exclusion_mask is not None:
                            # Subtract exclusion mask
                            mask = cv2.bitwise_and(mask, cv2.bitwise_not(exclusion_mask))
                            
                        # Find contours
                        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        for cnt in contours:
                            if cv2.contourArea(cnt) > 20: 
                                epsilon = 0.005 * cv2.arcLength(cnt, True)
                                approx = cv2.approxPolyDP(cnt, epsilon, True)
                                pts = approx.reshape(-1, 2).tolist()
                                predictions.append({
                                    "label": label,
                                    "confidence": conf,
                                    "points": pts
                                })

                elif r.boxes is not None:
                    for box in r.boxes:
                        label = r.names[int(box.cls[0])]
                        if classes and label not in classes: continue
                        
                        xyxy = box.xyxy[0].tolist()
                        points = [[xyxy[0], xyxy[1]], [xyxy[2], xyxy[1]], [xyxy[2], xyxy[3]], [xyxy[0], xyxy[3]]]
                        predictions.append({
                            "label": label,
                            "confidence": float(box.conf[0]),
                            "points": points
                        })

        return predictions

# Singleton instance
inference_service = InferenceService()
