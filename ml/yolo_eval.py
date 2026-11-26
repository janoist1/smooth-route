#!/usr/bin/env python3
"""
Era 14: how good is the owner-trained YOLO defect model on the owner's polygons?

Ground truth = training_data.annotations (polygons drawn/accepted on the review
page). Every annotation was made 2026-01-03..05, and the production weights
(data/models/yolov8m-seg-best-20260105.pt) were trained on Colab on
2026-01-05 18:21 from an export of them, so most frames are IN-SAMPLE. Only
frames whose annotations were last edited AFTER the training run are a clean
held-out set (--after, default = the checkpoint's training timestamp).

Writes a YOLO-seg dataset (labels from the DB polygons; "ignore"/"vehicle"
polygons dropped) under the scratch dir and runs ultralytics' validator: per
class box + mask precision / recall / mAP50, and the confusion matrix (incl.
damage <-> marking/shadow/manhole confusion).

Usage:
  /Users/i/Dev/smooth-route/.venv/bin/python ml/yolo_eval.py --out /tmp/yolo_eval [--all]
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import psycopg2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEIGHTS = os.path.join(ROOT, "data", "models", "yolov8m-seg-best-20260105.pt")
NAMES = ["long_crack", "trans_crack", "alligator_crack", "pothole", "patch",
         "degradation", "shadow", "manhole", "marking"]
W, H = 600, 400


def db_rows():
    url = os.environ.get("DATABASE_URL") or [
        line.split("=", 1)[1].strip().strip('"').strip("'")
        for line in open(os.path.join(ROOT, ".env")) if line.startswith("DATABASE_URL=")][0]
    with psycopg2.connect(url) as c, c.cursor() as cur:
        cur.execute("SELECT image_filename, annotations, coalesce(updated_at, created_at) "
                    "FROM training_data WHERE annotations IS NOT NULL "
                    "AND annotations::text NOT IN ('[]', 'null')")
        return cur.fetchall()


def write_dataset(rows, out):
    for d in ("images/val", "labels/val"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    n, stats = 0, {"polygons": 0, "scored": 0}
    for fname, ann, _ in rows:
        src = os.path.join(ROOT, "data", "images", fname)
        if not os.path.exists(src):
            continue
        lines = []
        for p in ann:
            if p.get("label") not in NAMES or len(p.get("points", [])) < 3:
                continue
            pts = np.asarray(p["points"], float)
            pts[:, 0] = np.clip(pts[:, 0] / W, 0, 1)
            pts[:, 1] = np.clip(pts[:, 1] / H, 0, 1)
            lines.append(f"{NAMES.index(p['label'])} "
                         + " ".join(f"{v:.5f}" for v in pts.ravel()))
            stats["polygons"] += 1
            stats["scored"] += "score" in p
        dst = os.path.join(out, "images/val", fname)
        if not os.path.exists(dst):
            os.symlink(src, dst)
        with open(os.path.join(out, "labels/val", os.path.splitext(fname)[0] + ".txt"), "w") as f:
            f.write("\n".join(lines))
        n += 1
    with open(os.path.join(out, "data.yaml"), "w") as f:
        f.write(f"path: {out}\ntrain: images/val\nval: images/val\nnames:\n"
                + "".join(f"  {i}: {nm}\n" for i, nm in enumerate(NAMES)))
    return n, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--all", action="store_true", help="all annotated frames (in-sample!)")
    ap.add_argument("--after", default=None, help="ISO time; default = checkpoint training time")
    args = ap.parse_args()

    from ultralytics import YOLO
    import torch
    ck = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    trained = dt.datetime.fromisoformat(args.after or ck["date"])
    rows = db_rows()
    if not args.all:
        rows = [r for r in rows if r[2] > trained]
    n, st = write_dataset(rows, args.out)
    print(f"{'ALL (in-sample)' if args.all else f'held-out (edited after {trained})'}: "
          f"{n} frames, {st['polygons']} polygons ({st['scored']} pre-filled by AI)")
    m = YOLO(WEIGHTS)
    r = m.val(data=os.path.join(args.out, "data.yaml"), split="val", imgsz=640,
              device="mps", conf=0.001, iou=0.6, plots=True, verbose=False,
              project=args.out, name="val", exist_ok=True)
    print(f"\n{'class':16s} {'inst':>5s} {'box P':>6s} {'box R':>6s} {'box50':>6s} "
          f"{'mask P':>6s} {'mask R':>6s} {'mask50':>6s}")
    cm = r.confusion_matrix.matrix          # [pred(+bg), true(+bg)]
    inst = np.zeros(len(NAMES), int)
    for fn in os.listdir(os.path.join(args.out, "labels/val")):
        if fn.endswith(".txt"):
            for line in open(os.path.join(args.out, "labels/val", fn)):
                if line.strip():
                    inst[int(line.split()[0])] += 1
    for j, ci in enumerate(r.box.ap_class_index):
        bp, br, b50, _ = r.box.class_result(j)
        mp, mr, m50, _ = r.seg.class_result(j)
        print(f"{NAMES[ci]:16s} {int(inst[ci]):5d} {bp:6.2f} {br:6.2f} {b50:6.2f} "
              f"{mp:6.2f} {mr:6.2f} {m50:6.2f}")
    print(f"{'all':16s} {'':5s} {r.box.mp:6.2f} {r.box.mr:6.2f} {r.box.map50:6.2f} "
          f"{r.seg.mp:6.2f} {r.seg.mr:6.2f} {r.seg.map50:6.2f}")
    print("\nconfusion (rows = predicted, cols = true; last = background):")
    labels = NAMES + ["bg"]
    print(" " * 16 + " ".join(f"{nm[:6]:>6s}" for nm in labels))
    for i, nm in enumerate(labels):
        print(f"{nm:16s} " + " ".join(f"{int(v):6d}" for v in cm[i]))
    json.dump({"n_frames": n, **st, "map50_box": r.box.map50, "map50_mask": r.seg.map50},
              open(os.path.join(args.out, "summary.json"), "w"))


if __name__ == "__main__":
    sys.exit(main())
