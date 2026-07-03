from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.services.yolo_loader import (
    DEFAULT_YOLO_MODEL,
    YoloModelLoader,
    yolo_model_loader,
)


class InferenceService:
    def __init__(self, model_loader: YoloModelLoader = yolo_model_loader):
        self._model_loader = model_loader
        self.model = None
        self.cleaner_model = None
        self.current_model_path = None

    def load_model(self, force_reload: bool = False):
        """Load or reload the models if settings changed."""
        from app.core.settings_manager import settings_manager

        target_model_name = settings_manager.get_setting(
            "yolo_model", DEFAULT_YOLO_MODEL
        )
        target_cleaner_name = settings_manager.get_setting(
            "yolo_cleaner_model", DEFAULT_YOLO_MODEL
        )

        self.model = self._model_loader.load(
            "road_damage",
            target_model_name,
            force_reload=force_reload,
        )
        loaded_path = self._model_loader.loaded_path("road_damage")
        self.current_model_path = str(loaded_path) if loaded_path else None

        if target_cleaner_name:
            self.cleaner_model = self._model_loader.load(
                "vehicle_cleaner",
                target_cleaner_name,
                force_reload=force_reload,
            )
            cleaner_path = self._model_loader.loaded_path("vehicle_cleaner")
            self.current_cleaner_path = str(cleaner_path) if cleaner_path else None
        else:
            self._model_loader.unload("vehicle_cleaner")
            self.cleaner_model = None
            self.current_cleaner_path = None

    def detect_objects(
        self,
        image_path: str,
        conf_threshold: Optional[float] = None,
        classes: Optional[List[str]] = None,
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
            conf_threshold = settings_manager.get_setting("yolo_inference_conf", 0.25)

        cleaner_conf = settings_manager.get_setting("yolo_cleaner_conf", 0.25)

        print(
            f"DEBUG: Inference on {image_path} with conf={conf_threshold} using model {self.current_model_path}"
        )
        if classes:
            print(f"DEBUG: Filtering for classes: {classes}")

        if self.model is None:
            print("ERROR: Model is NONE in detect_objects")
            return []

        if not Path(image_path).is_file():
            print(f"ERROR: Image path NOT FOUND: {image_path}")
            return []

        # Run inference logic based on requested classes

        # Determine what to run
        run_cleaner = True
        run_main = True

        if classes is not None:
            # If classes specified, only run cleaner if 'ignore' is requested
            run_cleaner = "ignore" in classes
            # Only run main if there are other classes besides 'ignore'
            run_main = any(c != "ignore" for c in classes)

        predictions = []
        img_height, img_width = 0, 0
        vehicle_zones = []

        if run_cleaner and self.cleaner_model:
            cleaner_results = self.cleaner_model(
                image_path,
                conf=cleaner_conf,
                verbose=False,
                classes=[2, 3, 5, 7],
            )
            for cr in cleaner_results:
                if img_height == 0:
                    img_height, img_width = cr.orig_shape

                if hasattr(cr, "masks") and cr.masks is not None:
                    for mask_tensor in cr.masks.data:
                        mask = (mask_tensor.cpu().numpy() * 255).astype(np.uint8)
                        if mask.shape != (img_height, img_width):
                            mask = cv2.resize(
                                mask,
                                (img_width, img_height),
                                interpolation=cv2.INTER_NEAREST,
                            )

                        vehicle_zones.append(mask)
                        contours, _ = cv2.findContours(
                            mask,
                            cv2.RETR_EXTERNAL,
                            cv2.CHAIN_APPROX_SIMPLE,
                        )
                        for contour in contours:
                            if cv2.contourArea(contour) <= 50:
                                continue
                            epsilon = 0.005 * cv2.arcLength(contour, True)
                            approx = cv2.approxPolyDP(contour, epsilon, True)
                            predictions.append(
                                {
                                    "label": "ignore",
                                    "confidence": 0.8,
                                    "points": approx.reshape(-1, 2).tolist(),
                                }
                            )

                elif hasattr(cr, "boxes") and cr.boxes is not None:
                    for box in cr.boxes:
                        xyxy = box.xyxy[0].tolist()
                        x1, y1, x2, y2 = map(int, xyxy)

                        mask = np.zeros((img_height, img_width), dtype=np.uint8)
                        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
                        vehicle_zones.append(mask)

                        predictions.append(
                            {
                                "label": "ignore",
                                "confidence": float(box.conf[0]),
                                "points": [
                                    [x1, y1],
                                    [x2, y1],
                                    [x2, y2],
                                    [x1, y2],
                                ],
                            }
                        )

        if run_main:
            target_indices = None
            if classes and self.model.names:
                name_to_idx = {v: k for k, v in self.model.names.items()}
                target_indices = [
                    name_to_idx[name]
                    for name in classes
                    if name != "ignore" and name in name_to_idx
                ]
                if not target_indices:
                    return predictions

            results = self.model(
                image_path,
                conf=conf_threshold,
                verbose=False,
                classes=target_indices,
            )

            for r in results:
                if img_height == 0:
                    img_height, img_width = (
                        r.orig_shape if hasattr(r, "orig_shape") else (640, 640)
                    )

                exclusion_mask = None
                if vehicle_zones:
                    exclusion_mask = vehicle_zones[0]
                    for i in range(1, len(vehicle_zones)):
                        exclusion_mask = cv2.bitwise_or(
                            exclusion_mask, vehicle_zones[i]
                        )

                if hasattr(r, "masks") and r.masks is not None:
                    for i, mask_obj in enumerate(r.masks.data):
                        conf = float(r.boxes.conf[i])
                        cls_id = int(r.boxes.cls[i])
                        label = r.names[cls_id]

                        if classes and label not in classes:
                            continue

                        mask = mask_obj.cpu().numpy()
                        mask = cv2.resize(mask, (img_width, img_height))
                        mask = (mask > 0.5).astype(np.uint8) * 255

                        if exclusion_mask is not None:
                            mask = cv2.bitwise_and(
                                mask, cv2.bitwise_not(exclusion_mask)
                            )

                        contours, _ = cv2.findContours(
                            mask,
                            cv2.RETR_EXTERNAL,
                            cv2.CHAIN_APPROX_SIMPLE,
                        )
                        for contour in contours:
                            if cv2.contourArea(contour) <= 20:
                                continue
                            epsilon = 0.005 * cv2.arcLength(contour, True)
                            approx = cv2.approxPolyDP(contour, epsilon, True)
                            predictions.append(
                                {
                                    "label": label,
                                    "confidence": conf,
                                    "points": approx.reshape(-1, 2).tolist(),
                                }
                            )

                elif r.boxes is not None:
                    for box in r.boxes:
                        label = r.names[int(box.cls[0])]
                        if classes and label not in classes:
                            continue

                        xyxy = box.xyxy[0].tolist()
                        points = [
                            [xyxy[0], xyxy[1]],
                            [xyxy[2], xyxy[1]],
                            [xyxy[2], xyxy[3]],
                            [xyxy[0], xyxy[3]],
                        ]
                        predictions.append(
                            {
                                "label": label,
                                "confidence": float(box.conf[0]),
                                "points": points,
                            }
                        )

        return predictions


# Singleton instance
inference_service = InferenceService()
