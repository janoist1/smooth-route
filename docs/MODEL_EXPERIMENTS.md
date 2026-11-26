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

## OSM `smoothness` / `surface` tags (T-52, 2026-11-26)

Could OpenStreetMap's crowd-sourced `smoothness=` and `surface=` tags serve as free
labels (e.g. for Budapest) or as model context? `ml/osm_tags.py`, offline: cached
Overpass tiles (101 k highway ways), frames snapped to the nearest heading-compatible
way within 20 m (the segment builder's rule).

- **Coverage.** `smoothness` is on 12.6% of ways: 13% of labelled frames (85% in
  Budapest, 0% around Tapolca and Törökbálint), 16% of today's new frames.
  `surface` is on 90% of labelled frames — and almost all of it is `asphalt`
  (1705 of 1903; the rest untagged). No labelled or new frame is on `sett`,
  `cobblestone` or `paving_stones`.
- **Agreement with the human label is weak** (252 tagged frames on 47 ways):
  Spearman 0.48, QWK 0.42, exact 60%; the model on the same frames reaches QWK 0.66.
  In Budapest alone: OSM QWK 0.36 / bad-road AUC 0.71 vs the model's 0.50 / 0.83.
  OSM never says worse than `intermediate` on these roads, so it cannot mark Rossz,
  and one tag covers a whole way (often kilometres) while the road changes every
  ~100 m.
- **Surface does not explain T-43.** All six urban over-rating frames lie on ways
  tagged `asphalt` (two of them `good` / `excellent`): the setts and markings the
  model reacts to are crossings and tram areas inside an asphalt way, invisible to
  OSM tags.
- **As features** (champion score + surface one-hot + smoothness → ridge stack,
  same harness as Era 9): QWK 0.772 / MAE 0.414 / AUC
  0.924, ΔQWK −0.002 [−0.017, +0.016] — no gain; in Budapest it is worse (QWK
  0.40 → 0.25, AUC 0.78 → 0.63).

**Decision:** OSM tags are **not** used as labels, features or a validation set: too
sparse outside Budapest, too coarse (per way), mostly "asphalt", and less accurate
than the model where they exist. An "OSM says …" line on the segment card is not
worth the confusion of a second, weaker opinion. Budapest still needs human labels.

## Era 11 — how many and which new labels lift the model (2026-11-26)

Simulation on the cached DINO features (no images), champion head, official spatial
protocol throughout. Code: `ml/learning_curve.py` (outputs `ml/cache/learning_curve_*.json`).

**Recommendation for the owner:** label new streets, not more frames on the same
streets. Label **~1000 frames, at most one every 50–100 m, on roads that have no
labels yet** (all areas, Budapest included). Expect about **+0.02 to +0.04 QWK**.
About +0.025 is the smallest gain the promotion gate can confirm. 500 such labels
give about +0.015 to +0.02, which is probably too small to confirm. For Budapest,
label the streets you want rated: the gain stays within a few hundred metres.

| 1. Learning curve (share of training labels) | 25 % | 50 % | 75 % | 100 % |
|---|---|---|---|---|
| whole 1 km cells removed (= fewer streets), QWK | 0.668 | 0.727 | 0.772 | 0.774 |
| single frames removed (same streets, sparser), QWK | 0.756 | 0.769 | 0.779 | 0.774 |

- **Coverage drives the curve, not density.** Keeping every street but only a
  quarter of the frames costs −0.018 QWK. Keeping a quarter of the streets costs
  −0.106.
- **Fitted gain from more labels on new streets:** the power-law fit gives +250 →
  +0.008, +500 → +0.015, +1000 → +0.025 QWK. The log-linear fit gives +0.011,
  +0.021, +0.037. For MAE (+1000): −0.04 to −0.06. For AUC (+1000): +0.008 to +0.013.
- **This is an optimistic upper bound.** The last step (75 → 100 %) added only
  +0.002, and the seed-bootstrap intervals (±0.001–0.01) ignore that the curve
  stops at 4 areas.

**2. Budapest.** Train on the other three areas plus k Budapest labels. Test on a
held-out Budapest cell, with no added label within 200 m of a test frame. QWK is
measured on Budapest's 229 frames, mean over 5 seeds.

| Budapest labels added | 0 | 25 | 50 | 100 | ~170 (all) |
|---|---|---|---|---|---|
| test = 500 m cell, QWK | 0.23 | 0.23 | 0.25 | 0.26 | **0.36** |
| test = 500 m cell, MAE | 0.48 | 0.44 | 0.44 | 0.44 | 0.43 |
| test = 1 km cell (other district), QWK | 0.23 | 0.19 | 0.11 | 0.17 | 0.20 |

- **The gain is local.** Labels from the same neighbourhood help (+0.14 QWK with
  ~170 labels). Labels from the other district help nothing.
- **Official CV overstates Budapest.** Its Budapest QWK of 0.40–0.42 comes from
  ~21 labelled frames just across a cell edge. With a 200 m buffer, the same split
  gives 0.20.
- Budapest has only 4 cells of 1 km, and 2 of them hold 212 of the 229 frames, so
  these Budapest numbers are noisy.

**3. Which frames to label.** Start from half the training cells (QWK 0.729). Add
frames from the other half using the label-queue strategies. All strategies draw
from the same pool, thinned to 50 m (~130 candidates per fold). 8 seeds.

| Added labels | random | diverse | uncertain | mixed | random, consecutive frames |
|---|---|---|---|---|---|
| 50 | 0.761 | 0.762 | 0.758 | 0.764 | 0.756 |
| 100 | 0.775 | 0.771 | 0.774 | 0.775 | 0.772 |
| ~130 (all thinned) | 0.778 | 0.780 | 0.780 | 0.779 | **0.764** (0/8 seeds better) |

- **~130 spread-out frames from new cells are worth all ~810 frames there.** They
  reach 0.778, versus 0.774 when every frame is used.
- **The queue strategy barely matters:** every strategy is within ±0.004 of random,
  well within the noise. Keep `mixed`.
- **What matters** is new streets and the 50 m near-duplicate rule, which the queue
  already enforces.
- Caveat: the candidate pool is small and comes from areas already labelled, so an
  "uncertain" advantage on a large, truly new pool cannot be ruled out.

## Era 12 — Pairwise "which road is worse?" judgments (pilot, T-53, 2026-11-26)

> **TL;DR:** Fable judges compared 117 blind pairs of labelled frames. On the
> 87 pairs where the human grades differ, they picked the human's worse road
> **88.5 %** of the time (95 % CI 80–94 %), and **95 %** on the three quarters
> they rated high or medium confidence. That is far better than the order
> implied by absolute VLM grades (65.5 %, because a third come out tied), and
> **exactly as good as the champion model on the same pairs (88.5 %)**, with
> different mistakes. Good enough for ranking labels from confident pairs
> outside Budapest; not a replacement for human grades.

**Setup.** `ml/pairwise_pilot.py make` sampled pairs from the 1903 labelled
frames (`ml/cache/dataset_v2.csv`, 1 = best). It kept usable road frames
only, stratified by human |Δ| (30 / 45 / 30 / 12 pairs for Δ = 0 / 1 / 2 / 3),
half within one region and half across, at least 300 m apart (neighbouring
frames are often the same panorama), each frame used once, A/B order random.
Frames were hard-linked under blind names (`data/vlm/pairwise/run1/`,
gitignored); 12 fresh Fable subagents judged ≤ 10 pairs each, two at a time,
seeing only their own pairs. Prompt: the pilot rubric as context plus "which
pavement is in worse condition, A or B, or equal?" and a confidence. The
judges returned JSON in their reply; their own file writes did not reach
disk. `ml/pairwise_pilot.py score` compares against the human order, the
absolute VLM grades of Era 9 (`vlm_attributes.csv` → `rqi_guess`) and the
champion's out-of-fold scores (`oof_spatial_champion.csv`).

| order source (pairs with human Δ ≥ 1, n = 87) | correct | notes |
|---|---|---|
| **VLM pairwise** | **88.5 %** [80.1, 93.6] | always decides; Δ1 84 %, Δ2 90 %, Δ3 100 % |
| VLM pairwise, high + medium confidence (65 pairs) | **95.4 %** | high 25/25, medium 92.5 %, low 68 % |
| VLM absolute grades (Era 9) | 65.5 % [55, 75] | 34.5 % ties, **0** reversed; coin-flipped ties → ~83 % |
| champion model (OOF score) | 88.5 % [80.1, 93.6] | Δ1 84 %, Δ2 90 %, Δ3 100 % |

- **Different errors:** both right on 70 pairs, VLM only 7, model only 7,
  both wrong 3. A combination could reach ~96 % on these pairs.
- **Region:** within-region 90.7 % vs cross-region 86.4 % (model 86 / 91 %).
  Pairs with a Budapest frame: VLM **67 %** (n = 18), model 78 %. Five of the
  ten VLM errors involve Budapest.
- **Ties:** on equal-grade pairs the judges said "equal" only 10 % of the
  time (prompt allowed it only when no difference was visible). Pairwise data
  therefore carries no tie information; treat Δ = 0 pairs as noise.
- 7 of the 10 errors were low-confidence calls, 8 of 10 had Δ = 1.

**Verdict.** Reliable enough to *generate ranking labels* if filtered:
keep only high/medium-confidence judgments (≈ 95 % agreement on ~75 % of
pairs), avoid Budapest until it has more human labels, and use the pairs as
an extra ranking loss next to human grades, never instead of them. Because
the VLM is not better than the champion on average but errs differently,
the most useful pairs are the ones where it **disagrees** with the model;
those go to the owner first. The same "which is worse?" format suits the
planned swipe game for faster human labelling. Pilot size is small
(87 decisive pairs); confirm on ~300 pairs before training on them.

## Era 13 — Ranking-augmented head with VLM pair labels (T-62, 2026-11-26)

Do VLM "which road is worse?" judgments improve the head as an extra ranking
term? (`ml/rank_head.py`.) Model: champion features, Nyström-RBF ridge on the human
labels **+ λ × logistic pairwise loss** on score differences. Two bases: plain
kernel ridge, and the champion SVR + a ridge correction shaped by the pairs
(`--svr-base`). λ ∈ {0, 0.3, 1, 3}, also chosen nested. Evaluated on human labels
only, official spatial CV + leave-one-area-out (LORO); pairs with a frame in a test
cell / the test area are dropped. Paired vs the champion SVR and vs λ = 0 (the
same model without pairs).

| Pairs | base | spatial ΔQWK vs champion (best λ / nested) | LORO ΔQWK vs champion (best λ / nested) | effect of more λ |
|---|---|---|---|---|
| 114 pilot pairs (labelled frames, sanity) | SVR | +0.014 / +0.014 (= λ 0 control) | +0.005 / +0.005 | none (±0.01 vs λ 0) |
| 171 unsure pairs (QA, unlabelled, non-Budapest) | SVR | +0.005 / +0.014 (= λ 0 control) | −0.013 / −0.021 | worse: λ 3 → −0.024 / −0.062 |
| 171 unsure pairs | kernel ridge | −0.018 / −0.011 | −0.039 / −0.080 | worse |

- **No gain.** On the SVR base the pairs move nothing beyond the λ = 0 control
  (spatial ±0.01), and more weight hurts monotonically. Nested λ picks ≈ 0.
- The pilot's apparent LORO gain on the kernel-ridge base (+0.07–0.09 vs λ 0) only
  closed that base's own gap to the SVR (−0.049). With the SVR as base it vanished.
  That is the sanity check working as intended.
- The unsure pairs are hard by construction: both frames sit within 0.25 of a cut
  and the champion orders them 56/44. Judge accuracy there is unknown and position
  bias is visible ("B is worse" 58%). About 170 noisy orderings carry less
  information than the 1,903 human grades they compete with.
- **Verdict:** no candidate; the champion stays. Pair judgments are better spent as
  a *label-queue filter* (which unsure frames the human should grade first) than
  as a training signal.

## Era 14 — The YOLO defect model measured on the owner's polygons (T-67, 2026-11-26)

The defect polygons on the detail card come from the owner-trained
`data/models/yolov8m-seg-best-20260105.pt` (9 classes, trained on Colab
2026-01-05 18:21; 364 train / 78 val frames). Ground truth = `training_data.annotations`:
**400 frames, 1,341 polygons** (plus 884 "ignore" regions). Per class (frames /
polygons): degradation 226/288, alligator_crack 139/179, patch 120/198, shadow
118/170, trans_crack 99/115, pothole 72/130, marking 63/189, manhole 40/50,
long_crack 20/22. Every annotation was made 2026-01-03…05, so most frames are
the model's own training data. The only clean held-out set is the **50 frames
edited after the training run** (236 polygons). `ml/yolo_eval.py`, ultralytics
validator, conf 0.001.

| class | held-out n | box P / R | box mAP50 | mask mAP50 | in-sample mask mAP50 |
|---|---|---|---|---|---|
| trans_crack | 20 | 0.58 / 0.35 | 0.35 | 0.44 | 0.87 |
| alligator_crack | 24 | 0.67 / 0.21 | 0.20 | 0.15 | 0.76 |
| pothole | 12 | 0.57 / 0.17 | 0.21 | 0.23 | 0.87 |
| patch | 23 | 0.42 / 0.13 | 0.15 | 0.12 | 0.87 |
| degradation | 37 | 0.70 / 0.39 | 0.46 | 0.21 | 0.84 |
| shadow | 29 | 0.53 / 0.45 | 0.50 | 0.50 | 0.90 |
| manhole | 4 | 0.84 / 0.50 | 0.56 | 0.56 | 0.94 |
| marking | 84 | 0.39 / 0.02 | 0.19 | 0.15 | 0.61 |
| long_crack | 3 | – / 0.00 | 0.00 | 0.00 | 0.65 |
| **all** | 236 | 0.63 / 0.25 | **0.29** | **0.26** | 0.85 |

- **Heavily overfit.** In-sample mask mAP50 is 0.85, held-out 0.26 (the
  checkpoint's own Colab val: 0.38). It memorised 364 frames.
- **The failure is missing defects, not mislabelling them.** On held-out frames
  most true polygons get no detection (recall 0.25). Damage classes are rarely
  confused with each other. Lane markings are almost never detected (2/84), so
  the "marking" class does not stop marking → crack false positives (seen in
  Era 8). False positives on clean road come mostly from shadow (10) and
  degradation/patch (9).
- The held-out set is small (3–37 polygons per damage class), so per-class
  numbers are rough; the in-sample/held-out gap is not.
- YOLO adds nothing to the RQI score (Era 8); its value is the explanatory
  polygons on the card.

**Plan (if defect marking matters):**
1. **Retrain, yes, but data first.** Target ≥ 300 polygons and ≥ 150 frames per
   kept class (today 22–288 polygons): about 1,200–1,500 annotated frames (~4×
   today). Spread them over many places, incl. Budapest, plus ~200 hard-negative
   frames (good roads with lane markings, crosswalks, shadows, manholes) and
   their "ignore"/background areas.
2. **Fewer classes:** merge long_crack + trans_crack → **crack**; keep
   alligator_crack, pothole, patch, degradation; keep manhole and shadow as
   distractors; **drop marking as a class** and use hard negatives instead.
   That leaves 5 damage + 2 distractor classes.
3. **Smaller model + honest split:** yolov8s-seg (11 M params instead of 27 M),
   strong augmentation, and a held-out split by 1 km cell or area (like the RQI
   gate), never random frames. Gate on held-out mask mAP50 per class.
4. **GPU:** the existing Colab export (`backend/app/services/training/colab_provider.py`) is
   enough. yolov8s-seg on ~1.5 k frames × 100 epochs is about 1–1.5 h on a
   Colab T4 (half a day on the M1 MPS). No GPU purchase needed.
5. Until then, show YOLO polygons only at conf ≥ 0.5 and label them on the card
   as indicative.

## Era 15 — Codex (gpt-6.1-sol) as an image labeller (T-89, 2026-11-26)

**Question.** Can Codex label frames well enough to fill the Budapest label gap
(2 % of Budapest frames labelled)?

**Setup.** The T-4 pilot exactly: 200 blind frames + 12 expert anchors, old 1–4
severity scale, same rubric; frames attached to `codex exec` in batches of 20
(read-only, empty workspace, no access to the key). Then 239 of the 332 other
owner-labelled Budapest frames the same way (stopped early, result settled).
Model = spatial-CV out-of-fold prediction (honest). Paired cell-free bootstrap.

| Set | Codex QWK | Model QWK | ΔQWK (95 % CI) | Codex exact / bad-acc |
|---|---|---|---|---|
| Pilot, 200 frames, 4 areas | 0.749 | 0.835 | −0.086 [−0.160, −0.018] | 60.5 % / 80.0 % |
| Budapest, 239 frames | 0.260 | 0.623 | −0.362 [−0.488, −0.234] | 53.1 % / 61.5 % |

- Best AI labeller so far (Fable 0.631, Opus 0.715 on the same 200), but clearly
  below the model. Codex + model averages are no better than the model (±0.00 at
  1/3 weight; worse at 1/2, and sensitive to the rounding direction).
- The early "Codex beats the model in Budapest" signal (22 frames: 0.58 vs 0.16)
  was noise. On 239 Budapest frames Codex calls roads the owner rates Kiváló/Jó
  "Közepes" (bias +0.23; 15 of 30 owner-Kiváló → Közepes): it reads urban wear,
  patches and markings as damage, unlike the owner. High-confidence answers are
  no better (QWK 0.23 on 135 frames).
- **Decision:** no Codex labels for training or on the map. Codex stays on code
  work (tickets, reviews). The lever is still the owner's labels in new areas.
  Upload cost: ~35 MB of images.

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
