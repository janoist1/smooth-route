"""
RQI inference service (clean pipeline).

Wraps the frozen DINOv2 backbone + trained head produced by the `ml/` pipeline
(see ml/README.md). The artifact at ml/cache/rqi_model.joblib carries a
machine-readable `feature_recipe` (which views/tokens to extract) plus the
sklearn pipeline, tuned ordinal cut-points and an isotonic P(bad) calibrator;
this service interprets that recipe, so retraining with a different recipe
does not require code changes here.

v2 model (2026-07-03, 1903 images). Honest spatial CV (1 km grid cells,
re-measured 2026-11-18, ml/spatial_cv.py): QWK 0.774, MAE 0.405, exact 61%,
+-1 acc 98.5%, bad-road (Közepes or worse) accuracy 86%, AUC 0.934. (The originally
reported QWK 0.889 / MAE 0.195 came from a random 5-fold that leaked
neighbouring Street View frames between train and test.)

Public interface: `predict_rqi(path) -> Optional[int]` (unchanged),
`predict_score(path) -> Optional[float]`, `predict_p_bad(path) -> Optional[float]`.
Images are scored RAW (no vehicle masking / sky crop) to match training.

Scale: every public method speaks the CANONICAL RQI scale (app.core.rqi_scale).
The artifact's head, cut-points and P(bad) calibrator live in the orientation it
was trained in (`scale_direction`, default "lower_is_better" = severity, which
every artifact so far uses). Scores are converted at this boundary only, so a
scale-direction flip needs neither retraining nor a new gate run.
"""
import os
from typing import Optional

import numpy as np
import torch
from PIL import Image

from app.core.rqi_scale import SCALE, SEVERITY


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
    # Class-level defaults so test doubles built with __new__ work too.
    scale = SCALE
    scale_direction = SEVERITY  # orientation of the artifact's raw scores

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
        self.scale_direction = artifact.get("scale_direction", SEVERITY)
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

    # ----- scale boundary: artifact orientation <-> canonical ---------------
    def _to_canonical(self, raw: float) -> float:
        return self.scale.convert(raw, self.scale_direction)

    def _to_raw(self, score: float) -> float:
        return self.scale.to_direction(score, self.scale_direction)

    @torch.no_grad()
    def predict_score(self, image_path: str) -> Optional[float]:
        """Continuous canonical RQI estimate (spans the model levels), or None on failure."""
        try:
            self.load_model()
            img = Image.open(image_path).convert("RGB")
            feat = self._features(img)
            return float(self._to_canonical(float(self.pipeline.predict(feat)[0])))
        except Exception as e:
            print(f"DinoInferenceService ERROR: {e}")
            return None

    @torch.no_grad()
    def extract_features(self, image_path: str) -> Optional[np.ndarray]:
        """The exact feature vector the head sees for an image, shape (1, D),
        or None on failure. `score_from_features` on it equals `predict_score`
        — for tools that need the vector as well as the score in ONE pass."""
        try:
            self.load_model()
            img = Image.open(image_path).convert("RGB")
            return self._features(img)
        except Exception as e:
            print(f"DinoInferenceService ERROR: {e}")
            return None

    def score_from_features(self, features: np.ndarray) -> float:
        """Continuous canonical RQI estimate from an `extract_features` vector
        (the same number `predict_score` returns for that image)."""
        return float(self._to_canonical(float(self.pipeline.predict(features)[0])))

    def predict_rqi(self, image_path: str) -> Optional[int]:
        """Canonical RQI level (one of SCALE.model_levels) via the tuned cut-points, or None."""
        score = self.predict_score(image_path)
        if score is None:
            return None
        return self.rqi_from_score(score)

    def rqi_from_score(self, score: float) -> int:
        """Canonical continuous score -> canonical level, using the artifact's
        cut-points (tuned in its own orientation)."""
        raw = self._to_raw(score)
        if self.thresholds:
            level = int(np.digitize(raw, self.thresholds) + 1)
        else:
            lo, hi = self.rqi_clip
            level = int(np.clip(round(raw), lo, hi))
        return int(self._to_canonical(level))

    def p_bad_from_score(self, score: float) -> Optional[float]:
        """Calibrated P(road is bad: level at or worse than SCALE.bad_from) from a
        canonical score. A probability, so it never needs flipping."""
        if self.p_bad_calibrator is None:
            return None
        return float(self.p_bad_calibrator.predict([self._to_raw(score)])[0])

    def predict_p_bad(self, image_path: str) -> Optional[float]:
        """Calibrated probability that the road is bad (SCALE.is_bad)."""
        score = self.predict_score(image_path)
        if score is None:
            return None
        return self.p_bad_from_score(score)

    def model_info(self) -> Optional[dict]:
        """Read the live artifact's metadata (no torch backbone load) for the
        read-only model card. Returns None if the artifact is absent/unreadable."""
        if not os.path.exists(MODEL_PATH):
            return None
        try:
            import joblib

            art = joblib.load(MODEL_PATH)
            cv = art.get("cv_metrics", {}) or {}
            recipe = art.get("feature_recipe") or {}
            return {
                "version": art.get("version"),
                "backbone": art.get("backbone"),
                "recipe": recipe.get("name"),
                "head": art.get("head"),
                "n_train": art.get("n_train"),
                "qwk": cv.get("qwk"),
                "mae": cv.get("mae"),
                "exact_acc": cv.get("exact_acc"),
                "bad_road_acc": cv.get("bad_road_acc"),
                "bad_road_auc": cv.get("bad_road_auc"),
                "scale_meaning": art.get("scale_meaning"),
            }
        except Exception as e:  # pragma: no cover - defensive
            print(f"DinoInferenceService.model_info ERROR: {e}")
            return None


# Singleton instance
dino_service = DinoInferenceService()
