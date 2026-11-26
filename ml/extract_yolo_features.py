"""Cache per-frame YOLO road-damage features for the labelled RQI frames.

Runs the *production* YOLO damage segmentation model (the weights named by the
"yolo_model" key in backend/config/analysis_settings.json, with the same
yolov8m-seg.pt fallback as backend/app/services/yolo_loader.py) over every
frame of ml/cache/dataset_v2.csv and stores hand-crafted damage statistics, so
a downstream experiment can test whether they add signal to the RQI regressor.
This script does NO model evaluation; it only extracts and caches features.

Feature grid (240 columns), named ``{thr}__{region}__{cls}__{stat}``:

* thr     ``c05``  = all detections with conf >= 0.05 (low inference threshold)
          ``prod`` = detections with conf >= the production threshold
                     ("yolo_inference_conf" in analysis_settings.json)
* region  ``full`` = whole frame (raw detections)
          ``roi``  = the production ROI trapezoid of road_analyzer.py
                     (bottom 10%..90% of the width, top 35%..65% at y = 0.5*H)
          ``low55``= lower 55% of the frame (y >= 0.45*H)
* cls     one of the 9 model classes (6 damage + shadow/manhole/marking), or
          ``any`` = union over the real damage classes only (class id <= 5,
          same rule as production's MAX_DAMAGE_CLASS_ID)
* stat    ``count``    number of detections with >= 1 mask pixel in the region
          ``area``     union mask area inside the region / full image area
          ``maxconf``  max confidence among those detections (0 if none)
          ``confarea`` sum_i conf_i * area_i (area_i = that detection's own
                       in-region mask area / image area; overlaps NOT merged)

All areas are fractions of the FULL image area (also for roi/low55), so the
three region variants are directly comparable. Missing detections -> zeros.
Masks are taken at original image resolution (retina_masks=True).

Usage:
    /Users/i/Dev/smooth-route/.venv/bin/python ml/extract_yolo_features.py

Output: ml/cache/yolo_feats.npz with ``files`` (manifest order), ``X``
(float32 [n_images, n_features]), ``names`` and ``meta`` (JSON string).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Dependency-free taxonomy module (no torch / DB imports).
from app.services.rqi_scoring import DAMAGE_CLASSES, MAX_DAMAGE_CLASS_ID  # noqa: E402

MANIFEST = ROOT / "ml" / "cache" / "dataset_v2.csv"
IMAGE_DIR = ROOT / "data" / "images"
MODEL_DIR = ROOT / "data" / "models"
SETTINGS = ROOT / "backend" / "config" / "analysis_settings.json"
OUT = ROOT / "ml" / "cache" / "yolo_feats.npz"

DEFAULT_YOLO_MODEL = "yolov8m-seg.pt"  # same fallback as yolo_loader.py
LOW_CONF = 0.05
DEFAULT_PROD_CONF = 0.25
LOW_REGION_TOP = 0.45  # low55 region: y >= 0.45 * H
BATCH = 32
IMGSZ = 640

REGIONS = ("full", "roi", "low55")
STATS = ("count", "area", "maxconf", "confarea")


def read_settings() -> dict:
    """analysis_settings.json is a list of {key, value, ...} records."""
    try:
        return {r["key"]: r["value"] for r in json.loads(SETTINGS.read_text())}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def resolve_weights(name: str) -> Path:
    """Production weights inside data/models, else the yolo_loader fallback."""
    candidate = MODEL_DIR / name
    if candidate.is_file():
        return candidate
    fallback = MODEL_DIR / DEFAULT_YOLO_MODEL
    if fallback.is_file():
        print(f"WARNING: {candidate} not found; using fallback {fallback}")
        return fallback
    raise FileNotFoundError(f"Neither {candidate} nor {fallback} exists")


def region_masks(h: int, w: int) -> dict[str, np.ndarray]:
    """Boolean [h, w] masks for the three regions."""
    full = np.ones((h, w), dtype=bool)
    # Same trapezoid as RoadDamageAnalyzer.analyze_image.
    roi = np.zeros((h, w), dtype=np.uint8)
    poly = np.array(
        [[w * 0.1, h], [w * 0.9, h], [w * 0.65, h * 0.5], [w * 0.35, h * 0.5]],
        dtype=np.int32,
    )
    cv2.fillPoly(roi, [poly], 255)
    low = np.zeros((h, w), dtype=bool)
    low[int(round(h * LOW_REGION_TOP)):, :] = True
    return {"full": full, "roi": roi > 0, "low55": low}


def frame_features(result, class_ids, thresholds, regions_cache) -> np.ndarray:
    """Feature vector for one ultralytics Results object.

    Layout: [threshold][region][class slot (classes..., any)][stat].
    """
    n_slots = len(class_ids) + 1  # + "any"
    out = np.zeros((len(thresholds), len(REGIONS), n_slots, len(STATS)), np.float32)
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return out.ravel()

    h, w = result.orig_shape
    if (h, w) not in regions_cache:
        regions_cache[(h, w)] = region_masks(h, w)
    regions = regions_cache[(h, w)]
    img_area = float(h * w)

    conf = boxes.conf.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int)
    if result.masks is not None:
        masks = result.masks.data.cpu().numpy() > 0.5
        if masks.shape[1:] != (h, w):  # safety net; retina masks are already h x w
            masks = np.stack(
                [cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
                 for m in masks]
            )
    else:
        # Detection-only weights: rasterise the boxes so the same code applies.
        masks = np.zeros((len(conf), h, w), dtype=bool)
        for i, (x1, y1, x2, y2) in enumerate(boxes.xyxy.cpu().numpy()):
            masks[i, max(int(y1), 0):int(np.ceil(y2)), max(int(x1), 0):int(np.ceil(x2))] = True

    slot_of = {c: s for s, c in enumerate(class_ids)}
    any_slot = len(class_ids)

    for r, rname in enumerate(REGIONS):
        m_reg = masks & regions[rname][None]
        px = m_reg.reshape(len(conf), -1).sum(1)  # per-detection in-region pixels
        for t, thr in enumerate(thresholds):
            keep = (conf >= thr) & (px > 0)
            if not keep.any():
                continue
            # (slot, detection selector) pairs: each class, then "any damage".
            groups = [(slot_of[c], keep & (cls == c)) for c in np.unique(cls[keep]) if c in slot_of]
            groups.append((any_slot, keep & (cls <= MAX_DAMAGE_CLASS_ID)))
            for slot, sel in groups:
                if not sel.any():
                    continue
                out[t, r, slot, 0] = sel.sum()
                out[t, r, slot, 1] = m_reg[sel].any(0).sum() / img_area  # union
                out[t, r, slot, 2] = conf[sel].max()
                out[t, r, slot, 3] = float((conf[sel] * px[sel]).sum() / img_area)
    return out.ravel()


def main() -> None:
    from ultralytics import YOLO

    settings = read_settings()
    weights = resolve_weights(str(settings.get("yolo_model", DEFAULT_YOLO_MODEL)))
    prod_conf = float(settings.get("yolo_inference_conf", DEFAULT_PROD_CONF))
    thresholds = (LOW_CONF, prod_conf)
    thr_names = ("c05", "prod")

    files = pd.read_csv(MANIFEST)["image_filename"].astype(str).tolist()
    missing = [f for f in files if not (IMAGE_DIR / f).is_file()]
    if missing:
        raise FileNotFoundError(f"{len(missing)} manifest images missing, e.g. {missing[:3]}")

    model = YOLO(str(weights))
    model_names = {int(k): v for k, v in model.names.items()}
    # Map model class ids to the DAMAGE_CLASSES codes (index == YOLO class id).
    class_ids = sorted(DAMAGE_CLASSES)
    mismatches = {
        i: (model_names.get(i), DAMAGE_CLASSES[i])
        for i in class_ids
        if model_names.get(i) != DAMAGE_CLASSES[i]
    }
    extra = sorted(set(model_names) - set(class_ids))
    if mismatches or extra:
        print(f"WARNING: class-name mismatch {mismatches}, unmapped model ids {extra}; "
              "features use DAMAGE_CLASSES codes by class id (as production does).")
    slots = [DAMAGE_CLASSES[i] for i in class_ids] + ["any"]
    names = [
        f"{t}__{r}__{c}__{s}" for t in thr_names for r in REGIONS for c in slots for s in STATS
    ]

    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"weights={weights.name} task={model.task} device={device} "
          f"conf={LOW_CONF}/{prod_conf} n={len(files)}")

    X = np.zeros((len(files), len(names)), dtype=np.float32)
    regions_cache: dict = {}
    shapes: dict = {}
    t0 = time.time()
    i = 0
    while i < len(files):
        batch = [str(IMAGE_DIR / f) for f in files[i:i + BATCH]]
        try:
            results = model.predict(batch, conf=LOW_CONF, imgsz=IMGSZ, device=device,
                                    retina_masks=True, verbose=False)
        except Exception as exc:  # MPS op failure -> redo this batch on CPU
            if device == "cpu":
                raise
            print(f"MPS failed ({type(exc).__name__}: {exc}); falling back to CPU")
            device = "cpu"
            continue
        for j, res in enumerate(results):
            X[i + j] = frame_features(res, class_ids, thresholds, regions_cache)
            shapes[tuple(res.orig_shape)] = shapes.get(tuple(res.orig_shape), 0) + 1
        i += len(batch)
        if (i // BATCH) % 10 == 0 or i >= len(files):
            print(f"  {i}/{len(files)}  {time.time() - t0:.0f}s", flush=True)
    runtime = time.time() - t0

    meta = {
        "weights_path": str(weights),
        "weights_name": weights.name,
        "task": model.task,
        "is_segmentation": model.task == "segment",
        "model_class_names": model_names,
        "class_slots": slots,
        "any_definition": f"union of damage classes with id <= {MAX_DAMAGE_CLASS_ID}",
        "conf_low": LOW_CONF,
        "conf_prod": prod_conf,
        "thresholds": dict(zip(thr_names, thresholds)),
        "regions": {
            "full": "whole frame",
            "roi": "production trapezoid: (0.1W,H),(0.9W,H),(0.65W,0.5H),(0.35W,0.5H)",
            "low55": f"y >= {LOW_REGION_TOP}*H",
        },
        "stats": list(STATS),
        "area_normaliser": "full image area (all regions)",
        "imgsz": IMGSZ,
        "retina_masks": True,
        "image_shapes_hw": {f"{h}x{w}": n for (h, w), n in shapes.items()},
        "device": device,
        "batch": BATCH,
        "runtime_sec": round(runtime, 1),
        "n_images": len(files),
        "manifest": str(MANIFEST),
    }
    np.savez_compressed(OUT, files=np.array(files), X=X, names=np.array(names),
                        meta=json.dumps(meta))
    print(f"saved {OUT}  X={X.shape}  runtime={runtime:.0f}s")


if __name__ == "__main__":
    main()
