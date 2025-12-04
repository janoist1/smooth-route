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
                detections=[]
            )
        
        h, w = img.shape[:2]
        
        # Focus on bottom third (road area)
        road_region = img[int(h*0.6):, :]
        
        # Convert to grayscale
        gray = cv2.cvtColor(road_region, cv2.COLOR_BGR2GRAY)
        
        # Edge detection (cracks/damage show as edges)
        edges = cv2.Canny(gray, 50, 150)
        
        # Calculate edge density
        edge_density = np.sum(edges > 0) / edges.size
        
        # Texture analysis - high variance indicates rough/damaged surface
        variance = np.var(gray)
        
        # Simple heuristic scoring
        damage_score = edge_density * 100 + variance / 1000
        
        # Map to RQI
        if damage_score < 5:
            rqi = 1.0
        elif damage_score < 10:
            rqi = 2.0
        elif damage_score < 20:
            rqi = 3.0
        elif damage_score < 35:
            rqi = 4.0
        else:
            rqi = 5.0
            
        return RoadQualityResult(
            rqi_score=rqi,
            damage_count=0,
            damage_types={"heuristic": 1},
            detections=[]
        )


# Singleton instance
road_quality_service = RoadQualityService()
