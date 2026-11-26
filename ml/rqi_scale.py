#!/usr/bin/env python3
"""ML view of the canonical RQI scale (shared/rqi_scale.json).

ML works in the fixed SEVERITY orientation: 1 = best, higher = worse, which
is today's numbering. Every label in ml/labels.csv and the caches, the model
targets, the cut-points, the P(bad) calibrator and the promotion gate use it.
Values cross between the canonical scale and ML in exactly two places:

  * DB -> ML: ml/export_labels.sh selects ``sql_to_severity("manual_rqi")``;
  * ML -> DB: the backend dino_service converts model scores using the
    artifact's ``scale_direction`` (written by save_model_v2.py).

So if the canonical direction flips (5 = best), no ML number changes and the
gate reports identical metrics. The level set and the bad-road boundary still
come from the shared file, so changing ``model_levels`` or ``bad_from`` there
reaches ML too.

Stdlib only; reuses the backend's helper by file path (no sys.path changes).
CLI:  python ml/rqi_scale.py                 # summary
      python ml/rqi_scale.py --sql manual_rqi  # SQL expr used by export_labels.sh
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_JSON = os.path.join(ROOT, "shared", "rqi_scale.json")
_CORE = os.path.join(ROOT, "backend", "app", "core", "rqi_scale.py")

_spec = importlib.util.spec_from_file_location("_rqi_scale_core", _CORE)
_core = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _core  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(_core)

RqiScale = _core.RqiScale
SEVERITY = _core.SEVERITY
SCALE = _core.load_scale(SHARED_JSON)

# --- severity-orientation constants (what every ML script uses) -----------
LEVELS = SCALE.severity_values(SCALE.values)              # [1, 2, 3, 4, 5]
MODEL_LEVELS = SCALE.severity_values(SCALE.model_levels)  # [1, 2, 3, 4]
DROPPED_LEVELS = [v for v in LEVELS if v not in MODEL_LEVELS]  # [5]
BAD_FROM = int(SCALE.to_severity(SCALE.bad_from))         # 3: severity >= 3 is bad
MIN_LEVEL, MAX_LEVEL = LEVELS[0], LEVELS[-1]
MODEL_MIN, MODEL_MAX = MODEL_LEVELS[0], MODEL_LEVELS[-1]
SCALE_DIRECTION = SEVERITY  # recorded in every artifact as "scale_direction"
SCALE_MEANING = (f"severity {MODEL_MIN}={SCALE.level(SCALE.from_severity(MODEL_MIN)).label_en.lower()}"
                 f" .. {MODEL_MAX}={SCALE.level(SCALE.from_severity(MODEL_MAX)).label_en.lower()}"
                 f" (lower=better road); canonical scale: shared/rqi_scale.json")


def sql_to_severity(column: str) -> str:
    """SQL expression mapping a canonical column to ML severity numbers."""
    if SCALE.direction == SEVERITY:
        return column
    return f"({SCALE.min_value + SCALE.max_value} - {column})"


def to_canonical(severity_value):
    """ML severity value/score -> canonical scale (for printing or writing back)."""
    return SCALE.from_severity(severity_value)


def main(argv):
    if len(argv) >= 3 and argv[1] == "--sql":
        print(sql_to_severity(argv[2]))
        return 0
    print(f"canonical direction : {SCALE.direction}")
    print("canonical levels    : " + ", ".join(
        f"{lv.value}={lv.label_hu}" for lv in SCALE.levels))
    print(f"ML severity levels  : {LEVELS} (model {MODEL_LEVELS}, dropped {DROPPED_LEVELS})")
    print(f"bad road            : severity >= {BAD_FROM}")
    print(f"export expression   : {sql_to_severity('manual_rqi')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
