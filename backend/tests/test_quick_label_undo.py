"""Quick-label undo and the one-off scale repair, without a DB."""
from copy import deepcopy

import pytest

from app.core.rqi_scale import SCALE, SEVERITY
from app.models.models import TrainingData
from app.services import label_queue_store as store
from scripts import repair_quick_label_scale as repair


@pytest.fixture
def label_db(monkeypatch):
    class Database:
        row = None

        def query(self, _model):
            return self

        def filter(self, _expression):
            return self

        def first(self):
            return self.row

        def add(self, row):
            self.row = row

        def delete(self, row):
            assert row is self.row
            self.row = None

        def commit(self):
            pass

    monkeypatch.setattr(store, "_point_filename", lambda _db, _point_id: "frame.jpg")
    return Database()


@pytest.mark.parametrize("scale", [SCALE, SCALE.mirrored()], ids=["canonical", "mirrored"])
@pytest.mark.parametrize("source", ["legacy", "history", "tagged", "post-flip-history"])
def test_quick_label_undo_converts_legacy_backup_and_repair_is_idempotent(label_db, monkeypatch,
                                                                       scale, source):
    monkeypatch.setattr(store, "SCALE", scale)
    monkeypatch.setattr(repair, "SCALE", scale)
    expected = (scale.value_of("poor") + scale.value_of("fair")) / 2
    direction = SEVERITY if source == "legacy" else scale.mirrored().direction
    if source == "post-flip-history":
        direction = scale.direction
    ql = {"timestamp": "2026-11-25T10:00:00Z",
          "previous_rqi": scale.to_direction(expected, direction), "history_added": True}
    if source == "tagged":
        ql.update(previous_rqi_direction=direction, previous_rqi_scale_version=scale.version)
    history = [{"timestamp": ql["timestamp"], "direction": direction}]
    metadata = {"quick_label": ql, "agent": "kept"}
    if source in ("history", "post-flip-history"):
        metadata["relabel_history"] = history
    original = deepcopy(metadata)
    fixed = repair.repair_metadata(metadata)
    assert metadata == original  # dry-run must not mutate the source
    assert fixed["quick_label"]["previous_rqi"] == expected
    assert fixed["quick_label"]["previous_rqi_direction"] == scale.direction
    assert fixed["quick_label"]["previous_rqi_scale_version"] == scale.version
    assert repair.repair_metadata(fixed) == fixed
    # Either path (runtime undo or repaired DB) restores the same human label.
    for meta in (original, fixed):
        label_db.row = TrainingData(image_filename="frame.jpg", manual_rqi=scale.best,
                                    annotations=[], tags=[], comment="", meta_data=deepcopy(meta))
        assert store.undo_quick_label(label_db, 1)
        assert label_db.row.manual_rqi == expected
        assert label_db.row.meta_data == {"agent": "kept"}


@pytest.mark.parametrize("created_row", [True, False])
def test_quick_label_undo_restores_previous_metadata_across_repeated_cycles(label_db, created_row):
    if not created_row:
        label_db.row = TrainingData(image_filename="frame.jpg", manual_rqi=SCALE.worst,
                                    annotations=[{"kept": True}], tags=["kept"], comment="kept",
                                    meta_data={"agent": "review"})
    store.save_quick_label(label_db, 1, SCALE.best, context={"strategy": "original"})
    original = deepcopy(label_db.row.meta_data)
    first_ql = original["quick_label"]
    assert first_ql["previous_rqi_direction"] == SCALE.direction
    assert first_ql["previous_rqi_scale_version"] == SCALE.version
    for _ in range(2):
        store.save_quick_label(label_db, 1, SCALE.worst, context={"strategy": "recheck"})
        assert label_db.row.meta_data["quick_label"]["previous_quick_label"] == first_ql
        # Exercise repair of nested backups, as well as the current backup.
        fixed = repair.repair_metadata(label_db.row.meta_data)
        assert repair.repair_metadata(fixed) == fixed
        assert store.undo_quick_label(label_db, 1)
        assert label_db.row.manual_rqi == SCALE.best
        assert label_db.row.meta_data == original
    assert store.undo_quick_label(label_db, 1)
    if created_row:
        assert label_db.row is None
    else:
        assert label_db.row.manual_rqi == SCALE.worst
        assert label_db.row.meta_data == {"agent": "review"}
        assert label_db.row.annotations == [{"kept": True}]
    assert not store.undo_quick_label(label_db, 1)
