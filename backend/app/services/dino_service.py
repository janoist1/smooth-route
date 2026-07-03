"""
RQI inference service (clean pipeline).

Wraps the frozen DINOv2 backbone + trained head produced by the `ml/` pipeline
(see ml/README.md). The artifact at ml/cache/rqi_model.joblib carries a
machine-readable `feature_recipe` (which views/tokens to extract) plus the
sklearn pipeline, tuned ordinal cut-points and an isotonic P(bad) calibrator;
this service interprets that recipe, so retraining with a different recipe
does not require code changes here.

v2 model (2026-07-03, 1903 images, 5-fold CV): QWK 0.889, MAE 0.195,
exact 81%, +-1 acc 99.8%, bad-road (RQI>=3) accuracy 92%, AUC 0.969.

Public interface: `predict_rqi(path) -> Optional[int]` (unchanged),
`predict_score(path) -> Optional[float]`, `predict_p_bad(path) -> Optional[float]`.
Images are scored RAW (no vehicle masking / sky crop) to match training.
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

# Artifact contract (see ml/README "Artifact szerződés"). REQUIRED keys make the
# artifact structurally usable; EXPECTED keys carry the v2 metadata that the
# product relies on (tuned thresholds, calibrated P(bad), reliability, etc.).
REQUIRED_KEYS = ("pipeline",)
EXPECTED_V2_KEYS = ("version", "backbone", "feature_recipe", "thresholds",
                    "p_bad_calibrator", "cv_metrics", "n_train")


def validate_artifact(artifact: dict) -> list:
    """Raise ValueError on a structurally unusable artifact; return a list of
    non-fatal warnings for missing v2 metadata (empty if fully conformant)."""
    if not isinstance(artifact, dict):
        raise ValueError(
            f"RQI artifact must be a dict, got {type(artifact).__name__}. "
            f"Retrain with: .venv/bin/python ml/save_model_v2.py"
        )
    missing_required = [k for k in REQUIRED_KEYS if k not in artifact]
    if missing_required:
        raise ValueError(
            f"RQI artifact is missing required key(s) {missing_required} at "
            f"{MODEL_PATH}. It cannot score images. Retrain with "
            f"ml/save_model_v2.py and verify with ml/evaluate_artifact.py."
        )
    recipe = artifact.get("feature_recipe")
    if recipe is not None and "keys" not in recipe:
        raise ValueError(
            "RQI artifact feature_recipe has no 'keys' list; the service cannot "
            "know which features to build. Retrain with ml/save_model_v2.py."
        )
    return [f"missing '{k}'" for k in EXPECTED_V2_KEYS if k not in artifact]


class DinoInferenceService:
    def __init__(self):
        self.device = self._get_device()
        self.backbone = None
        self.processor = None
        self.pipeline = None          # sklearn scaler+head
        self.recipe = None            # feature recipe dict (v2) or None (v1)
        self.thresholds = None        # ordinal cut-points (v2) or None
        self.p_bad_calibrator = None
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
                f"Train it with: .venv/bin/python ml/save_model_v2.py"
            )

        artifact = joblib.load(MODEL_PATH)
        warnings = validate_artifact(artifact)
        if warnings:
            print(f"DinoInferenceService WARNING: artifact at {MODEL_PATH} is "
                  f"missing v2 metadata ({', '.join(warnings)}); running with "
                  f"fallbacks. Retrain with ml/save_model_v2.py to refresh.")
        self.pipeline = artifact["pipeline"]
        self.recipe = artifact.get("feature_recipe")
        self.thresholds = artifact.get("thresholds")
        self.p_bad_calibrator = artifact.get("p_bad_calibrator")
        self.rqi_clip = tuple(artifact.get("rqi_clip", (1, 4)))
        backbone_name = artifact.get("backbone", "facebook/dinov2-small")

        print(f"DinoInferenceService: loading {backbone_name} on {self.device} "
              f"(head trained on {artifact.get('n_train', '?')} images, "
              f"recipe={self.recipe['name'] if self.recipe else 'v1 cls'})")
        self.processor = AutoImageProcessor.from_pretrained(backbone_name)
        self.backbone = AutoModel.from_pretrained(backbone_name).to(self.device).eval()
        self._loaded = True

    def _features(self, img: Image.Image) -> np.ndarray:
        """Build the feature vector the artifact's recipe asks for."""
        if not self.recipe:  # v1 artifact: CLS token only
            inp = self.processor(images=img, return_tensors="pt").to(self.device)
            return self.backbone(**inp).pooler_output.float().cpu().numpy()

        keys = self.recipe["keys"]
        views = [img]  # slot 0: original
        need_flip = any(k.endswith("_flip") or k.endswith("_avg") for k in keys)
        need_crop = any(k.endswith("_crop") for k in keys)
        flip_idx = crop_idx = None
        if need_flip:
            flip_idx = len(views)
            views.append(img.transpose(Image.FLIP_LEFT_RIGHT))
        if need_crop:
            crop_idx = len(views)
            w, h = img.size
            views.append(img.crop((0, int(h * self.recipe.get("crop_top", 0.35)), w, h)))

        inp = self.processor(images=views, return_tensors="pt").to(self.device)
        out = self.backbone(**inp)
        cls = out.pooler_output.float().cpu().numpy()
        patch = out.last_hidden_state[:, 1:].mean(1).float().cpu().numpy()

        pool = {"cls": cls[0], "patch": patch[0]}
        if flip_idx is not None:
            pool["cls_flip"] = cls[flip_idx]
            pool["patch_flip"] = patch[flip_idx]
            pool["cls_avg"] = (pool["cls"] + pool["cls_flip"]) / 2
            pool["patch_avg"] = (pool["patch"] + pool["patch_flip"]) / 2
        if crop_idx is not None:
            pool["cls_crop"] = cls[crop_idx]
            pool["patch_crop"] = patch[crop_idx]
        if self.recipe.get("needs_clip"):
            raise NotImplementedError(
                "CLIP-concat recipes are not wired into the backend service")

        return np.concatenate([pool[k] for k in keys])[None, :]

    @torch.no_grad()
    def predict_score(self, image_path: str) -> Optional[float]:
        """Continuous RQI estimate (1.0-4.0), or None on failure."""
        try:
            self.load_model()
            img = Image.open(image_path).convert("RGB")
            feat = self._features(img)
            return float(self.pipeline.predict(feat)[0])
        except Exception as e:
            print(f"DinoInferenceService ERROR: {e}")
            return None

    def predict_rqi(self, image_path: str) -> Optional[int]:
        """RQI class (1-4) via tuned ordinal cut-points, or None on failure."""
        score = self.predict_score(image_path)
        if score is None:
            return None
        return self.rqi_from_score(score)

    def rqi_from_score(self, score: float) -> int:
        if self.thresholds:
            return int(np.digitize(score, self.thresholds) + 1)
        lo, hi = self.rqi_clip
        return int(np.clip(round(score), lo, hi))

    def p_bad_from_score(self, score: float) -> Optional[float]:
        """Calibrated P(road is bad, RQI >= 3) from an existing score."""
        if self.p_bad_calibrator is None:
            return None
        return float(self.p_bad_calibrator.predict([score])[0])

    def predict_p_bad(self, image_path: str) -> Optional[float]:
        """Calibrated probability that the road is bad (RQI >= 3)."""
        score = self.predict_score(image_path)
        if score is None:
            return None
        return self.p_bad_from_score(score)


# Singleton instance
dino_service = DinoInferenceService()
