"""Score unlabelled Street View frames with the live RQI model into a cache
file, so the label queue's "uncertain" strategy can rank every frame.

Usage (from backend/):
    ../.venv/bin/python scripts/score_frames.py [--limit N] [--batch 32]
        [--include-labelled] [--device mps|cpu]

Why a cache file and not the DB: only ~3.3k frames carry a v2 continuous score
(``analysis_metadata.dino_score``); the rest were classified by the older
model. Writing v2 scores into ``analysis_metadata`` would make ``dinoScore``
disagree with the stored ``dino_rqi_score`` on the map. The queue only needs a
ranking signal, so the scores go to ``data/cache/frame_scores.csv`` (git-ignored
canonical data dir) and the DB stays untouched. The queue prefers the DB score
when present and falls back to this cache.

- Frames that already have ``analysis_metadata.dino_score`` are skipped.
- Resumable: rows already in the cache for the same model artifact are
  skipped; results are appended per batch, so an interrupt loses one batch.
- Images are scored RAW, exactly like ``dino_service`` (no preprocessing).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.paths import data_path, image_path  # noqa: E402
from app.services.label_queue_store import (  # noqa: E402
    SCORE_CACHE_FIELDS,
    model_version,
    score_cache_path,
)

def load_targets(include_labelled: bool) -> list[str]:
    from app.core.database import SessionLocal
    from app.models.models import StreetViewImage, TrainingData
    from app.graphql.resolver_helpers import image_filename_from_url

    db = SessionLocal()
    try:
        labelled = set()
        if not include_labelled:
            labelled = {
                f for (f,) in db.query(TrainingData.image_filename)
                .filter(TrainingData.manual_rqi.isnot(None)).all()
            }
        out = []
        for url, meta in db.query(StreetViewImage.image_url,
                                  StreetViewImage.analysis_metadata).all():
            name = image_filename_from_url(url)
            if not name or name in labelled:
                continue
            if isinstance(meta, dict) and meta.get("dino_score") is not None:
                continue
            out.append(name)
        return sorted(set(out))
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--include-labelled", action="store_true")
    ap.add_argument("--device", default=None, help="override torch device")
    args = ap.parse_args()

    import numpy as np
    import torch
    from PIL import Image

    from app.services.dino_service import dino_service

    if args.device:
        dino_service.device = args.device
    dino_service.load_model()
    recipe_keys = (dino_service.recipe or {}).get("keys", ["cls"])
    batchable = set(recipe_keys) <= {"cls", "patch"}
    version = model_version()

    cache = score_cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if cache.exists():
        with cache.open() as fh:
            for row in csv.DictReader(fh):
                if row.get("model_version") == version:
                    done.add(row["image_filename"])

    targets = [t for t in load_targets(args.include_labelled) if t not in done]
    targets = [t for t in targets if image_path(t).is_file()]
    if args.limit:
        targets = targets[: args.limit]
    print(f"{len(targets)} frames to score ({len(done)} already cached) "
          f"on {dino_service.device}, batch={args.batch if batchable else 1}")

    new_file = not cache.exists()
    fh = cache.open("a", newline="")
    writer = csv.DictWriter(fh, fieldnames=SCORE_CACHE_FIELDS)
    if new_file:
        writer.writeheader()

    t0 = time.time()
    step = args.batch if batchable else 1
    n = 0
    try:
        for i in range(0, len(targets), step):
            names = targets[i:i + step]
            imgs, ok = [], []
            for name in names:
                try:
                    imgs.append(Image.open(image_path(name)).convert("RGB"))
                    ok.append(name)
                except Exception as exc:  # unreadable file: skip, keep going
                    print(f"skip {name}: {exc}")
            if not ok:
                continue
            with torch.no_grad():
                if batchable:
                    inp = dino_service.processor(images=imgs, return_tensors="pt").to(
                        dino_service.device)
                    out = dino_service.backbone(**inp)
                    pool = {
                        "cls": out.pooler_output.float().cpu().numpy(),
                        "patch": out.last_hidden_state[:, 1:].mean(1).float().cpu().numpy(),
                    }
                    feats = np.concatenate([pool[k] for k in recipe_keys], axis=1)
                else:
                    feats = np.concatenate([dino_service._features(im) for im in imgs])
            scores = dino_service.pipeline.predict(feats)
            for name, s in zip(ok, scores):
                p_bad = dino_service.p_bad_from_score(float(s))
                writer.writerow({
                    "image_filename": name,
                    "score": round(float(s), 3),
                    "p_bad": "" if p_bad is None else round(p_bad, 3),
                    "model_version": version,
                })
            fh.flush()
            n += len(ok)
            if (i // step) % 20 == 0:
                rate = n / max(time.time() - t0, 1e-6)
                print(f"{n}/{len(targets)}  {rate:.1f} img/s", flush=True)
    finally:
        fh.close()
    print(f"done: {n} frames scored in {time.time() - t0:.0f}s -> "
          f"{os.path.relpath(cache, data_path())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
