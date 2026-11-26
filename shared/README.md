# RQI scale: the one definition

[`rqi_scale.json`](rqi_scale.json) is the **only** place the road-quality scale
is defined: levels, labels (HU/EN), colours, labelling rubric, direction,
the bad-road boundary and the levels the model predicts. Backend, ML, frontend,
docs and the labelling UI all read it.

**Higher is better** (owner's decision, 2026-11-26: "5 kiváló mehet").

| Value | Key | UI label | EN | Colour | Rubric (labelling) |
|---|---|---|---|---|---|
| 5 | `excellent` | **Kiváló** | Excellent | `#1f5fa8` dark blue | New or freshly resurfaced, no visible defects. |
| 4 | `good` | **Jó** | Good | `#3d9ad6` light blue | Light wear, small cracks, good patches; does not affect driving. |
| 3 | `fair` | **Közepes** | Fair | `#e0a400` amber | Visible crack networks, heavy patching, small potholes. |
| 2 | `poor` | **Rossz** | Poor | `#e8632b` orange | Deep potholes, broken-up or very rough surface. |
| 1 | `very_poor` | **Nagyon rossz** | Very poor | `#b3172c` dark red | Barely drivable. The model never predicts it (14 labels, mostly junk). |

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

**Severity numbering.** Model outputs, model cut-points (`thresholds` in
`ml/cache/rqi_model.joblib`, `backend/config/segment_aggregation.json`,
`ml/segment_recipe.json`, all tagged `"scale_direction": "lower_is_better"`),
the P(bad) calibrator input and the YOLO damage-% bands use a fixed *severity*
numbering: 1 = Kiváló, higher = worse. That was the numbering before the flip.
Everything ML stores (`ml/labels.csv`, caches) is severity too. Values change
numbering only at these boundaries:

- **model → DB:** `dino_service` converts with the artifact's `scale_direction`
  (written by `save_model_v2.py`; artifacts without it are severity);
  `segment_aggregation` converts frame scores to severity, cuts, and converts
  back;
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

## The direction flip (phase 2): status and runbook

Code is flipped on branch `claude/rqi-canonical-scale-e22444`; the **data
migration has NOT run yet** (lead's go pending). The branch must not run against
an unmigrated DB: it would show every stored value inverted. Merge it and
migrate in one step.

Tooling, all tested:

- `backend/alembic/pending/rqi_flip_direction.py` (revision `0006`, revises
  `0005`) is the data migration, **inactive** outside `versions/`. It mirrors
  `training_data.manual_rqi`, `street_view_images.rqi_score` /
  `dino_rqi_score`, `analysis_metadata.dino_score`, `road_segments.score` /
  `rqi` and the legacy `training_data.manual_dino_rqi` (if present).
  Probabilities stay untouched. Its own inverse, so downgrade runs the same
  SQL. Upgrade refuses unless the deployed JSON says `higher_is_better`.
- `backend/scripts/rqi_flip_dry_run.py` gives a READ-ONLY before/after report
  plus invariants on any DB.
- `backend/scripts/rqi_flip_rehearsal.py` runs upgrade + downgrade on a
  throwaway PostGIS container loaded with a pg_dump of the dev data.

Steps at the go:

1. Merge the remaining branches into the integration branch first. Then merge
   this branch. Resolve `rqi_scale.json` / `rqi_scale.py` in favour of this
   branch (the label-queue branch carries an older copy).
2. Migrate the call sites in the newly merged code (checklist below), with
   gates green.
3. `git mv backend/alembic/pending/rqi_flip_direction.py backend/alembic/versions/`,
   re-check `down_revision` is the head, and update
   `backend/tests/test_rqi_flip_migration.py` (`test_is_not_active_yet`, `PENDING`).
4. Run `backend/scripts/rqi_flip_dry_run.py` and `backend/scripts/rqi_flip_rehearsal.py`;
   both must PASS.
5. Local DB: stop the dev server, run `alembic upgrade head` (from `backend/`).
   Then regenerate `data/cache/frame_scores.csv` (label queue).
6. ML check: `bash ml/export_labels.sh`; `git diff --stat ml/labels.csv` must be
   empty. Optionally re-run `ml/evaluate_artifact.py`.
7. Public site, with owner approval: `backend/scripts/publish.py` (upgrades Neon,
   then reloads `street_view_images`) and the `master` push in the same window.

Rollback: `alembic downgrade 0005` with the flipped code, then revert the flip
commit. Keep the app stopped in between.

### Checklist for code merged after this branch

| Branch / area | What to check |
|---|---|
| label queue (`claude/label-queue-quick-rate-*`) | already uses `SCALE` / `from_severity`; keep this branch's `rqi_scale.*` on conflict; run its tests with the flipped JSON; the docstring "P(RQI >= 3)" becomes Közepes or worse; regenerate `frame_scores.csv` after the migration |
| QA (`claude/qa-analysis-layer-*`) | e2e tests: RouteQualityCard test ids are now `route-bar-<key>` / `route-class-<key>` (level key, not number); `segment_read.py` / `queries.py` hunks |
| frame quality (`claude/frame-quality-audit-*`) | `road_segments.py`: this branch changed one line (report loop over `SCALE.model_levels`) |
| VLM attributes (`claude/ml-vlm-attributes-*`) | edits `ml/save_model_v2.py`: keep the `R.*` constants and the artifact's `scale_direction` |
| any new code | no literal levels; lists best first; tests via `sv()` |
| owner decisions | trainingStats cuts fair/poor at the Közepes/Rossz midpoint, adminStats at Közepes: pick one. Whether to collect Nagyon rossz labels (train them as Rossz, or keep dropping them). Whether to drop the unused `manual_dino_rqi` column |
