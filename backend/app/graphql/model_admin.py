"""Admin "Modell" panel: label progress, retrain + gate report, promotion (T-68).
Admin-only; not on the public read schema. Logic: app/services/model_ops.py."""
from __future__ import annotations

import os
from typing import List, Optional

import strawberry

from app.graphql.permissions import IsAdmin
from app.graphql.resolver_helpers import get_db_session


@strawberry.type
class AreaCount:
    area: str
    count: int


@strawberry.type
class LevelCount:
    level: int
    count: int


@strawberry.type
class ModelAdmin:
    trained_on: int            # frames in the champion's training set
    new_labels: int            # human labels the champion has not seen
    new_by_area: List[AreaCount]
    new_by_level: List[LevelCount]
    sprint_labelled: int
    sprint_target: int
    hint: str
    candidate_available: bool
    report: List[str]          # plain-Hungarian gate report of the latest retrain
    report_verdict: Optional[bool]
    report_gate_pass: Optional[bool]
    report_at: Optional[str]
    confirm_phrase: str


@strawberry.type
class ModelAdminQuery:
    @strawberry.field(permission_classes=[IsAdmin])
    def model_admin(self) -> ModelAdmin:
        from sqlalchemy import text

        from app.core.rqi_scale import SCALE
        from app.services import label_queue as lq
        from app.services import label_queue_store as store
        from app.services import model_ops as ops

        trained = ops.champion_training_set()
        db = get_db_session()
        try:
            rows = db.execute(text(
                "SELECT td.image_filename, td.manual_rqi, svi.latitude, svi.longitude "
                "FROM training_data td LEFT JOIN street_view_images svi "
                "ON svi.image_url = 'images/' || td.image_filename "
                "WHERE td.manual_rqi IS NOT NULL")).all()
            sprint = store.sprint_count(db)
        finally:
            db.close()
        n, by_area, by_level = ops.summarize_new_labels(rows, trained, SCALE.nearest, lq.area_of)
        summary = ops.latest_summary()
        return ModelAdmin(
            trained_on=len(trained), new_labels=n,
            new_by_area=[AreaCount(area=a, count=c) for a, c in sorted(by_area.items(), key=lambda x: -x[1])],
            new_by_level=[LevelCount(level=lv, count=by_level.get(lv, 0)) for lv in SCALE.values],
            sprint_labelled=sprint, sprint_target=lq.SPRINT_TARGET,
            hint=ops.learning_curve_hint(n),
            candidate_available=os.path.isfile(ops.CANDIDATE),
            report=ops.describe_report(summary),
            report_verdict=None if summary is None else bool(summary.get("verdict")),
            report_gate_pass=None if summary is None else bool(summary.get("gate_pass")),
            report_at=None if summary is None else summary.get("_at"),
            confirm_phrase=ops.CONFIRM_PHRASE,
        )


@strawberry.type
class ModelAdminMutation:
    @strawberry.mutation(permission_classes=[IsAdmin])
    def start_retrain(self) -> str:
        """Run ml/retrain.py (make retrain) as a job; returns the job id (SSE)."""
        from app.services import model_ops as ops

        return ops.start_retrain()

    @strawberry.mutation(permission_classes=[IsAdmin])
    def promote_candidate(self, confirm: str) -> str:
        """Swap the candidate in (backup kept), reload the live model, refresh the
        model card as a job. Needs the exact confirmation phrase and a PASS gate."""
        from app.services import model_ops as ops

        backup = ops.promote(confirm, summary=ops.latest_summary())
        ops.reload_live_model()
        try:
            ops.start_model_card()
        except ops.PromotionError:
            pass  # another model job is running; the card can be refreshed later
        return f"Élesítve. Az előző modell mentése: {os.path.relpath(backup, ops.ROOT)}"

    @strawberry.mutation(permission_classes=[IsAdmin])
    def start_rescore_and_rebuild(self) -> str:
        """Follow-up job after a promotion: re-score frames, rebuild segments."""
        from app.services import model_ops as ops

        return ops.start_rescore_and_rebuild()
