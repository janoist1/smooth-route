"""GraphQL surface of the label queue ("Gyors címkézés" quick-rate screen).

Own module (merged into the root Query/Mutation in schema.py) so it does not
collide with other work in queries.py / mutations.py. Everything here is
admin-only, like the review page; it is not part of the public read schema.
Logic: app/services/label_queue.py (pure) + label_queue_store.py (DB).
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

import strawberry

from app.graphql.permissions import IsAdmin
from app.graphql.resolver_helpers import get_db_session
from app.services.capture_date import format_capture_date


@strawberry.enum
class LabelQueueStrategy(Enum):
    UNCERTAIN = "uncertain"
    DIVERSE = "diverse"
    MIXED = "mixed"


@strawberry.type
class LabelQueueItem:
    id: int
    image_url: str
    latitude: float
    longitude: float
    heading: Optional[float]
    capture_date: Optional[str]
    street_view_url: str
    reason: str
    area: str
    uncertainty: Optional[float]
    cell_labels: int
    boundary: Optional[str]  # nearest decision boundary, e.g. "2|3"
    # The model's guess. The UI keeps it hidden until the frame is rated
    # (anchoring bias); it is here so the reveal needs no extra round trip.
    model_score: Optional[float]
    model_rqi: Optional[int]
    model_p_bad: Optional[float]


@strawberry.type
class LabelQueueStats:
    total_labelled: int
    labelled_today: int
    eligible: int
    scored: int


@strawberry.type
class LabelQueueResult:
    strategy: LabelQueueStrategy
    items: List[LabelQueueItem]
    stats: LabelQueueStats


@strawberry.type
class LabelExample:
    rqi: int
    id: int
    image_url: str


@strawberry.input
class QuickLabelInput:
    point_id: int
    rqi: int
    strategy: Optional[str] = None
    reason: Optional[str] = None
    revealed_model: bool = False
    elapsed_ms: Optional[int] = None


@strawberry.type
class QuickLabelResult:
    point_id: int
    image_filename: str
    rqi: int
    total_labelled: int
    labelled_today: int


def _street_view_url(lat: float, lon: float, heading, pitch, pano_id) -> str:
    base = "https://www.google.com/maps/@?api=1&map_action=pano"
    view = f"&heading={heading or 0}&pitch={pitch or 0}"
    if pano_id:
        return f"{base}&pano={pano_id}{view}"
    return f"{base}&viewpoint={lat},{lon}{view}"


def _labeller(info: strawberry.Info) -> Optional[str]:
    identity = info.context.get("identity")
    return getattr(identity, "clerk_id", None)


@strawberry.type
class LabelQueueQuery:
    @strawberry.field(permission_classes=[IsAdmin])
    def label_queue(
        self,
        strategy: LabelQueueStrategy = LabelQueueStrategy.MIXED,
        limit: int = 20,
        exclude_ids: Optional[List[int]] = None,
    ) -> LabelQueueResult:
        """Next frames worth labelling. ``excludeIds``: frames the client
        already holds (queued / skipped / just rated) — never returned, and
        their near-duplicates are not served either."""
        from app.services import label_queue_store as store

        db = get_db_session()
        try:
            result, info, cuts = store.build(db, strategy.value, limit, exclude_ids or ())
            total, today = store.label_counts(db)
        finally:
            db.close()

        items = []
        for it in result.items:
            f, meta = it.frame, info[it.frame.id]
            items.append(LabelQueueItem(
                id=f.id,
                image_url=f"images/{meta.filename}",
                latitude=f.lat,
                longitude=f.lon,
                heading=meta.heading,
                capture_date=format_capture_date(meta.capture_date),
                street_view_url=_street_view_url(f.lat, f.lon, meta.heading,
                                                 meta.pitch, meta.pano_id),
                reason=it.reason,
                area=it.area,
                uncertainty=None if it.uncertainty is None else round(it.uncertainty, 3),
                cell_labels=it.cell_labels,
                boundary=it.boundary,
                model_score=None if f.score is None else round(f.score, 3),
                model_rqi=store.model_rqi(f.score, cuts),
                model_p_bad=None if f.p_bad is None else round(f.p_bad, 3),
            ))
        return LabelQueueResult(
            strategy=strategy,
            items=items,
            stats=LabelQueueStats(total_labelled=total, labelled_today=today,
                                  eligible=result.eligible, scored=result.scored),
        )

    @strawberry.field(permission_classes=[IsAdmin])
    def label_examples(self, per_class: int = 1) -> List[LabelExample]:
        """Rubric thumbnails: clear, already-labelled exemplars per RQI 1-4."""
        from app.services import label_queue_store as store

        db = get_db_session()
        try:
            rows = store.label_examples(db, per_class)
        finally:
            db.close()
        return [LabelExample(rqi=r, id=pid, image_url=f"images/{name}")
                for r, pid, name in rows]


@strawberry.type
class LabelQueueMutation:
    @strawberry.mutation(permission_classes=[IsAdmin])
    def quick_label(self, info: strawberry.Info, input: QuickLabelInput) -> QuickLabelResult:
        """Write manual_rqi (1-4) for one frame into training_data."""
        from app.services import label_queue_store as store

        context = {k: v for k, v in {
            "strategy": input.strategy,
            "reason": input.reason,
            "revealed_model": input.revealed_model,
            "elapsed_ms": input.elapsed_ms,
        }.items() if v is not None}
        db = get_db_session()
        try:
            try:
                name = store.save_quick_label(db, input.point_id, input.rqi,
                                              labeller=_labeller(info), context=context)
            except store.QuickLabelError:
                db.rollback()
                raise
            total, today = store.label_counts(db)
        finally:
            db.close()
        return QuickLabelResult(point_id=input.point_id, image_filename=name,
                                rqi=input.rqi, total_labelled=total, labelled_today=today)

    @strawberry.mutation(permission_classes=[IsAdmin])
    def undo_quick_label(self, point_id: int) -> bool:
        """Revert the quick label of one frame (review-page labels are never touched)."""
        from app.services import label_queue_store as store

        db = get_db_session()
        try:
            return store.undo_quick_label(db, point_id)
        finally:
            db.close()
