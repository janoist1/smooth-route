#!/usr/bin/env python3
"""Copy the canonical RQI scale (shared/rqi_scale.json) to its deployable copies.

The backend (Vercel deploys only backend/) and the frontend (Vite bundles only
frontend/) cannot read shared/ at runtime, so each carries a byte-identical
copy. Edit shared/rqi_scale.json only, then run:

    python scripts/sync_rqi_scale.py          # write the copies
    python scripts/sync_rqi_scale.py --check  # exit 1 if a copy drifted
    python scripts/sync_rqi_scale.py --flip   # mirror the numbering (1 = best <-> 5 = best)
                                              # + the segment config's "scale" block and
                                              # thresholds + sync; ships together with the
                                              # data migration (shared/README.md)

Backend pytest and Vitest also fail on drift (test_rqi_scale.py, rqiScale.test.ts).
"""
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "shared", "rqi_scale.json")
SEGMENT_CONFIG = os.path.join(ROOT, "backend", "config", "segment_aggregation.json")
COPIES = (
    os.path.join(ROOT, "backend", "app", "core", "rqi_scale.json"),
    os.path.join(ROOT, "frontend", "src", "modules", "ui", "utils", "rqiScale.json"),
)


def flip_source():
    """Rewrite shared/rqi_scale.json with the numbering mirrored (see shared/README.md)."""
    path = os.path.join(ROOT, "backend", "app", "core", "rqi_scale.py")
    spec = importlib.util.spec_from_file_location("_rqi_scale_core", path)
    core = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = core
    spec.loader.exec_module(core)
    scale = core.load_scale(SOURCE)
    data = scale.mirrored_data()
    with open(SOURCE, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"shared/rqi_scale.json: direction {scale.direction} -> {data['direction']}")
    flip_segment_config(scale)


def flip_segment_config(scale):
    """Mirror the segment layer's own "scale" block + cut-points (RqiScale in
    backend/app/services/segment_aggregation.py) so it keeps matching the
    canonical scale (pinned by backend/tests/test_rqi_scale.py)."""
    if not os.path.exists(SEGMENT_CONFIG):
        return
    with open(SEGMENT_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    mirror = scale.min_value + scale.max_value
    cfg["thresholds"] = sorted(round(mirror - t, 3) for t in cfg["thresholds"])
    sc = cfg["scale"]
    sc["classes"] = sorted(mirror - c for c in sc["classes"])
    sc["higher_is_worse"] = not sc["higher_is_worse"]
    sc["bad_class"] = mirror - sc["bad_class"]
    text = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
    # keep short numeric lists on one line, as the file is written by hand
    text = re.sub(r"\[\s*([-\d.,\s]+?)\s*\]",
                  lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]", text)
    with open(SEGMENT_CONFIG, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"backend/config/segment_aggregation.json: thresholds {cfg['thresholds']}, "
          f"classes {sc['classes']}, higher_is_worse {sc['higher_is_worse']}")


def main(argv):
    check = "--check" in argv[1:]
    if "--flip" in argv[1:]:
        flip_source()
    with open(SOURCE, "rb") as f:
        src = f.read()
    drifted = []
    for path in COPIES:
        cur = open(path, "rb").read() if os.path.exists(path) else None
        if cur == src:
            continue
        drifted.append(os.path.relpath(path, ROOT))
        if not check:
            with open(path, "wb") as f:
                f.write(src)
    if check and drifted:
        print("RQI scale copies out of sync: " + ", ".join(drifted)
              + "\nRun: python scripts/sync_rqi_scale.py")
        return 1
    print(("in sync" if check else "synced") + (f" ({', '.join(drifted)})" if drifted and not check else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
