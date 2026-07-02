#!/usr/bin/env python3
"""
Audit the exported RQI labels BEFORE we train anything.

Purpose: answer "is this a viable direction?" with evidence, not a guess.
Runs anywhere with numpy/pandas/PIL (no torch, no downloads) -> Claude runs it
in-sandbox the moment ml/labels.csv exists.

Usage:  python ml/audit_labels.py
"""
import os
import json
import sys
from collections import Counter

import numpy as np
import pandas as pd
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELS = os.path.join(ROOT, "ml", "labels.csv")
IMAGES = os.path.join(ROOT, "data", "images")


def _parse_tags(v):
    if not isinstance(v, str) or not v.strip():
        return []
    try:
        x = json.loads(v)
        return x if isinstance(x, list) else [str(x)]
    except Exception:
        return [t.strip() for t in v.strip("{}").split(",") if t.strip()]


def main():
    if not os.path.exists(LABELS):
        print(f"!! {LABELS} not found. Run `bash ml/export_labels.sh` first.")
        sys.exit(1)

    df = pd.read_csv(LABELS)
    print(f"Rows in labels.csv: {len(df)}")
    print(f"Columns: {list(df.columns)}\n")

    df = df[df["manual_rqi"].notna()].copy()
    df["rqi_round"] = df["manual_rqi"].round().clip(1, 5).astype(int)

    # --- distribution ---
    print("=== RQI distribution (rounded 1-5) ===")
    dist = df["rqi_round"].value_counts().sort_index()
    total = len(df)
    for k in range(1, 6):
        n = int(dist.get(k, 0))
        bar = "#" * int(40 * n / max(total, 1))
        print(f"  {k}: {n:4d} ({100*n/max(total,1):5.1f}%) {bar}")
    print(f"  mean={df['manual_rqi'].mean():.2f}  median={df['manual_rqi'].median():.2f}"
          f"  std={df['manual_rqi'].std():.2f}")
    imb = dist.max() / max(dist.min(), 1)
    print(f"  imbalance (max/min class) = {imb:.1f}x\n")

    # --- images on disk ---
    print("=== image availability on disk ===")
    exists = df["image_filename"].apply(
        lambda f: os.path.exists(os.path.join(IMAGES, str(f)))
    )
    print(f"  present: {int(exists.sum())} / {len(df)}")
    if (~exists).any():
        missing = df.loc[~exists, "image_filename"].head(5).tolist()
        print(f"  missing examples: {missing}")
    dups = df["image_filename"].duplicated().sum()
    print(f"  duplicate filenames: {int(dups)}\n")

    # --- tags (difficulty factors) ---
    tag_counter = Counter()
    for v in df.get("tags", pd.Series([], dtype=object)):
        for t in _parse_tags(v):
            tag_counter[t] += 1
    if tag_counter:
        print("=== tags (shadow/wet/occlusion etc.) ===")
        for t, n in tag_counter.most_common():
            print(f"  {t}: {n}")
        print()

    # --- image size sanity on a sample ---
    sample = df.loc[exists, "image_filename"].head(30)
    sizes = []
    for f in sample:
        try:
            with Image.open(os.path.join(IMAGES, str(f))) as im:
                sizes.append(im.size)
        except Exception:
            pass
    if sizes:
        ws, hs = zip(*sizes)
        print("=== image size sample ===")
        print(f"  width  min/med/max: {min(ws)}/{int(np.median(ws))}/{max(ws)}")
        print(f"  height min/med/max: {min(hs)}/{int(np.median(hs))}/{max(hs)}\n")

    # --- verdict heuristics ---
    n_ok = int(exists.sum())
    min_class = int(dist.min())
    print("=== quick read ===")
    print(f"  usable labelled images: {n_ok}")
    print(f"  smallest class: {min_class} samples")
    notes = []
    if n_ok < 150:
        notes.append("Very small set -> expect high variance; use cross-validation, not a single split.")
    if imb >= 5:
        notes.append("Strong class imbalance -> need class weighting + balanced eval; consider merging 4&5.")
    if min_class < 15:
        notes.append("At least one class is tiny -> that class will be unreliable; maybe collapse to 3 levels (good/fair/poor).")
    if not notes:
        notes.append("Balance/size look workable for a first frozen-backbone baseline.")
    for s in notes:
        print("  - " + s)


if __name__ == "__main__":
    main()
