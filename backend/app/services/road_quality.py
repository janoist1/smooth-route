"""
Road Quality Analysis Service using YOLO for damage detection.
"""
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import json

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
    analysis_metadata: Optional[Dict] = None  # Contains edge_density, variance, damage_score, etc.
    
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
        "D00": 1.0,   # Minor
        "D10": 1.5,   # Moderate
        "D20": 2.0,   # Significant
        "D40": 3.0,   # Severe (pothole)
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
        
    def _load_model(self):
        """Lazy load the YOLO model."""
        if self._loaded:
            return
            
        from ultralytics import YOLO
        
        if self.model_path:
            self.model = YOLO(self.model_path)
        else:
            # Use YOLOv8 nano as base - we'll detect general damage patterns
            # For production, you'd use a fine-tuned RDD model
            self.model = YOLO("yolov8n.pt")
            
        self._loaded = True
        print(f"Model loaded. Device: {self.model.device}")
        
    def analyze_image(self, image_path: str, confidence_threshold: float = 0.25) -> RoadQualityResult:
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
                    damage_type = self._classify_damage(rel_area, (x2-x1)/(y2-y1+0.001))
                    
                    detections.append(DamageDetection(
                        damage_type=damage_type,
                        confidence=conf,
                        bbox=(x1, y1, x2, y2),
                        area=rel_area
                    ))
                    
                    damage_counts[damage_type] = damage_counts.get(damage_type, 0) + 1
        
        # Calculate RQI
        rqi_score = self._calculate_rqi(detections)
        
        return RoadQualityResult(
            rqi_score=rqi_score,
            damage_count=len(detections),
            damage_types=damage_counts,
            detections=detections
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
        if total_weight < 1:
            return 1.0
        elif total_weight < 3:
            return 2.0
        elif total_weight < 6:
            return 3.0
        elif total_weight < 10:
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
                analysis_metadata={"error": "Image not loaded"}
            )
        
        h, w = img.shape[:2]
        
        # Focus on bottom 40% (road area) - more conservative than before
        road_start = int(h * 0.6)
        road_region = img[road_start:, :]
        
        # Convert to grayscale
        gray = cv2.cvtColor(road_region, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
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
        # Lower thresholds to catch fine cracks, but filter noise
        edges_fine = cv2.Canny(blurred, 30, 80)   # Fine cracks
        edges_coarse = cv2.Canny(blurred, 80, 200)  # Large damage
        
        # Calculate edge densities
        edge_density_fine = np.sum(edges_fine > 0) / edges_fine.size
        edge_density_coarse = np.sum(edges_coarse > 0) / edges_coarse.size
        
        # Combined edge density (weight fine cracks more - they indicate damage)
        edge_density = edge_density_fine * 0.7 + edge_density_coarse * 0.3
        
        # Texture analysis - calculate variance in smaller blocks to detect localized damage
        block_size = 32
        variances = []
        for y in range(0, gray.shape[0] - block_size, block_size):
            for x in range(0, gray.shape[1] - block_size, block_size):
                block = gray[y:y+block_size, x:x+block_size]
                variances.append(np.var(block))
        
        # Use 75th percentile variance (more sensitive to damaged areas)
        # This catches localized damage better than median
        texture_variance = np.percentile(variances, 75) if variances else np.var(gray)
        
        # Structural analysis - detect linear patterns (cracks)
        # Use HoughLinesP with higher threshold to reduce false positives
        lines = cv2.HoughLinesP(edges_fine, 1, np.pi/180, threshold=50, minLineLength=30, maxLineGap=10)
        line_count = len(lines) if lines is not None else 0
        line_density = line_count / (gray.shape[0] * gray.shape[1]) * 10000  # Reduced normalization factor
        
        # Calculate local contrast (damaged areas have higher contrast)
        laplacian = cv2.Laplacian(blurred, cv2.CV_64F)
        contrast_score = np.var(laplacian)
        
        # Detect patches/repairs (areas with different texture)
        # Use adaptive thresholding to find patches
        adaptive = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                         cv2.THRESH_BINARY_INV, 11, 2)
        patch_density = np.sum(adaptive > 0) / adaptive.size
        
        # Combined damage score with balanced weighting
        # Reduced weights to avoid false positives while still detecting real damage
        damage_score = (
            edge_density * 30 +              # Reduced weight on edges
            edge_density_fine * 20 +         # Reduced weight on fine cracks
            texture_variance / 500 +         # Reduced sensitivity to texture variance
            line_density * 0.5 +             # Significantly reduced weight on structural damage
            contrast_score / 15000 +         # Reduced weight on contrast
            patch_density * 15               # Reduced weight on patch detection
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
            shadow_variance = np.var(gray[shadow_mask]) if np.sum(shadow_mask) > 0 else 0
            non_shadow_variance = np.var(gray[~shadow_mask]) if np.sum(~shadow_mask) > 0 else 0
            
            # If shadows have high variance (sharp edges), they're causing false positives
            shadow_edge_factor = shadow_variance / (non_shadow_variance + 1) if non_shadow_variance > 0 else 1.0
        else:
            shadow_edge_factor = 1.0
        
        # Brightness-based compensation (more aggressive for shadows)
        brightness_factor = 1.0
        if mean_brightness < 60:  # Dark/very shadowy
            # Strong compensation: shadows create many false edges
            brightness_factor = 0.65 - (shadow_coverage * 0.2)  # More shadows = more compensation
        elif mean_brightness < 100:  # Moderately shadowy
            brightness_factor = 0.75 - (shadow_coverage * 0.15)
        elif mean_brightness > 200:  # Very bright (overexposed)
            brightness_factor = 0.9
        
        # Additional compensation if shadows have sharp edges
        if shadow_coverage > 0.15 and shadow_edge_factor > 1.5:
            brightness_factor *= 0.85  # Extra reduction for sharp shadow edges
        
        damage_score *= brightness_factor
        
        # Quantile-based RQI mapping
        # This adapts to the actual distribution of damage scores in the dataset
        # Thresholds are based on percentiles: 25%, 50%, 75%, 90%
        # This ensures a more balanced distribution across RQI levels
        # These thresholds are calibrated based on analysis of 1098 points
        # where median damage_score = 21.68, 75th percentile = 26.65
        
        # Using percentiles ensures:
        # - RQI 1: Top 25% best roads (damage_score < 15.1)
        # - RQI 2: Next 25% (15.1 <= damage_score < 21.7)
        # - RQI 3: Next 25% (21.7 <= damage_score < 26.7)
        # - RQI 4: Next 15% (26.7 <= damage_score < 35)
        # - RQI 5: Worst 10% (damage_score >= 35)
        
        if damage_score < 15.1:  # 25th percentile
            rqi = 1.0  # Excellent (top 25% - truly smooth roads)
        elif damage_score < 21.7:  # 50th percentile (median)
            rqi = 2.0  # Good (next 25% - minor issues)
        elif damage_score < 26.7:  # 75th percentile
            rqi = 3.0  # Fair (next 25% - visible wear)
        elif damage_score < 35.0:  # ~90th percentile (estimated)
            rqi = 4.0  # Poor (next 15% - significant damage)
        else:
            rqi = 5.0  # Very Poor (worst 10% - severe damage)
        
        # Store detailed analysis metadata
        analysis_metadata = {
            "method": "improved_heuristic_v2",
            "edge_density": float(edge_density),
            "edge_density_fine": float(edge_density_fine),
            "edge_density_coarse": float(edge_density_coarse),
            "texture_variance": float(texture_variance),
            "line_density": float(line_density),
            "line_count": int(line_count),
            "contrast_score": float(contrast_score),
            "patch_density": float(patch_density),
            "damage_score": float(damage_score),
            "mean_brightness": float(mean_brightness),
            "brightness_factor": float(brightness_factor),
            "shadow_coverage": float(shadow_coverage),
            "shadow_edge_factor": float(shadow_edge_factor),
            "road_region_height_ratio": 0.4,  # Bottom 40% of image
            "canny_threshold_fine_low": 30,
            "canny_threshold_fine_high": 80,
            "canny_threshold_coarse_low": 80,
            "canny_threshold_coarse_high": 200,
            "rqi_thresholds": {
                "excellent": 15.1,  # 25th percentile
                "good": 21.7,      # 50th percentile (median)
                "fair": 26.7,      # 75th percentile
                "poor": 35.0       # ~90th percentile
            },
            "method_note": "quantile_based_normalization"
        }
            
        return RoadQualityResult(
            rqi_score=rqi,
            damage_count=0,
            damage_types={"heuristic": 1},
            detections=[],
            analysis_metadata=analysis_metadata
        )


# Singleton instance
road_quality_service = RoadQualityService()
