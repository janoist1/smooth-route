"""
Road Quality Analysis Service using YOLO for damage detection.
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json
import cv2
import numpy as np


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

    # RDD2020 class names (Road Damage Dataset)
    DAMAGE_CLASSES = {
        0: "D00",  # Longitudinal Crack
        1: "D10",  # Transverse Crack
        2: "D20",  # Alligator Crack
        3: "D40",  # Pothole
    }

    DAMAGE_NAMES = {
        "D00": "Longitudinal Crack",
        "D10": "Transverse Crack",
        "D20": "Alligator Crack",
        "D40": "Pothole",
    }

    # Severity weights for RQI calculation
    DAMAGE_WEIGHTS = {
        "D00": 1.0,  # Minor
        "D10": 1.2,  # Moderate
        "D20": 1.5,  # Significant
        "D40": 2.5,  # Severe (pothole)
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
        """Lazy load the YOLO model."""
        if self._loaded:
            return

        from ultralytics import YOLO
        import os
        from app.core.config import settings

        # Determine model path
        actual_model_path = self.model_path
        
        if not actual_model_path:
            # Check for high-priority trained model in data directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            trained_model = os.path.join(project_root, "data", "models", "trained_yolo.pt")
            
            if os.path.exists(trained_model):
                actual_model_path = trained_model
                print(f"Using trained YOLO model: {trained_model}")
            else:
                actual_model_path = "yolov8m.pt"
                print(f"Using default YOLO model: {actual_model_path}")

        self.model = YOLO(actual_model_path)
        self._loaded = True
        print(f"Model loaded. Device: {self.model.device}")

    def analyze_image(
        self, image_path: str, confidence_threshold: float = 0.25
    ) -> RoadQualityResult:
        """
        Analyze a single image for road damage.

        Args:
            image_path: Path to the image file.
            confidence_threshold: Minimum confidence for detections.

        Returns:
            RoadQualityResult with RQI score and damage details.
        """
        self._load_model()

        # Run inference
        results = self.model(image_path, conf=confidence_threshold, verbose=False)

        # Process detections
        detections = []
        damage_counts: Dict[str, int] = {}

        for result in results:
            if result.boxes is None:
                continue

            img_h, img_w = result.orig_shape
            img_area = img_h * img_w

            for box in result.boxes:
                # Get box coordinates
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])

                # Calculate relative area
                box_area = (x2 - x1) * (y2 - y1)
                rel_area = box_area / img_area

                # For now, classify bottom-third detections as potential road damage
                # (Street View images show road at bottom)
                if y1 > img_h * 0.5:  # Detection in lower half
                    # Map to damage type based on shape/size heuristics
                    damage_type = self._classify_damage(
                        rel_area, (x2 - x1) / (y2 - y1 + 0.001)
                    )

                    detections.append(
                        DamageDetection(
                            damage_type=damage_type,
                            confidence=conf,
                            bbox=(x1, y1, x2, y2),
                            area=rel_area,
                        )
                    )

                    damage_counts[damage_type] = damage_counts.get(damage_type, 0) + 1

        # Calculate RQI
        rqi_score = self._calculate_rqi(detections)

        return RoadQualityResult(
            rqi_score=rqi_score,
            damage_count=len(detections),
            damage_types=damage_counts,
            detections=detections,
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


# Singleton instance
road_quality_service = RoadQualityService()
