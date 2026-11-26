# RQI scale: the one definition

[`rqi_scale.json`](rqi_scale.json) is the **only** place the road-quality scale
is defined: levels, labels (HU/EN), colours, labelling rubric, direction,
the bad-road boundary and the levels the model predicts. Backend, ML, frontend,
docs and the labelling UI all read it.

| Value (today) | Key | UI label | EN | Rubric (labelling) |
|---|---|---|---|---|
| 1 | `excellent` | **Kiváló** | Excellent | New or freshly resurfaced, no visible defects. |
| 2 | `good` | **Jó** | Good | Light wear, small cracks, good patches; does not affect driving. |
| 3 | `fair` | **Közepes** | Fair | Visible crack networks, heavy patching, small potholes. |
| 4 | `poor` | **Rossz** | Poor | Deep potholes, broken-up or very rough surface. |
| 5 | `very_poor` | **Nagyon rossz** | Very poor | Barely drivable. The model never predicts it (14 labels, mostly junk). |

- `direction`: `lower_is_better` today (1 = Kiváló). A flip to 5 = best is
  prepared, not applied (see the flip runbook below).
- `bad_from: 3`: a **bad road** means Közepes or worse. That is the event the
  calibrated `P(bad)` (`dino_p_bad`, "Rossz út valószínűsége") predicts. Közepes
  sits in the middle, so it stays `3` in either direction.
- `model_levels: [1, 2, 3, 4]`: the DINO model predicts these. Labels at 5 are
  dropped from training.
- `unknown`: label/colour for a missing score ("Nincs adat").

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
| Backend | `from app.core.rqi_scale import SCALE` | `value_of("good")`, `at_or_better` / `worse_than` (work on SQLAlchemy columns too), `is_bad`, `nearest`, `toward_worse`, `label`, `worst_first_key`, `from_severity` / `to_severity` |
| Frontend | `modules/ui` (`utils/rqiScale.ts`) | `rqiValue('good')`, `atOrBetter`, `worseThan`, `isBadRqi`, `nearestRqiLevel`, `towardWorseRqiLevel`, `rqiScoreLabelHu`, `compareWorstFirst`, `RQI_LEVELS`, `RQI_MODEL_LEVELS`; `getRQIColor` / `getRQILabel` in `utils/rqi.ts` |
| ML | `import rqi_scale as R` (`ml/rqi_scale.py`) | `R.MODEL_LEVELS`, `R.BAD_FROM`, `R.DROPPED_LEVELS`, `R.sql_to_severity()`; `spatial_cv` re-exports `RQI_LABELS`, `BAD_FROM`, `DROPPED_LEVELS` |

**Severity orientation.** Model outputs, model cut-points (`thresholds` in
`ml/cache/rqi_model.joblib`, `backend/config/segment_aggregation.json`,
`ml/segment_recipe.json`), the P(bad) calibrator input and the YOLO damage-%
bands are all expressed in a fixed *severity* numbering: 1 = best, higher =
worse. That is today's numbering. Everything ML stores (`ml/labels.csv`,
caches) is severity too. Values cross into the canonical scale at exactly two
boundaries:

- **ML → DB:** `dino_service` converts with the artifact's `scale_direction`
  (written by `save_model_v2.py`; artifacts without it are severity);
- **DB → ML:** `ml/export_labels.sh` selects `R.sql_to_severity("manual_rqi")`.

So flipping the canonical direction changes no ML number. `labels.csv` is
re-exported byte-identical and the promotion gate reports identical metrics.

## Changing the scale

- **Labels, colours, rubric:** edit, sync, done. No data changes. (Kiváló and Jó
  share the map green today on purpose; the map legend groups them.)
- **`bad_from` or `model_levels`:** these are model decisions. Retrain
  (`ml/save_model_v2.py`: the P(bad) calibrator and cut-points depend on them)
  and pass `ml/evaluate_artifact.py`.
- **Direction:** follow the runbook below. Never edit `direction` by hand.

## Flipping the direction (phase 2 runbook, not applied)

Tooling, all prepared and tested:

- `scripts/sync_rqi_scale.py --flip` mirrors the JSON (values `x -> 6 - x`,
  `bad_from`, `model_levels`, direction) and syncs the copies. Flipping twice
  is the identity.
- `backend/alembic/pending/rqi_flip_direction.py` is the data migration,
  **inactive** outside `versions/`. It mirrors `training_data.manual_rqi`,
  `street_view_images.rqi_score` / `dino_rqi_score`,
  `analysis_metadata.dino_score`, `road_segments.score` / `rqi` and the legacy
  `training_data.manual_dino_rqi` (if present). Probabilities stay untouched.
  Its own inverse, so downgrade runs the same SQL. Upgrade refuses unless the
  deployed JSON is already flipped.
- `backend/scripts/rqi_flip_dry_run.py` gives a READ-ONLY before/after report
  plus invariants on any DB.
- `backend/scripts/rqi_flip_rehearsal.py` runs upgrade + downgrade on a
  throwaway PostGIS container loaded with a pg_dump of the dev data.

Steps, in one change and one release window:

1. Migrate the phase-2 call sites (list below) to the helpers. Each one must
   pass its tests with the JSON flipped locally.
2. `python scripts/sync_rqi_scale.py --flip`, then update the two direction-pin
   tests (`backend/tests/test_rqi_scale.py::test_current_direction_pin`,
   `rqiScale.test.ts` "direction pin"). Every other scale test is written in
   severity terms and must stay green.
3. `git mv backend/alembic/pending/rqi_flip_direction.py backend/alembic/versions/`,
   set its `down_revision` to the current head, and update
   `backend/tests/test_rqi_flip_migration.py` (its `test_is_not_active_yet` and
   `PENDING` path guard phase 1).
4. Run `backend/scripts/rqi_flip_dry_run.py` and `backend/scripts/rqi_flip_rehearsal.py`;
   both must PASS. Then run all gates.
5. Local DB: stop the dev server, run `alembic upgrade head` (from `backend/`).
6. ML check: `bash ml/export_labels.sh`; `git diff --stat ml/labels.csv` must be
   empty, so the gate is unchanged (optionally re-run `ml/evaluate_artifact.py`).
7. Public site, with owner approval: `backend/scripts/publish.py` (upgrades Neon,
   then reloads `street_view_images`) and the `master` push in the same window,
   so the deployed JSON and the data agree.

Rollback: `alembic downgrade <previous>` with the flipped code, then revert the
flip commit. Keep the app stopped in between.

### Phase-2 call sites (owned by other in-flight work on 2026-11-26)

| Area | Where | What to change |
|---|---|---|
| Segment backend | `backend/app/services/segment_aggregation.py`, `backend/config/segment_aggregation.json` | cut-points `[1.51, 2.47, 3.18]` are severity: add `"scale_direction"` and convert frame scores (`SCALE.to_severity`) before cutting, back with `from_severity`. Use `SCALE.is_bad` for the 0/1 fallback ("RQI ≥ 3") |
| Segment ML | `ml/segment_eval.py`, `ml/segment_recipe.json` | `df["rqi"] != 5` → `S.DROPPED_LEVELS`; recipe gets `"scale_direction"` |
| Label queue | `backend/app/services/label_queue*.py`, `backend/scripts/score_frames.py` | `VALID_RQI = (1, 2, 3, 4)` → `SCALE.model_levels`; `model_rqi()` re-implements the cut-points → use `dino_service.rqi_from_score`; regenerate `data/cache/frame_scores.csv` at the flip |
| Map UI | `frontend/src/modules/map/**` | `segments/labels.ts` QUALITY_HU table → `rqiScoreLabelHu`; `RQI_CLASSES` → `RQI_MODEL_LEVELS`; legend chips `rqiLabelHu(1)`… → `rqiValue('excellent')`…; PointDetailCard "/ 5.0 RQI Score" text; route/segment class lists |
| Labelling UI | `frontend/src/modules/training/**` | BottomPanel + `TrainingView/colors.ts` + `TrainingStats` own 3-band colours (≤ 2 / ≤ 3.5) → scale colours; buttons `[1..5]` → `RQI_LEVELS`; title "Minőség (RQI 1–4)"; keys `'1'..'5'`; EvaluationDashboard 1–5 axes |
| GraphQL docs | `backend/app/graphql/types.py`, `backend/app/models/models.py`, `schema.graphql` | descriptions "RQI>=3", "(1.0-4.0)", "1.0 - 5.0" → name the levels |
| Owner decisions | `backend/app/graphql/queries.py` | trainingStats cuts fair/poor at 3.5, adminStats at 3.0: pick one. Whether to collect Nagyon rossz labels (train 5 as 4, or keep dropping it) |
| Tests elsewhere | map, segment, label-queue tests | they pin numbers (`rqiLabelHu(1) === 'Kiváló'`) → write as severity (`sv(1)`) |
