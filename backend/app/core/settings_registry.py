"""Schema for every supported analysis setting."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    value_type: type
    default: Any
    category: str
    consumer: str


def _definition(
    key: str,
    value_type: type,
    default: Any,
    category: str,
    consumer: str,
) -> SettingDefinition:
    return SettingDefinition(key, value_type, default, category, consumer)


SETTING_REGISTRY = {
    definition.key: definition
    for definition in [
        _definition(
            "yolo_model",
            str,
            "yolov8m-seg-best-20260105.pt",
            "YOLO (Objektum Detektálás)",
            "InferenceService, RoadDamageAnalyzer, TrainingService",
        ),
        _definition(
            "yolo_cleaner_model",
            str,
            "yolov8m-seg.pt",
            "YOLO (Objektum Detektálás)",
            "InferenceService",
        ),
        _definition(
            "yolo_cleaner_conf",
            float,
            0.25,
            "YOLO (Objektum Detektálás)",
            "InferenceService",
        ),
        _definition(
            "yolo_inference_conf",
            float,
            0.15,
            "YOLO (Objektum Detektálás)",
            "InferenceService, RoadDamageAnalyzer",
        ),
        _definition(
            "yolo_training_epochs",
            int,
            50,
            "Tanítás - YOLO",
            "TrainingService",
        ),
        _definition(
            "yolo_training_batch_size",
            int,
            16,
            "Tanítás - YOLO",
            "TrainingService",
        ),
        _definition(
            "yolo_training_patience",
            int,
            50,
            "Tanítás - YOLO",
            "TrainingService",
        ),
        _definition(
            "training_provider",
            str,
            "local",
            "Tanítás - Általános",
            "TrainingService",
        ),
        _definition(
            "training_workers",
            int,
            4,
            "Tanítás - Általános",
            "TrainingService",
        ),
        _definition(
            "fastsam_model",
            str,
            "FastSAM-s.pt",
            "YOLO tanítóadat-diagnosztika",
            "RoadPreprocessor",
        ),
        _definition(
            "google_maps_pitch",
            int,
            -20,
            "Google Street View",
            "GoogleMapsService",
        ),
        _definition(
            "rqi_display_source",
            str,
            "dino",
            "Megjelenítés",
            "GraphQL map/training queries",
        ),
    ]
}
