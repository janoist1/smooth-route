# Model experiments: what we tried and what we learned

*Updated 2026-11-26.* The decision log behind the live RQI model. How to run the
pipeline and the gate: [ml/README.md](../ml/README.md). Terms: [GLOSSARY.md](GLOSSARY.md).

> **Numbering.** The product scale is 5 = Kiváló … 1 = Nagyon rossz
> ([shared/rqi_scale.json](../shared/rqi_scale.json)). The model and every number in
> this file use the **old (severity) numbering, 1 = Kiváló, 2 = Jó, 3 = Közepes,
> 4 = Rossz** (product value = 6 − old). Where it helps, classes are named instead.
> "Bad road" = Közepes or worse. Metrics (QWK, MAE, AUC) are identical in either
> numbering.

## TL;DR — where we are

- **Live model:** frozen DINOv2-small (CLS + mean patch token) → SVR-RBF → tuned
  cut-points + isotonic P(bad) calibrator (`ml/cache/rqi_model.joblib`).
- **Honest quality** (spatial CV, streets never seen in training): **QWK 0.774,
  MAE 0.405, exact 61%, ±1 98.5%, bad-road AUC 0.934.** In a new region: QWK 0.66 /
  AUC 0.87. Budapest is the weak spot (AUC 0.78 within the city).
- **On the map** the unit is a ~200 m road segment (median frame score): QWK 0.84,
  MAE 0.29, bad-road AUC 0.97, with a calibrated three-level confidence (Era 7).
- **Challengers:** many variants land within noise of the champion. Two pass the gate
  as "measurably better" but are **not promoted**: a dinov2-base two-view model
  (+0.021 QWK, 11× inference cost, Era 8) and champion + VLM attributes (+0.031 QWK,
  needs a VLM call per frame, Era 9).
- **What moves the needle now is labels**, not models: more places, Budapest, a fixed
  holdout region, a sharper Jó definition.

| Component | Status | Role |
|---|---|---|
| v2 RQI engine (`rqi_model.joblib` + `dino_service.py`) | **live** | the map's RQI + P(bad) |
| Segment aggregation (`segment_aggregation.json`, `road_segments`) | **live** | the map's road colours + confidence |
| YOLO damage segmenter (`road_analyzer.py`) | live | damage polygons on the detail card only |
| `ml/legacy/` (v1 Ridge scripts) | reference | superseded by v2 |
| FastSAM preprocessing (`preprocessing.py`) | quarantined | review-page diagnostic only, never on the RQI path |
| Hand-written heuristic, web DINO head training | removed | dead ends (Eras 1, 4) |

## Eras 1–4 — what did not work

| Era | Approach | Why it was dropped |
|---|---|---|
| 1 | Hand-written image rules (edge density, texture variance, patch density) | Shadows, wet asphalt and asphalt colour fooled it; endless hand-tuning. Code removed. |
| 2 | YOLOv8 damage segmentation → damage % → RQI | Good polygons, weak RQI: misses wavy/fatigued surfaces. Kept for "what is wrong?", not "how bad?". |
| 3 | FastSAM road masking before the model | Unreliable masks; the raw frame works better. Never on the RQI path. |
| 4 | Frozen DINOv2 + classifier head, trained from the web UI | Right backbone, wrong recipe: ordinal scale as plain classes, no augmentation/stratified CV, "best" checkpoint picked on a tiny noisy split. |

## Era 5 — the clean `ml/` pipeline (2026-07)

- **v1:** frozen DINOv2-small + Ridge, stratified 5-fold CV, 1238 images: QWK 0.83.
  Labels are learnable without re-annotation.
- **v2 (the live model):** three measurable fixes.
  1. **Data recovery:** 676 labelled images missing on disk were re-downloaded from
     Street View with a capture-date guard (only panoramas that existed at labelling
     time): 1238 → **1903 images**.
  2. **Head + features:** SVR-RBF won a 35-cell grid; mean patch token appended to
     CLS. TTA, bottom crop, CLIP and dinov2-base added nothing.
  3. **Tuned cut-points + calibration:** learned class borders instead of .5 rounding;
     isotonic P(bad) calibrator.
- **DINOv3 ViT-S/16:** slightly worse on every metric and failed the gate → v2 stays.

The v2 numbers reported then (QWK 0.889 / MAE 0.195 / AUC 0.970) came from a random
5-fold CV and are **inflated by spatial leakage** — see Era 6. Never cite them.

## Era 6 — honest measurement: spatial CV (2026-11-18)

**The leak.** Frames are ~10 m apart on the same street; a random split puts a test
frame's near-twin in training. A GPS-only k-NN (no image) scored QWK 0.884 on random
CV — almost the champion. On spatial CV it drops to 0.60 while the image model keeps
0.77, so the model does learn the road surface.

**Protocol (now official, `ml/spatial_cv.py`):** coordinates for all 1903 images
(`ml/image_coords.csv`), 1 km grid cells, StratifiedGroupKFold(5), seed 42,
cut-points tuned in a nested inner spatial CV. Why 1 km: the label variogram rises
until ~1 km and is flat from 1 to 5 km; the cell-size curve flattens between 500 m
and 1 km (QWK 0.83 at 200 m, 0.79 at 500 m–1 km, 0.77 at 2 km, 0.66 leaving a whole
region out). 95% cell-bootstrap CI for the champion: QWK [0.69, 0.83], MAE
[0.34, 0.46], AUC [0.89, 0.97].

**Gate** (`ml/evaluate_artifact.py`): QWK ≥ 0.774, MAE ≤ 0.405, AUC ≥ 0.934; to
replace the champion the paired ΔQWK 95% CI must be above 0.

**Challenger grid on spatial CV** (7 feature sets × 5 heads × 3 backbones + last-2-
block fine-tune): everything sensible lands at QWK 0.77–0.80 and no challenger is
measurably better once checked on shifted grids. The ordinal-logistic head ties the
SVR (0.775) and is a cheap fallback.

**Where it fails.**

| Region (same OOF predictions) | n | QWK | AUC | Left out entirely: QWK / AUC |
|---|---|---|---|---|
| Budapest (VII–VIII.) | 229 | 0.40 | **0.78** | **0.23** / 0.76 |
| Törökbálint–Budaörs | 665 | 0.57 | 0.93 | 0.62 / 0.94 |
| Székesfehérvár | 359 | 0.56 | 0.93 | 0.41 / 0.87 |
| Tapolca area | 650 | 0.70 | 0.91 | 0.37 / 0.72 |

Budapest has 229 images from one district and no Kiváló label; urban scenes (tram
rails, setts, parked cars, shadow) differ from rural ones. Per class, recall is
Kiváló 0.83, **Jó 0.43**, Közepes 0.67, Rossz 0.60; errors are almost always one
class off (no Kiváló↔Rossz confusion).

**Recommendations (still open):** a fixed independent holdout region; many places
with few frames each (100–200 m apart), especially Budapest incl. excellent roads;
a sharper Jó definition (second annotator on ~200 frames); measure at segment level
(done in Era 7).

## Era 7 — segment-level aggregation (2026-11-26)

The map shows ~200 m road segments, so we measured segments under the same spatial
protocol (`ml/segment_eval.py`; recipe: `ml/segment_recipe.json`, applied by
`backend/config/segment_aggregation.json`). Segment truth = median human label;
cut-points re-tuned for aggregated scores on training folds only.

| Unit | QWK | MAE | exact | bad-road AUC |
|---|---|---|---|---|
| single frame | 0.780 | 0.404 | 61% | 0.940 |
| **200 m segment, median score** | **0.843** | **0.292** | **71%** | **0.968** |

- **Length matters more than the aggregator.** Median, mean, trimmed mean and mean
  P(bad) are within noise; majority vote of frame classes is clearly worse. The gain
  over a single frame is measurable from 200 m (+0.079 [+0.029, +0.119]).
- **Why the gain is modest:** errors of neighbouring frames are correlated (0.65 at
  10 m, 0.42 at 50 m, 0.19 at 200 m) — the model misjudges a stretch, not a frame.
- **Confidence** = f(frames, score spread, distance of the score from the nearest
  cut-point). The margin carries almost all the signal. Levels on the map:

  | level | share of road | class correct | good/bad wrong |
  |---|---|---|---|
  | high (≥ 0.80) | 19% | 0.93 | 0% |
  | medium | 56% | 0.69 | 9% |
  | low (< 0.55) | 25% | 0.58 | 23% |

- **Frame spacing.** Thinning the labelled runs: 20–30 m is as good as today's 10 m;
  **50 m everywhere + a 30 m second pass on low-confidence segments** matches 10 m
  with 26% of the frames (uniform 30 m: 33%). Re-visiting only bad segments is
  harmful. Defects 1–2 frames long (15% of bad road) are hidden by a 200 m median
  even with dense frames; showing them needs a separate frame-level layer.
- **Regions:** a regional score offset survives aggregation (Tapolca); Budapest does
  not improve (QWK 0.44 → 0.34 on 13 segments) — its problem is the good/bad call.
- **Image age** cannot be fitted: labels describe the image, and repeat captures
  disagree as often months apart as years apart. Age stays a product rule (show the
  capture date; the confidence age factor only after 3 years).

Limits: 19.5 km of road, 35 cells, wide CIs (QWK ±0.08); segment length and level
thresholds were chosen after seeing these tables.

## Era 8 — higher-resolution road features (2026-11-26)

Question: does the 224×224 centre crop lose crack-scale texture? (`ml/extract_features_hires.py`,
`ml/experiments_hires.py`, 170 cells, paired against the champion; "measurably
better" = CI > 0 on the official grid **and** on ≥ 4 of 6 shifted grids.)

- **Refuted.** Road-only DINOv2 features get *worse* with resolution (bottom half:
  QWK 0.781 at 0.5× → 0.761 at 1× → 0.745 at 2×). The signal comes from the scene,
  not crack texture.
- A **second, wider view** helps a little at any resolution (full frame at 336×224
  gains as much as at 588×392, ~+0.02 on the official grid, ~+0.01 across shifts).
- **YOLO damage features add nothing** (alone QWK 0.54–0.62; stacked +0.004 n.s.).
- **One candidate qualifies:** dinov2-base cls+patch + full frame at 588×392
  (block-8 mean+std): QWK 0.796 / MAE 0.382 / AUC 0.940, ΔQWK +0.021 [+0.001,
  +0.040], 4/6 shifted grids. **Not promoted:** smallest margin the rule allows,
  ~11× inference (186 vs 17 ms/frame), Közepes recall drops 0.68 → 0.57. Saved as
  `ml/cache/rqi_model_candidate.joblib` (backend parity verified,
  `ml/check_backend_parity.py`). Re-measure on the holdout region first.

## Era 9 — VLM attributes as features (2026-11-26)

Fable (Claude VLM) workers described all 1903 frames with 15 fixed pavement
attributes (`ml/vlm_attribute_prompt.md`; blinded batches, anchor leakage found
and fixed). Code: `ml/vlm_attributes.py`, `ml/vlm_feature_eval.py`.

| Candidate (official spatial CV) | QWK | MAE | AUC | ΔQWK [95% CI] |
|---|---|---|---|---|
| champion | 0.774 | 0.405 | 0.934 | – |
| VLM's own RQI guess as the prediction | 0.613 | 0.490 | 0.796 | −0.161 |
| attributes alone → ridge | 0.777 | 0.377 | 0.919 | +0.002 |
| **champion score + attributes → ridge (gate artifact)** | **0.805** | **0.344** | **0.940** | **+0.031 [+0.006, +0.056]** |
| same, attributes distilled from DINO (no VLM) | 0.758–0.787 | | | −0.016 … +0.012 |

- **First measurably better challenger:** CI > 0 on 4 of 5 shifted grids; Jó recall
  0.43 → 0.56. The gain is on sealed-crack motorways (expert says Jó, DINO says
  Kiváló), rural lanes and dappled shadow. Budapest does not improve.
- **Not promoted:** it needs one VLM call per frame (~1.3 k tokens); distillation
  into DINO heads keeps none of the gain. Candidate:
  `ml/cache/rqi_model_vlm_candidate.joblib`. Cheaper next tests: VLM only on unsure
  frames, or 1–2 frames per segment.
- **By-product:** `data/vlm/label_audit.csv`, 60 frames for the owner to re-check
  (incl. 9 pixel-identical pairs with different labels); served by the label queue's
  re-check mode.
- **AI-labelling pilot (T-4, earlier):** VLM labellers agreed with the expert at QWK
  0.63 / 0.72, below the model itself (0.84) → no VLM labelling at scale.

## Era 10 — unlabelled frames: regional normalisation, self-training (2026-11-26)

Can the ~15k unlabelled frames fix regional generalisation? (`ml/semisup_regional.py`;
champion recipe, official spatial CV **and** leave-one-area-out (LORO), paired vs
champion; frame positions from Postgres into gitignored `ml/cache/frame_meta.csv`.)
Regional offset = mean predicted − mean true score of an area when that area is
left out (severity units, + = predicted worse). For the champion: Budapest −0.35,
Törökbálint +0.27, Székesfehérvár +0.48, Tapolca −0.32. The model pulls a new
region towards the training average.

| Candidate | spatial ΔQWK [95% CI] | LORO QWK (champion 0.663) | LORO ΔQWK [95% CI] |
|---|---|---|---|
| features − area mean (± whitening) | −0.094 / −0.085 (sig.) | 0.430 / 0.419 | −0.23 / −0.24 (sig.) |
| features − mean of frames within 1 / 3 km | −0.18 … −0.21 (sig.) | 0.28–0.49 | −0.18 … −0.39 (sig.) |
| [features, features − area / 3 km mean] | +0.003 / +0.008 (n.s.) | 0.597 / 0.604 | −0.066 / −0.059 |
| self-training, strict pool (no test cells/area), w 0.3 | +0.009 [−0.003, +0.018] | 0.575 | −0.088 [−0.160, −0.026] |
| self-training, test area's unlabelled frames too | – | 0.645 | −0.017 [−0.054, +0.022] |

- **Regional normalisation fails.** The areas genuinely differ in road quality
  (mean label 1.4–2.7), so subtracting a regional feature mean removes real signal
  together with the camera/scene offset; the regional offsets *grow*.
- **Self-training does not generalise.** About 700 confident, neighbour-consistent
  pseudo-labels per fold barely move spatial CV and hurt a new region. Pseudo-labels
  repeat the model's own regional bias. Using the new region's own frames
  (transductive) also fails to help, and Budapest gets slightly worse in every
  variant.
- **Verdict:** no candidate; the champion stays. Regional generalisation needs
  labels from the region (incl. excellent Budapest roads), not more of the model's
  own guesses.

## Where the model is unsure: novelty and geography (2026-11-26)

Can we tell in advance where predictions are unreliable?

- **Feature-space novelty** (T-33, `ml/novelty.py`): distance to the nearest
  labelled frames in the SVR's feature space. AUC for "class wrong" only 0.56–0.60
  (spatial) / 0.53–0.62 (region left out); flat over deciles 2–9; adds nothing over
  the cut-point margin. **Not used.**
- **Geography** (T-41, `ml/geo_reliability.py`): distance to and density of labelled
  frames, class coverage nearby. AUC 0.48–0.68, worse than the existing confidence
  (0.66 / 0.77); adding it lowers held-out AUC. Spatial CV only probes 0.1–1.25 km,
  so a distance curve cannot be fitted. **Not used as a factor.**
- **Product rule instead (T-44):** a segment with no human label within 3 km is
  capped at "medium" confidence (`unlabelled_area` in `segment_aggregation.json`,
  reason `unlabelled_area`). An honesty rule, not a fitted factor.

## Lessons

1. **With little data the recipe matters, not model size** — the same backbone gave
   QWK 0.83 or junk depending on the training protocol; dinov2-base added nothing.
2. **The evaluation protocol is the real product.** Fixed folds, paired comparisons,
   and folds that separate *space*: for sequential captures random CV measures
   location, not skill.
3. **Data beats architecture:** 665 recovered images were worth more than any trick.
4. **Treat an ordinal scale as ordinal** (regression + tuned cut-points).
5. **A calibrated probability is worth more than a bare class** — the product
   promise is "good or bad, and how sure".
