# Glossary

Plain-language definitions of the ML and project terms used across the docs. The
"HU" column gives the Hungarian term used with the owner and in the UI. Numbers in
"Here" are from the official spatial CV (2026-11-18); their source of truth is
[ml/README.md](../ml/README.md).

In one sentence: the model gives a road image a 1–4 grade; to know how far to
trust it we hide images from it, ask it, and compare with the human grade — QWK,
MAE, AUC etc. all measure that agreement from different angles.

## 1. Basics

| Term | HU | Meaning — *here* |
|---|---|---|
| RQI (Road Quality Index) | útminőség-index | Our 1–4 road-quality scale; **lower is better** (1 excellent, 4 poor; 5 unused). |
| Label / ground truth | címke | The human grade for an image; the truth we compare against. *Here: 1903 usable labelled images (`training_data`).* |
| Model / artifact | modell / artifact | The trained predictor saved as one file with everything needed to serve it (head, recipe, cut-points, calibrator). *Here: `ml/cache/rqi_model.joblib` (saved with joblib).* |
| Feature | jellemző | Numbers extracted from an image that the model works on. *Here: DINOv2 turns each image into 768 numbers.* |
| Inference | következtetés | Running the trained model on a new image (vs. training). Map scoring is inference. |

## 2. Metrics

| Term | HU | Meaning — *here* |
|---|---|---|
| Exact accuracy | pontos találat | Share of images where the predicted grade equals the human one. *Here: 61% on unseen streets.* |
| ±1 accuracy | ±1 pontosság | Share off by at most one grade. *Here: 98.5%; no 1↔4 confusions.* |
| MAE (mean absolute error) | átlagos abszolút hiba | Average distance from the human grade, in grades. *Here: 0.405.* |
| QWK (quadratic weighted kappa) | kvadratikusan súlyozott kappa | **Main score.** Agreement on an ordinal scale, punishing big misses quadratically and correcting for chance: 0 = guessing, 1 = perfect, > 0.8 strong. *Here: 0.774 (the old random-fold 0.889 was inflated by spatial leakage).* |
| AUC (ROC AUC) | görbe alatti terület | Quality of the good/bad decision ("is RQI ≥ 3?"): probability that a truly bad road gets a higher risk than a truly good one. 0.5 = coin flip, 1 = perfect. *Here: 0.934 (Budapest only 0.78).* |
| Confusion matrix | tévesztési mátrix | Table of true vs. predicted grade. *Here: errors are almost all next to the diagonal; class 2 is the weakest (recall 0.43).* |
| Baseline | naiv alapvonal | A dumb reference the model must beat. *Here: a GPS-only k-NN (no image) gets QWK 0.60 on spatial CV; the image model 0.77.* |
| Reliability table | megbízhatósági tábla | "When the model says X, what is it really?" *Here: a predicted 4 is truly 4 in 63% of cases and almost never a good road.* |

## 3. Honest evaluation

| Term | HU | Meaning — *here* |
|---|---|---|
| Train/test split | tanító/teszt szétválasztás | Train on some images, grade on hidden ones; only the hidden score counts. |
| Overfitting | túltanulás | Memorising the training images instead of learning a rule. |
| Leakage | szivárgás | The answer sneaks into training (e.g. the same image on both sides) → the score looks too good. |
| Cross-validation (CV), k-fold | keresztvalidáció | Split into k folds, train on k−1, test on the rest, rotate, average. *Here: 5 folds.* |
| Stratified | rétegzett | Each fold gets every grade in proportion. |
| Out-of-fold (OOF) prediction | OOF-predikció | Each image's prediction from the run where it was in the test fold; cut-points and calibration are tuned on these. |
| Nested CV | beágyazott CV | CV inside CV, so that tuning (e.g. cut-points) also happens on hidden data. |
| Spatial leakage | térbeli szivárgás | Street View frames are ~10 m apart, so a random split puts a test frame's near-twin into training. A GPS-only model scores QWK 0.88 on random CV — that is the size of the leak. |
| Spatial / grouped CV (StratifiedGroupKFold) | térbeli CV | Whole 1 km × 1 km grid cells go to one fold, so tests run on streets never seen. **Official since 2026-11-18** (`ml/spatial_cv.py`). |
| Variogram | variogram | How grade difference grows with distance; it flattens at ~1 km, hence the cell size. |
| Leave-one-area-out | régió-kihagyás | Train on three collection areas, test on the fourth: "does it work in a new town?" *Here: QWK 0.66 / AUC 0.87.* |
| Bootstrap CI / paired bootstrap | konfidencia-intervallum | Resample cells to get the metric's 95% band; paired = the band of the *difference* between two models. Excludes 0 → "measurably better". |
| Seed | véletlenmag | Fixed random start for reproducible splits. *Here: `seed=42`.* |

## 4. Model anatomy

| Term | HU | Meaning — *here* |
|---|---|---|
| Backbone | gerinc, „látás-agy" | A large pre-trained vision network used as a feature extractor. *Here: DINOv2-small (Meta).* |
| Frozen | fagyasztott | The backbone is not trained further; only the small head is. Works with little data. |
| CLS / patch tokens | CLS / patch tokenek | DINOv2 outputs: CLS summarises the whole image, patch tokens describe small regions (surface texture). *Here: both, concatenated.* |
| Head | fej | The small model on top of the features that outputs the grade. *Here: SVR-RBF.* |
| Regression vs. classification | regresszió vs. osztályozás | Regression predicts a continuous value (e.g. 2.6) and respects order; classification treats grades as unordered boxes. *Here: regression.* |
| Ordinal scale | sorrendi skála | Order matters, steps need not be equal. RQI is ordinal → QWK + regression. |
| Ridge / SVR-RBF / ordinal logistic | – | Head types: linear, non-linear kernel regression, proportional-odds ordinal model. *Here: SVR-RBF ships; ordinal logistic is an equal fallback.* |
| StandardScaler / pipeline | normalizálás / pipeline | Put features on a common scale; chain scaler → head so training and serving match. |
| Cut-point / threshold | vágópont | Where the continuous score is cut into grades; tuned, not fixed at .5. |
| Calibration, P(bad) | kalibráció, P(rossz) | Turns the score into a trustworthy probability that the road is bad (RQI ≥ 3); isotonic = the method. Shown on the point card as „Rossz út valószínűsége". |
| TTA (test-time augmentation) | – | Averaging predictions over e.g. mirrored copies. Tried; did not help. |
| Class imbalance | osztály-egyensúlytalanság | Some grades have far more examples than others. |
| Epoch | epoch | One full pass over the training data. The shipped head is fit in one go; only the experimental fine-tune (`ml/finetune_lastblocks.py`) uses epochs. |

## 5. Infrastructure

| Term | HU | Meaning — *here* |
|---|---|---|
| Promotion gate | élesítési kapu | A new model ships only if `ml/evaluate_artifact.py` says PASS on spatial CV (and, to replace the champion, is measurably better in the paired comparison). |
| MPS / CUDA / CPU | – | Where compute runs: Apple GPU / NVIDIA GPU / plain CPU. *Here: MPS on the Mac.* |

Related: model history and decisions — [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md);
pipeline and exact numbers — [ml/README.md](../ml/README.md).
