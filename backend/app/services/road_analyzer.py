"""
YOLO-based road damage analyzer: loads the segmentation model and scores a
single image (damage detection + ROI masking + damage%→RQI).
"""

from typing import Dict, Optional

import cv2
import numpy as np

from app.services.rqi_scoring import (
    DAMAGE_CLASSES,
    MAX_DAMAGE_CLASS_ID,
    DamageDetection,
    RoadQualityResult,
    rqi_from_damage_percent,
)
from app.services.yolo_loader import (
    DEFAULT_YOLO_MODEL,
    YoloModelLoader,
    yolo_model_loader,
)

# Ordered class codes (index == YOLO class id).
CLASS_CODES = [DAMAGE_CLASSES[i] for i in sorted(DAMAGE_CLASSES)]


class RoadDamageAnalyzer:
    """Loads the YOLO model (lazily) and analyzes one image at a time."""

    def __init__(self, model_loader: YoloModelLoader = yolo_model_loader):
        self._model_loader = model_loader
        self.model = None
        self.current_model_path = None

    def _get_setting(self, key: str, default: float) -> float:
        from app.core.settings_manager import settings_manager

        return settings_manager.get_setting(key, default)

    def _load_model(self):
        """Lazy load or reload the YOLO model if settings changed."""
        from app.core.settings_manager import settings_manager

        target_model = settings_manager.get_setting("yolo_model", DEFAULT_YOLO_MODEL)
        self.model = self._model_loader.load("road_damage", target_model)
        loaded_path = self._model_loader.loaded_path("road_damage")
        self.current_model_path = str(loaded_path) if loaded_path else None
        self.is_segmentation = getattr(self.model, "task", None) == "segment"

    def analyze_image(
        self, image_path: str, confidence_threshold: Optional[float] = None
    ) -> RoadQualityResult:
        """Analyze a single image for road damage (segmentation + ROI masking)."""
        self._load_model()

        if confidence_threshold is None:
            confidence_threshold = self._get_setting("yolo_inference_conf", 0.25)

        results = self.model(image_path, conf=confidence_threshold, verbose=False)

        detections = []
        damage_counts: Dict[str, int] = {}
        total_damage_pixels = 0

        img_h, img_w = 0, 0
        roi_area_pixels = 0

        for result in results:
            img_h, img_w = result.orig_shape

            # ROI trapezoid: damage only counts if it is on the road surface.
            roi_mask = np.zeros((img_h, img_w), dtype=np.uint8)
            mask_poly = np.array(
                [
                    [img_w * 0.1, img_h],  # bottom-left
                    [img_w * 0.9, img_h],  # bottom-right
                    [img_w * 0.65, img_h * 0.5],  # top-right
                    [img_w * 0.35, img_h * 0.5],  # top-left
                ],
                dtype=np.int32,
            )
            cv2.fillPoly(roi_mask, [mask_poly], 255)
            roi_area_pixels = np.sum(roi_mask > 0)

            if hasattr(result, "masks") and result.masks is not None:
                for i, mask_obj in enumerate(result.masks.data):
                    conf = float(result.boxes.conf[i])
                    cls_id = int(result.boxes.cls[i])
                    label = (
                        CLASS_CODES[cls_id] if cls_id < len(CLASS_CODES) else "unknown"
                    )

                    mask = mask_obj.cpu().numpy()
                    mask = cv2.resize(mask, (img_w, img_h))

                    effective_mask = cv2.bitwise_and(mask, mask, mask=roi_mask)
                    damage_pixels = np.sum(effective_mask > 0.5)

                    if damage_pixels > 0:
                        rel_area = damage_pixels / roi_area_pixels
                        x1, y1, x2, y2 = result.boxes.xyxy[i].tolist()
                        detections.append(
                            DamageDetection(
                                damage_type=label,
                                confidence=conf,
                                bbox=(x1, y1, x2, y2),
                                area=rel_area,
                            )
                        )
                        # Negative classes (shadow/manhole/marking) don't count as damage.
                        if cls_id <= MAX_DAMAGE_CLASS_ID:
                            total_damage_pixels += damage_pixels
                            damage_counts[label] = damage_counts.get(label, 0) + 1

            elif result.boxes is not None:
                # Fallback to bounding boxes.
                for box in result.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    label = (
                        CLASS_CODES[cls_id] if cls_id < len(CLASS_CODES) else "unknown"
                    )

                    cy = (y1 + y2) / 2
                    if cy > img_h * 0.5:
                        box_area = (x2 - x1) * (y2 - y1)
                        rel_area = box_area / (img_h * img_w)
                        detections.append(
                            DamageDetection(
                                damage_type=label,
                                confidence=conf,
                                bbox=(x1, y1, x2, y2),
                                area=rel_area,
                            )
                        )
                        if cls_id <= MAX_DAMAGE_CLASS_ID:
                            damage_counts[label] = damage_counts.get(label, 0) + 1

        total_damage_percent = (
            (total_damage_pixels / roi_area_pixels) * 100 if roi_area_pixels > 0 else 0
        )

        return RoadQualityResult(
            rqi_score=rqi_from_damage_percent(total_damage_percent),
            damage_count=len(damage_counts),
            damage_types=damage_counts,
            detections=detections,
            analysis_metadata={"damage_percent": round(total_damage_percent, 2)},
        )
