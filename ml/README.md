# `ml/` — the RQI model pipeline

Trains, gates and ships the RQI model (`ml/cache/rqi_model.joblib`) that the backend's
`dino_service.py` loads. Recipe: frozen DINOv2-small (CLS + mean patch token) →
StandardScaler → SVR-RBF → tuned ordinal cut-points + isotonic P(bad) calibrator, on
the **raw** frame. Why this recipe and every experiment behind it:
[docs/MODEL_EXPERIMENTS.md](../docs/MODEL_EXPERIMENTS.md). Everything runs on the
Mac (MPS) with `.venv/bin/python` (in a worktree: the main checkout's interpreter).

## Scale: ML works in severity numbering

The product scale is defined in [shared/rqi_scale.json](../shared/rqi_scale.json)
(5 = Kiváló … 1 = Nagyon rossz). **Everything in `ml/` uses the severity numbering
1 = Kiváló … 4 = Rossz**: `labels.csv`, caches, targets, cut-points, the calibrator,
the gate. Constants come from `ml/rqi_scale.py` (`spatial_cv.RQI_LABELS / BAD_FROM /
DROPPED_LEVELS`). Values change numbering only at two boundaries: the label export
(`export_labels.sh` selects `6 - manual_rqi`) and the backend (`dino_service` uses the
artifact's `scale_direction`). Nagyon rossz labels (14, mostly junk) are dropped from
training. Details: [shared/README.md](../shared/README.md).

## Pipeline

| Step | Command | Output |
|---|---|---|
| Export labels (Docker DB) | `bash ml/export_labels.sh` | `ml/labels.csv` (+ `svi_id`, lat/lon, `source` = quick/review) |
| Label audit | `ml/audit_labels.py` | distribution, images on disk |
| Recover missing images | `ml/recover_missing_images.py` | Street View re-download with capture-date guard (quota-safe client) |
| Features | `ml/extract_features_v2.py [--backbone small]` | `ml/cache/feats_v2_*.npz`, `clip_v2.npz`, `dataset_v2.csv` |
| Coordinates | `ml/build_coords.py` | `ml/image_coords.csv` (committed; needed by the spatial CV) |
| Train the artifact | `ml/save_model_v2.py` | `ml/cache/rqi_model.joblib` (`--out` for a side candidate) |
| **Gate** | `ml/evaluate_artifact.py [artifact]` | PASS / FAIL (below) |
| One-shot predict | `ml/predict.py <image>…` | level, score, P(bad), road check |

Research tools (not needed to retrain): `experiments.py` (feature × head grid),
`tune_svr.py`, `finetune_lastblocks.py`, `compare_candidates.py` (paired challenger
test), `spatial_analysis.py` (variogram, cell-size curve, region errors),
`experiments_hires.py` / `extract_features_hires.py` / `extract_yolo_features.py`
(Era 8), `vlm_attributes.py` / `vlm_feature_eval.py` (Era 9), `learning_curve.py`
(Era 11: how many and which labels help),
`check_backend_parity.py` (backend rebuilds the training features exactly),
`label_consistency.py` (the owner's blind re-check agreement — the practical QWK
ceiling). `ml/legacy/` is v1, reference only.

## One-command retrain

`make retrain` (= `ml/retrain.py`) once enough new labels exist. It exports labels
(aborts if they anti-correlate with the cache, i.e. a scale mix-up), reuses cached
features (DINOv2 + CLIP only for new frames), rebuilds coordinates, fits the champion
recipe as `ml/cache/rqi_model_candidate.joblib`, runs the gate plus three reports
(old vs all labels on the same folds; champion vs candidate on the new labels only —
a true holdout; Budapest) into `ml/cache/retrain/<run>/summary.md`. **PROMOTABLE** =
gate PASS, ≥ 50 new labels (`--min-new`), paired ΔQWK ≥ 0 with CI above −0.02.
Promotion is a manual `cp` (printed); it never writes the live model or shared
caches. Flags: `--force`, `--no-extract`, `--labels CSV`; `RQI_ML_CACHE` /
`RQI_ML_COORDS` re-gate a run by hand.

## Promotion gate (mandatory)

A new or changed `rqi_model.joblib` ships **only** on PASS from
`ml/evaluate_artifact.py`. It re-fits the artifact's recipe and head on the official
**spatial CV** (`ml/spatial_cv.py`: 1 km grid cells, StratifiedGroupKFold 5,
seed 42) with cut-points tuned in a nested inner spatial CV; it ignores the numbers
stored in the artifact.

| Metric | Threshold | Tolerance |
|---|---|---|
| QWK | ≥ 0.774 | 0.005 |
| MAE | ≤ 0.405 | 0.005 |
| bad-road AUC | ≥ 0.934 | 0.003 |

PASS only means "not worse". To replace the champion the gate's paired cell bootstrap
must say **"measurably better: YES"** (ΔQWK 95% CI > 0), ideally confirmed on shifted
grids. Exit code 0 = PASS, 1 = FAIL, 2 = error. After promoting, raise `GATE` in
`evaluate_artifact.py` to the new champion. Never cite the old random-CV numbers
(0.889 / 0.195 / 0.970).

## Artifact contract

`dino_service.validate_artifact` checks on load. **Required:** `pipeline` (sklearn
StandardScaler + head) and, if present, `feature_recipe.keys`. **Expected** (warning
if missing): `version`, `backbone`, `feature_recipe` (`name`, `keys`, `needs_clip`,
`crop_top`, optional `hires_views`), `thresholds` (3 cut-points), `p_bad_calibrator`,
`cv_metrics`, `n_train`, `reliability`, `scale_direction` (severity; default when
absent). `save_model_v2.py` writes all of them — add new fields in both places.

## Segment evaluation

`ml/segment_eval.py` measures ~200 m segments under the same spatial protocol and
writes the recipe `ml/segment_recipe.json` (`--write-recipe`; severity numbering,
tagged `scale_direction`). The backend applies it through
`backend/config/segment_aggregation.json` with the thresholds mirrored to the product
numbering — `scripts/sync_rqi_scale.py` (`flip_segment_config`) does that, and a
backend test checks the two agree. Results: Era 7 of the experiments doc.

## Frame quality flags

`ml/frame_quality.py` marks frames that must not count toward road quality in
`street_view_images.analysis_metadata.frame_quality` =
`{usable, reasons, road_prob, blur, brightness, dup_of, version}`. Reasons:
`missing_image`, `no_imagery`, `dark`, `blur`, `not_road`, `indoor`,
`tunnel_garage`, `hood`, `duplicate`. Consumers skip a frame only when `usable` is
explicitly `false`. Thresholds (`THRESHOLDS`) are calibrated so labelled road frames
are almost never flagged (0.16%). Stages cache in `ml/cache/frame_quality/` and
resume:

```bash
.venv/bin/python ml/frame_quality.py all                       # compute
.venv/bin/python ml/frame_quality.py write                     # dry run
.venv/bin/python ml/frame_quality.py write --commit --backup data/backups/<fresh dump>
```

New frames are handled incrementally by `make postprocess`
([DEVELOPMENT.md](../DEVELOPMENT.md#collecting-street-view-frames-safely)).

## Reliability checks (not used in production)

- `ml/novelty.py validate` — feature-space novelty does not predict error (AUC
  0.56–0.60).
- `ml/geo_reliability.py` — distance to labelled areas does not predict error;
  the product uses a fixed 3 km "unlabelled area" confidence cap instead.

Both: [MODEL_EXPERIMENTS.md](../docs/MODEL_EXPERIMENTS.md#where-the-model-is-unsure-novelty-and-geography-2026-11-26).

## Open

- A fixed, independent holdout region (new district + new town), never trained on.
- More, more varied labels (Budapest incl. Kiváló roads); a sharper Jó definition.
- Promotion decisions on the two gated candidates (Era 8 dinov2-base two-view,
  Era 9 VLM stack) after the holdout exists.
- The live artifact's `cv_metrics` still shows the old leaky numbers until it is
  re-saved (re-saving also refits cut-points and calibrator — a deliberate decision).

## Tests

`make test-ml` (or `.venv/bin/python -m pytest -q ml/tests`, ~15 s; in a git worktree
pass `PYTHON=<main checkout>/.venv/bin/python`) runs the unit tests of the promotion
pipeline on synthetic data: spatial folds and cells, nested cut-points (incl. a
leakage guard), bootstrap deltas, segment chaining/aggregation/truth, the retrain
verdict, and the model-card builder (it also fails when `ml/model_card.json` no
longer matches the champion's hash). No torch, images or DB; CI runs them in the
`ml` job.
