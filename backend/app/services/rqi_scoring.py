"""
Pure road-quality scoring types and helpers (no torch, no DB, no I/O).

Kept dependency-free so the damage taxonomy and the damage%→RQI mapping can be
unit-tested in isolation and reused by the analyzer without importing YOLO.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Pipeline 2.0 taxonomy — YOLO class id -> short code.
DAMAGE_CLASSES: Dict[int, str] = {
    0: "long_crack",
    1: "trans_crack",
    2: "alligator_crack",
    3: "pothole",
    4: "patch",
    5: "degradation",
    6: "shadow",
    7: "manhole",
    8: "marking",
}

DAMAGE_NAMES: Dict[str, str] = {
    "long_crack": "Longitudinal Crack",
    "trans_crack": "Transverse Crack",
    "alligator_crack": "Alligator Crack",
    "pothole": "Pothole",
    "patch": "Asphalt Patch",
    "degradation": "Surface Degradation",
    "shadow": "Shadow",
    "manhole": "Manhole",
    "marking": "Road Marking",
}

# Class ids 0..5 are actual damage; 6..8 (shadow/manhole/marking) are ignored
# for the damage ratio.
MAX_DAMAGE_CLASS_ID = 5


@dataclass
class DamageDetection:
    """A single detected road damage."""

    damage_type: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2
    area: float  # relative area (0-1)


@dataclass
class RoadQualityResult:
    """Result of a road-quality analysis for one image."""

    rqi_score: float  # 1-5 scale (lower = better)
    damage_count: int
    damage_types: Dict[str, int]  # {type: count}
    detections: List[DamageDetection]
    analysis_metadata: Optional[Dict] = None  # e.g. {"damage_percent": ...}


def rqi_from_damage_percent(damage_percent: float) -> float:
    """Map the share of road area that is damaged (%) to an RQI score (1-5)."""
    if damage_percent < 0.5:
        return 1.0
    if damage_percent < 2.0:
        return 2.0
    if damage_percent < 5.0:
        return 3.0
    if damage_percent < 10.0:
        return 4.0
    return 5.0
