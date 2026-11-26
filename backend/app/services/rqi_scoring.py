"""
Pure road-quality scoring types and helpers (no torch, no DB, no I/O).

Kept dependency-free so the damage taxonomy and the damage%→RQI mapping can be
unit-tested in isolation and reused by the analyzer without importing YOLO.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.rqi_scale import SCALE

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

    rqi_score: float  # canonical RQI level (app.core.rqi_scale), all 5 levels
    damage_count: int
    damage_types: Dict[str, int]  # {type: count}
    detections: List[DamageDetection]
    analysis_metadata: Optional[Dict] = None  # e.g. {"damage_percent": ...}


# Upper damage% bound of each band, best band first (severity 1..4); anything
# at or above the last bound is the worst level (severity 5).
DAMAGE_PERCENT_BANDS = (0.5, 2.0, 5.0, 10.0)


def rqi_from_damage_percent(damage_percent: float) -> float:
    """Map the share of road area that is damaged (%) to an RQI level.

    The bands are defined in severity order (1 = least damage) and converted
    to the canonical scale, so a direction flip needs no change here.
    """
    severity = len(DAMAGE_PERCENT_BANDS) + 1
    for i, upper in enumerate(DAMAGE_PERCENT_BANDS):
        if damage_percent < upper:
            severity = i + 1
            break
    return float(SCALE.from_severity(severity))
