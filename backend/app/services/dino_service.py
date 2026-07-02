"""
RQI inference service (clean pipeline).

Wraps the frozen DINOv2-small backbone + trained ordinal head produced by the
`ml/` pipeline (see ml/README.md). The artifact is a scikit-learn Pipeline
(StandardScaler + Ridge) saved at ml/cache/rqi_model.joblib.

Cross-validated quality: MAE 0.30, ±1 acc 99.6%, QWK 0.83 (RQI 1-4, lower=better).

Public interface is unchanged: `dino_service.predict_rqi(image_path) -> Optional[int]`.
Images are scored RAW (no vehicle masking / sky crop) to match how the head was
trained.
"""
import os
from typing import Optional

import numpy as np
import torch
from PIL import Image


def _project_root() -> str:
    services_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(services_dir)
    backend_dir = os.path.dirname(app_dir)
    return os.path.dirname(backend_dir)


MODEL_PATH = os.path.join(_project_root(), "ml", "cache", "rqi_model.joblib")


class DinoInferenceService:
    def __init__(self):
        self.device = self._get_device()
        self.backbone = None
        self.processor = None
        self.pipeline = None          # sklearn scaler+ridge
        self.rqi_clip = (1, 4)
        self._loaded = False

    def _get_device(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def load_model(self):
        """Lazy-load the joblib artifact + DINOv2 backbone once."""
        if self._loaded:
            return
        import joblib
        from transformers import AutoImageProcessor, AutoModel

        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                f"RQI model not found at {MODEL_PATH}. "
                f"Train it with: .venv/bin/python ml/save_model.py"
            )

        artifact = joblib.load(MODEL_PATH)
        self.pipeline = artifact["pipeline"]
        self.rqi_clip = tuple(artifact.get("rqi_clip", (1, 4)))
        backbone_name = artifact.get("backbone", "facebook/dinov2-small")

        print(f"DinoInferenceService: loading {backbone_name} on {self.device} "
              f"(head trained on {artifact.get('n_train', '?')} images)")
        self.processor = AutoImageProcessor.from_pretrained(backbone_name)
        self.backbone = AutoModel.from_pretrained(backbone_name).to(self.device).eval()
        self._loaded = True

    @torch.no_grad()
    def predict_score(self, image_path: str) -> Optional[float]:
        """Continuous RQI estimate (1.0-4.0), or None on failure."""
        try:
            self.load_model()
            img = Image.open(image_path).convert("RGB")
            inp = self.processor(images=img, return_tensors="pt").to(self.device)
            feat = self.backbone(**inp).pooler_output.float().cpu().numpy()
            return float(self.pipeline.predict(feat)[0])
        except Exception as e:
            print(f"DinoInferenceService ERROR: {e}")
            return None

    def predict_rqi(self, image_path: str) -> Optional[int]:
        """Rounded RQI class (1-4), or None on failure."""
        score = self.predict_score(image_path)
        if score is None:
            return None
        lo, hi = self.rqi_clip
        return int(np.clip(round(score), lo, hi))


# Singleton instance
dino_service = DinoInferenceService()
