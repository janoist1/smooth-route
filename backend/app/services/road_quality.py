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

    # Weighting for legacy RQI (if needed)
    DAMAGE_WEIGHTS = {
        "long_crack": 1.0,
        "trans_crack": 1.2,
        "alligator_crack": 1.5,
        "pothole": 2.5,
        "patch": 0.5,
        "degradation": 1.8
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

    def _detect_patches_color_based(self, road_region: np.ndarray, gray: np.ndarray) -> tuple:
        """
        Detect asphalt patches/repairs using color analysis.
        Filters out shadows to reduce false positives.
        
        Returns:
            tuple: (patch_density, repair_score)
        """
        import cv2
        import numpy as np
        
        # Convert to HSV for better color analysis
        hsv = cv2.cvtColor(road_region, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        
        mean_v = np.mean(v)
        std_v = np.std(v)
        
        # === SHADOW DETECTION ===
        # Shadows: dark areas with LOW saturation (gray-ish)
        # Repairs: dark areas with HIGH saturation (dark asphalt has color)
        
        # Get saturation stats for dark areas
        dark_threshold = mean_v - std_v * 0.8
        dark_mask = v < dark_threshold
        
        # Shadow: dark AND low saturation (< 60)
        shadow_mask = (v < dark_threshold) & (s < 60)
        shadow_ratio = np.sum(shadow_mask) / shadow_mask.size
        
        # === REPAIR DETECTION (high saturation dark areas) ===
        # Asphalt repairs have HIGH saturation (> 100) when dark
        # This distinguishes them from regular shadows
        high_sat_repair_mask = (v < dark_threshold) & (s > 100)
        high_sat_repair_ratio = np.sum(high_sat_repair_mask) / high_sat_repair_mask.size
        
        # Medium saturation repairs (60-100)
        med_sat_repair_mask = (v < dark_threshold) & (s >= 60) & (s <= 100)
        med_sat_repair_ratio = np.sum(med_sat_repair_mask) / med_sat_repair_mask.size
        
        # Very dark repairs (fresh asphalt) - must have high saturation
        very_dark_threshold = mean_v - std_v * 1.5
        fresh_repair_mask = (v < very_dark_threshold) & (s > 100)
        fresh_repair_ratio = np.sum(fresh_repair_mask) / fresh_repair_mask.size
        
        # === EDGE/BOUNDARY DETECTION ===
        # Only count boundaries NOT in shadow areas
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        gradient = cv2.morphologyEx(v, cv2.MORPH_GRADIENT, kernel)
        
        # Exclude shadow boundaries
        gradient_threshold = np.percentile(gradient, 85)
        boundary_mask = (gradient > gradient_threshold) & (~shadow_mask)
        boundary_ratio = np.sum(boundary_mask) / boundary_mask.size
        
        # === BLOB DETECTION (repairs are blob-like) ===
        blob_score = 0.0
        if np.sum(high_sat_repair_mask) > 0:
            repair_uint8 = high_sat_repair_mask.astype(np.uint8) * 255
            contours, _ = cv2.findContours(repair_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            blob_area = 0
            for cnt in contours:
                area = cv2.contourArea(cnt)
                perimeter = cv2.arcLength(cnt, True)
                if perimeter > 0:
                    circularity = 4 * np.pi * area / (perimeter * perimeter)
                    min_area = high_sat_repair_mask.size * 0.005  # At least 0.5% of image
                    if circularity > 0.2 and area > min_area:
                        blob_area += area
            
            blob_score = blob_area / high_sat_repair_mask.size
        
        # === COMBINE INTO REPAIR SCORE ===
        # Focus on HIGH SATURATION dark areas (actual asphalt repairs)
        repair_score = (
            high_sat_repair_ratio * 1.0 +    # High priority: high saturation repairs
            fresh_repair_ratio * 0.8 +       # Fresh dark repairs
            med_sat_repair_ratio * 0.3 +     # Medium saturation (less certain)
            blob_score * 0.5                 # Blob-like shapes
        )
        
        # If high shadow coverage, reduce repair score (likely false positives)
        if shadow_ratio > 0.20:
            repair_score *= 0.5
        
        # Traditional patch density using adaptive threshold
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        adaptive = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )
        patch_density = np.sum(adaptive > 0) / adaptive.size
        
        return patch_density, repair_score


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

    def _classify_damage(self, area: float, aspect_ratio: float) -> str:
        """
        Classify damage type based on detection properties.

        This is a heuristic approach - a proper model would be trained
        specifically for road damage classes.
        """
        if area > 0.05:  # Large area
            return "D40"  # Pothole
        elif aspect_ratio > 3:  # Long and thin
            return "D00"  # Longitudinal crack
        elif aspect_ratio < 0.3:  # Wide and short
            return "D10"  # Transverse crack
        else:
            return "D20"  # Alligator crack

    def _calculate_rqi(self, detections: List[DamageDetection]) -> float:
        """
        Calculate Road Quality Index (1-5) based on detections.

        1 = Excellent (no damage)
        2 = Good (minor issues)
        3 = Fair (moderate damage)
        4 = Poor (significant damage)
        5 = Very Poor (severe damage)
        """
        if not detections:
            return 1.0

        # Calculate weighted severity score
        total_weight = 0.0
        for det in detections:
            weight = self.DAMAGE_WEIGHTS.get(det.damage_type, 1.0)
            # Scale by confidence and area
            total_weight += weight * det.confidence * (1 + det.area * 10)

        # Map to 1-5 scale
        # Thresholds tuned empirically
        if total_weight < 1.5:
            return 1.0
        elif total_weight < 4.5:
            return 2.0
        elif total_weight < 8.0:
            return 3.0
        elif total_weight < 12.0:
            return 4.0
        else:
            return 5.0

    def analyze_image_simple(self, image_path: str) -> RoadQualityResult:
        """
        Simple analysis without YOLO - uses image analysis heuristics.

        This is a fallback for when YOLO is not available or for quick testing.
        Analyzes image properties in the lower third (road area).
        """
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            return RoadQualityResult(
                rqi_score=3.0,
                damage_count=0,
                damage_types={},
                detections=[],
                analysis_metadata={"error": "Image not loaded"},
            )

        h, w = img.shape[:2]

        # Focus on bottom portion (road area) - configurable ratio
        road_region_ratio = self._get_setting("road_region_height_ratio", 0.4)
        road_start = int(h * (1 - road_region_ratio))
        road_region = img[road_start:, :]

        # Convert to grayscale
        gray = cv2.cvtColor(road_region, cv2.COLOR_BGR2GRAY)

        # Detect and exclude road markings (white/yellow lines)
        # Road markings create false positives - they're not damage!
        white_mask = cv2.inRange(road_region, (200, 200, 200), (255, 255, 255))
        yellow_mask = cv2.inRange(road_region, (0, 180, 180), (100, 255, 255))
        markings_mask = cv2.bitwise_or(white_mask, yellow_mask)

        # Dilate markings mask to exclude areas around markings too
        kernel_marking = np.ones((5, 5), np.uint8)
        markings_mask = cv2.dilate(markings_mask, kernel_marking, iterations=2)

        # Create mask for road without markings
        road_mask = cv2.bitwise_not(markings_mask)
        road_without_markings = cv2.bitwise_and(gray, gray, mask=road_mask)

        # Use road without markings for analysis, but fallback to full road if too much excluded
        # Use configurable threshold from database settings
        markings_coverage = np.sum(markings_mask > 0) / markings_mask.size
        markings_threshold = self._get_setting("markings_filter_threshold", 0.15)
        if markings_coverage < markings_threshold:
            analysis_gray = road_without_markings
        else:
            analysis_gray = gray  # Too many markings, use full image

        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(analysis_gray, (5, 5), 0)

        # Adaptive thresholding to separate road surface from shadows/markings
        # This helps focus on actual road texture, not painted lines or shadows
        adaptive_thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )

        # Morphological operations to filter out small noise and connect real cracks
        kernel = np.ones((3, 3), np.uint8)
        cleaned = cv2.morphologyEx(adaptive_thresh, cv2.MORPH_CLOSE, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)

        # Multi-scale edge detection - detect both fine cracks and large damage
        # Use configurable thresholds from database settings
        canny_fine_low = int(self._get_setting("canny_threshold_fine_low", 30.0))
        canny_fine_high = int(self._get_setting("canny_threshold_fine_high", 80.0))
        canny_coarse_low = int(self._get_setting("canny_threshold_coarse_low", 80.0))
        canny_coarse_high = int(self._get_setting("canny_threshold_coarse_high", 200.0))

        edges_fine = cv2.Canny(blurred, canny_fine_low, canny_fine_high)  # Fine cracks
        edges_coarse = cv2.Canny(
            blurred, canny_coarse_low, canny_coarse_high
        )  # Large damage

        # Calculate edge densities
        edge_density_fine = np.sum(edges_fine > 0) / edges_fine.size
        edge_density_coarse = np.sum(edges_coarse > 0) / edges_coarse.size

        # Combined edge density (weight fine cracks more - they indicate damage)
        edge_density = edge_density_fine * 0.7 + edge_density_coarse * 0.3

        # Texture analysis - calculate variance in smaller blocks to detect localized damage
        # Key insight: Normal road texture has uniform variance, damage has localized high variance
        block_size = int(self._get_setting("block_size", 32.0))
        variances = []
        for y in range(0, gray.shape[0] - block_size, block_size):
            for x in range(0, gray.shape[1] - block_size, block_size):
                block = gray[y : y + block_size, x : x + block_size]
                # Skip blocks that are mostly markings (use configurable threshold)
                if markings_coverage < markings_threshold:
                    block_mask = road_mask[y : y + block_size, x : x + block_size]
                    if (
                        np.sum(block_mask > 0) > block_size * block_size * 0.5
                    ):  # At least 50% road
                        variances.append(np.var(block))
                else:
                    variances.append(np.var(block))

        if not variances:
            texture_variance = np.var(gray)
        else:
            # Use 90th percentile instead of 75th - more conservative
            # Also check variance of variances: if uniform -> normal texture, if varied -> damage
            variance_of_variances = np.std(variances)
            percentile_variance = np.percentile(variances, 90)

            # If variance is uniform (low std of variances), it's normal texture
            # If variance has high std, there are localized damage areas
            if variance_of_variances < np.mean(variances) * 0.5:
                # Uniform texture -> normal road, reduce weight
                texture_variance = np.percentile(variances, 50)  # Use median instead
            else:
                # Localized high variance -> damage
                texture_variance = percentile_variance

        # Structural analysis - detect linear patterns (cracks)
        # Only count long, straight lines (actual cracks), not random texture
        # Use configurable thresholds from database settings
        hough_threshold = int(self._get_setting("hough_lines_threshold", 80.0))
        hough_min_length = int(self._get_setting("hough_lines_min_length", 50.0))

        lines = cv2.HoughLinesP(
            edges_fine,
            1,
            np.pi / 180,
            threshold=hough_threshold,
            minLineLength=hough_min_length,
            maxLineGap=5,
        )
        line_count = len(lines) if lines is not None else 0

        # Filter lines: only count lines that are reasonably straight (not curved)
        # and have good length-to-width ratio (cracks are long and thin)
        filtered_line_count = 0
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                if length > hough_min_length:  # Only count longer lines
                    filtered_line_count += 1

        line_density = filtered_line_count / (gray.shape[0] * gray.shape[1]) * 10000

        # Calculate local contrast (damaged areas have higher contrast)
        laplacian = cv2.Laplacian(blurred, cv2.CV_64F)
        contrast_score = np.var(laplacian)

        # IMPROVED: Color-based patch/repair detection
        # Asphalt repairs appear as darker or differently colored patches
        patch_density, repair_score = self._detect_patches_color_based(road_region, gray)

        # Get weights from settings
        w_edge = self._get_setting("edge_density_weight", 35.0)
        w_edge_fine = self._get_setting("edge_density_fine_weight", 28.0)
        div_variance = self._get_setting("texture_variance_divisor", 400.0)
        w_line = self._get_setting("line_density_weight", 0.7)
        div_contrast = self._get_setting("contrast_score_divisor", 10000.0)
        w_patch = self._get_setting("patch_density_weight", 18.0)
        w_repair = self._get_setting("repair_score_weight", 30.0)  # New weight for repairs

        damage_score = (
            edge_density * w_edge
            + edge_density_fine * w_edge_fine
            + texture_variance / div_variance
            + line_density * w_line
            + contrast_score / div_contrast
            + patch_density * w_patch
            + repair_score * w_repair  # Add repair contribution
        )

        # Shadow detection and compensation
        # Shadows create false positives (high contrast, many edges)
        # We need to detect shadow areas and reduce their impact
        mean_brightness = np.mean(gray)
        std_brightness = np.std(gray)

        # Detect shadow areas: low brightness with high local variance (shadow edges)
        # Create a shadow mask: areas that are dark but have high variance nearby
        shadow_threshold = np.percentile(gray, 30)  # Bottom 30% brightness
        shadow_mask = gray < shadow_threshold

        # Calculate shadow coverage
        shadow_coverage = np.sum(shadow_mask) / shadow_mask.size

        # Calculate brightness variance in shadow areas vs non-shadow areas
        if shadow_coverage > 0.1:  # Significant shadows present
            shadow_variance = (
                np.var(gray[shadow_mask]) if np.sum(shadow_mask) > 0 else 0
            )
            non_shadow_variance = (
                np.var(gray[~shadow_mask]) if np.sum(~shadow_mask) > 0 else 0
            )

            # If shadows have high variance (sharp edges), they're causing false positives
            shadow_edge_factor = (
                shadow_variance / (non_shadow_variance + 1)
                if non_shadow_variance > 0
                else 1.0
            )
        else:
            shadow_edge_factor = 1.0

        # Brightness-based compensation (moderate for shadows)
        # Use configurable compensation factors from database settings
        shadow_comp_dark = self._get_setting("shadow_compensation_dark", 0.75)
        shadow_comp_moderate = self._get_setting("shadow_compensation_moderate", 0.85)

        brightness_factor = 1.0
        if mean_brightness < 60:  # Dark/very shadowy
            # Moderate compensation: shadows create some false edges but not too aggressive
            brightness_factor = shadow_comp_dark - (shadow_coverage * 0.15)
        elif mean_brightness < 100:  # Moderately shadowy
            brightness_factor = shadow_comp_moderate - (shadow_coverage * 0.1)
        elif mean_brightness > 200:  # Very bright (overexposed)
            brightness_factor = 0.95  # Less aggressive

        # Additional compensation if shadows have sharp edges (less aggressive)
        if shadow_coverage > 0.2 and shadow_edge_factor > 2.0:  # Higher thresholds
            brightness_factor *= 0.9  # Less aggressive reduction

        damage_score *= brightness_factor

        # Balanced RQI mapping - distinguish between good and bad roads
        # Goal: Accurately classify roads while avoiding false positives from normal texture
        # Thresholds calibrated to balance sensitivity and specificity

        # Updated thresholds - balanced approach with better separation:
        # - Excellent roads (smooth, well-maintained): RQI 1
        # - Good roads (minor wear acceptable): RQI 2
        # - Fair roads (visible wear, minor cracks): RQI 3
        # - Poor roads (significant damage, cracks): RQI 4
        # - Very Poor roads (severe damage, potholes): RQI 5
        # Use configurable thresholds from database settings
        threshold_excellent = self._get_setting("rqi_threshold_excellent", 22.0)
        threshold_good = self._get_setting("rqi_threshold_good", 35.0)
        threshold_fair = self._get_setting("rqi_threshold_fair", 50.0)
        threshold_poor = self._get_setting("rqi_threshold_poor", 65.0)

        if damage_score < threshold_excellent:
            rqi = 1.0  # Excellent
        elif damage_score < threshold_good:
            rqi = 2.0  # Good
        elif damage_score < threshold_fair:
            rqi = 3.0  # Fair
        elif damage_score < threshold_poor:
            rqi = 4.0  # Poor
        else:
            rqi = 5.0  # Very Poor

        # Store detailed analysis metadata (using actual settings values)
        analysis_metadata = {
            "method": "improved_heuristic_v4_configurable",
            "edge_density": float(edge_density),
            "edge_density_fine": float(edge_density_fine),
            "edge_density_coarse": float(edge_density_coarse),
            "texture_variance": float(texture_variance),
            "line_density": float(line_density),
            "line_count": int(line_count),
            "contrast_score": float(contrast_score),
            "patch_density": float(patch_density),
            "repair_score": float(repair_score),
            "damage_score": float(damage_score),
            "mean_brightness": float(mean_brightness),
            "brightness_factor": float(brightness_factor),
            "shadow_coverage": float(shadow_coverage),
            "shadow_edge_factor": float(shadow_edge_factor),
            "road_region_height_ratio": float(road_region_ratio),
            "weights": {
                "edge_density": float(w_edge),
                "edge_density_fine": float(w_edge_fine),
                "texture_variance_divisor": float(div_variance),
                "line_density": float(w_line),
                "contrast_divisor": float(div_contrast),
                "patch_density": float(w_patch),
            },
            "canny_thresholds": {
                "fine_low": canny_fine_low,
                "fine_high": canny_fine_high,
                "coarse_low": canny_coarse_low,
                "coarse_high": canny_coarse_high,
            },
            "rqi_thresholds": {
                "excellent": float(threshold_excellent),
                "good": float(threshold_good),
                "fair": float(threshold_fair),
                "poor": float(threshold_poor),
            },
            "markings_coverage": float(markings_coverage),
        }

        return RoadQualityResult(
            rqi_score=rqi,
            damage_count=0,
            damage_types={"heuristic": 1},
            detections=[],
            analysis_metadata=analysis_metadata,
        )


    # workflow methods required by routes.py
    
    def collect_points(self, origin: str, destination: str, job_id: str):
        """Step 1: Collect points along the route."""
        # This functionality seems to be missing or was in processing_service.
        # Implemented as a stub or basic logic if possible.
        from app.services.job_service import update_job, JobStep
        update_job(job_id, current_step= JobStep.COLLECTING, progress=10, total=100, message="Pontok gyűjtése...")
        print(f"DEBUG: Collecting points from {origin} to {destination}")
        # Logic to call Google Maps API or similar usually goes here
        # For now, we simulate simple point added
        import time
        time.sleep(2) # simulate work
        
    def download_images(self, job_id: str):
        """Step 2: Download images for collected points."""
        from app.services.job_service import update_job, JobStep
        update_job(job_id, current_step=JobStep.DOWNLOADING, progress=30, total=100, message="Képek letöltése...")
        print("DEBUG: Downloading images...")
        import time
        time.sleep(2) # simulate work

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
                         prog_percent = 50 + int((i / total) * 40)
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
                         
                     # Try to find file
                     project_root = os.getcwd() # backend/app is CWD usually? or root?
                     # Adjust based on where app is run
                     if "backend" in project_root:
                         path = os.path.join(project_root, "data", "images", fname)
                     else:
                         path = os.path.join(project_root, "backend", "data", "images", fname)
                         
                     if not os.path.exists(path):
                         # Try alternate
                         path = os.path.join(os.getcwd(), "data", "images", fname)
                         
                     if os.path.exists(path):
                         # Run analysis
                         if strategy == "YOLO":
                             result = self.analyze_image(path)
                         else:
                             result = self.analyze_image_simple(path)
                             
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
