# RQI scale: the one definition

[`rqi_scale.json`](rqi_scale.json) is the **only** place the road-quality scale
is defined: levels, labels (HU/EN), colours, labelling rubric, direction,
the bad-road boundary and the levels the model predicts. Backend, ML, frontend,
docs and the labelling UI all read it.

**Higher is better** (owner's decision, 2026-11-26: "5 kiváló mehet").

| Value | Key | UI label | EN | Colour |
|---|---|---|---|---|
| 5 | `excellent` | **Kiváló** | Excellent | `#1f5fa8` dark blue |
| 4 | `good` | **Jó** | Good | `#3d9ad6` light blue |
| 3 | `fair` | **Közepes** | Fair | `#e0a400` amber |
| 2 | `poor` | **Rossz** | Poor | `#e8632b` orange |
| 1 | `very_poor` | **Nagyon rossz** | Very poor | `#b3172c` dark red |

The labelling rubric (one line per level, HU + EN, plus `rubric_note_*`: rate the
visible surface only, never the speed limit or road class) lives in the JSON and is
shown on the quick-rate screen and the review panel; the human-readable version with
the driver's test is [docs/TrainingGuide.md](../docs/TrainingGuide.md).

- `direction: higher_is_better`. Until 2026-11-26 the numbering was the
  mirror image (1 = Kiváló); stored data is converted by the migration
  `rqi_flip_direction` (new = 6 − old). See the flip section below.
- `bad_from: 3`: a **bad road** means Közepes or worse, i.e. value ≤ 3. That is
  the event the calibrated `P(bad)` (`dino_p_bad`, "Rossz út valószínűsége")
  predicts. Közepes is the middle, so it is 3 in either numbering.
- `model_levels: [2, 3, 4, 5]`: the DINO model predicts Rossz … Kiváló. Labels
  at Nagyon rossz are dropped from training.
- `unknown`: label/colour for a missing score ("Nincs adat", `#888`).
- **Colours:** five distinct, colour-blind-safe colours, ordered good → bad.
  Validated with the dataviz palette checker: all-pairs deutan/protan
  ΔE ≥ 9.7 (target ≥ 8), normal vision ≥ 15.3, OKLCH lightness and chroma inside
  the light-mode band. The amber and the light blue are below 3:1 contrast on a
  light base map, so lines are drawn with the dark casing the segment layer
  already uses. Blue instead of green for "good" is deliberate: a green-to-red
  scale cannot be made colour-blind-safe.

## Copies (do not edit)

Vercel deploys only `backend/` and Vite bundles only `frontend/`, so two
byte-identical copies ship with the code:
`backend/app/core/rqi_scale.json` and `frontend/src/modules/ui/utils/rqiScale.json`.
After editing the shared file run `python scripts/sync_rqi_scale.py`. Backend
pytest and Vitest fail if a copy drifts (`--check` does the same).

## Rules for code

Never write a bare level number or threshold (`<= 2`, `>= 3`, `[1, 2, 3, 4]`,
`!= 5`, `6 - x`). Use the helpers:

| Where | Import | Main helpers |
|---|---|---|
| Backend | `from app.core.rqi_scale import SCALE` | `value_of("good")`, `at_or_better` / `worse_than` (work on SQLAlchemy columns too), `is_bad`, `nearest`, `toward_worse`, `label`, `worst_first_key`, `model_levels`, `from_severity` / `to_severity` |
| Frontend | `modules/ui` (`utils/rqiScale.ts`) | `rqiValue('good')`, `rqiLevel(v)`, `atOrBetter`, `worseThan`, `isBadRqi`, `nearestRqiLevel`, `towardWorseRqiLevel`, `rqiScoreLabelHu`, `rqiTextColor`, `compareWorstFirst`, `RQI_LEVELS` / `RQI_MODEL_LEVELS` (best first); `getRQIColor` / `getRQILabel` in `utils/rqi.ts` |
| ML | `import rqi_scale as R` (`ml/rqi_scale.py`) | `R.MODEL_LEVELS`, `R.BAD_FROM`, `R.DROPPED_LEVELS`, `R.sql_to_severity()`; `spatial_cv` re-exports `RQI_LABELS`, `BAD_FROM`, `DROPPED_LEVELS` |

Lists that hold one number per level are ordered **best first** (for example
`RouteQuality.lengthByRqi` = metres in Kiváló, Jó, Közepes, Rossz). Index them
through `RQI_MODEL_LEVELS` / `SCALE.model_levels`, never with `i + 1`. In tests,
write values as `sv(k)` (`SCALE.from_severity` / `fromSeverity`) so they hold in
either numbering.

**Segment layer.** `backend/config/segment_aggregation.json` restates the scale
for the segment code (`"scale": {"classes", "higher_is_worse", "bad_class"}` +
canonical-numbering `thresholds`, read only by `RqiScale` in
`segment_aggregation.py`). `backend/tests/test_rqi_scale.py` fails if that block
disagrees with this file, or if its thresholds are not the ML recipe's mirrored;
`scripts/sync_rqi_scale.py --flip` mirrors it together with the JSON.

**Severity numbering.** Model outputs, model cut-points (`thresholds` in
`ml/cache/rqi_model.joblib` and `ml/segment_recipe.json`, the latter tagged
`"scale_direction": "lower_is_better"`),
the P(bad) calibrator input and the YOLO damage-% bands use a fixed *severity*
numbering: 1 = Kiváló, higher = worse. That was the numbering before the flip.
Everything ML stores (`ml/labels.csv`, caches) is severity too. Values change
numbering only at these boundaries:

- **model → DB:** `dino_service` converts with the artifact's `scale_direction`
  (written by `save_model_v2.py`; artifacts without it are severity);
- **DB → ML:** `ml/export_labels.sh` selects `R.sql_to_severity("manual_rqi")`,
  which is `(6 - manual_rqi)` now.

So the flip changed no ML number. The promotion gate output is byte-identical
before and after (QWK 0.774, MAE 0.405, AUC 0.934), and the flipped DB exports
the identical `labels.csv` (proved by the rehearsal below).

## Changing the scale

- **Labels, colours, rubric:** edit, sync, done. No data changes.
- **`bad_from` or `model_levels`:** these are model decisions. Retrain
  (`ml/save_model_v2.py`: the P(bad) calibrator and cut-points depend on them)
  and pass `ml/evaluate_artifact.py`.
- **Direction:** `scripts/sync_rqi_scale.py --flip` plus the data migration
  below. Never edit `direction` by hand.

## The direction flip (done 2026-11-26)

Owner's decision: 5 = Kiváló. Code, segment config and copies were flipped with
`scripts/sync_rqi_scale.py --flip`; stored data with Alembic
`backend/alembic/versions/0006_rqi_flip_direction.py` (new = 6 − old for
`manual_rqi`, `rqi_score`, `dino_rqi_score`, `analysis_metadata.dino_score` /
`dino_rqi_score_prev`, `road_segments.score` / `rqi`, legacy `manual_dino_rqi`;
probabilities untouched; its own inverse). Applied to the dev DB (backup
`data/backups/pre_rqi_flip_202611261309.dump`); verified: `road_segments` rebuilt to
the identical class split, label re-export identical in ML numbering, gate output
unchanged. **Neon gets it with the next release** ([docs/RELEASE.md](../docs/RELEASE.md):
`publish.py` upgrades the schema, then reloads the data).

Tools kept for any future change of numbering: `backend/scripts/rqi_flip_dry_run.py`
(read-only before/after report on a DB) and `backend/scripts/rqi_flip_rehearsal.py`
(upgrade + downgrade on a throwaway PostGIS container). A further flip would be a new
migration with the same SQL.

### Rules for new code

| Area | What to check |
|---|---|
| any new code | no literal levels; per-level lists best first; tests via `sv()`; anything that stores an RQI value must be converted if the numbering ever changes |
| segment recipe changes | a new `ml/segment_recipe.json` (severity) must reach `backend/config/segment_aggregation.json` mirrored (`flip_segment_config`); `test_rqi_scale.py` checks it |
| open owner decisions | trainingStats cuts fair/poor at the Közepes/Rossz midpoint, adminStats at Közepes: pick one. Collect Nagyon rossz labels (train them as Rossz) or keep dropping them. Drop the unused `manual_dino_rqi` column |
