"""Offline repair tests: original files, fake DB, no Google requests."""
import datetime as dt
from types import SimpleNamespace

from app.core.rqi_scale import SCALE
from scripts import quarantine_sv_placeholders as repair
from test_sv_quota_client import JPEG, image_bytes


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    def query(self, *args):
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self.rows

    def commit(self):
        self.commits += 1


def row(id, **kwargs):
    return SimpleNamespace(id=id, image_url=f"images/sv_{id}_old.jpg",
                           capture_date=dt.date(2022, 6, 1),
                           rqi_score=SCALE.value_of("fair"),
                           dino_rqi_score=SCALE.value_of("fair"), **kwargs)


def test_repair_defaults_to_dry_run_and_apply_is_idempotent(tmp_path):
    image = tmp_path / "placeholder.jpg"
    image.write_bytes(image_bytes(placeholder=True))
    original = {"other": "kept", "frame_quality": {"usable": True, "reasons": ["hood"]}}
    frame = row(1, analysis_metadata=original)
    db = FakeSession([frame])
    counts = repair.run(db, resolve=lambda _: image)
    assert counts == {"placeholders": 1}
    assert db.commits == 0 and frame.analysis_metadata == original
    assert frame.capture_date == dt.date(2022, 6, 1)
    assert frame.rqi_score == frame.dino_rqi_score == SCALE.value_of("fair")

    counts = repair.run(db, apply=True, resolve=lambda _: image)
    assert counts == {"placeholders": 1} and db.commits == 1
    assert frame.capture_date is None and frame.rqi_score is None and frame.dino_rqi_score is None
    assert frame.analysis_metadata == {
        "other": "kept", "frame_quality": {"usable": False, "reasons": ["hood", repair.REASON]}}
    assert original["frame_quality"]["usable"] is True and image.is_file()
    assert repair.run(db, apply=True, resolve=lambda _: image) == {"already_quarantined": 1}


def test_repair_keeps_real_road_images_and_skips_missing_or_unreadable_files(tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(JPEG)
    corrupt = tmp_path / "broken.jpg"
    corrupt.write_bytes(b"broken")
    paths = {"images/sv_1_old.jpg": photo, "images/sv_2_old.jpg": None,
             "images/sv_3_old.jpg": corrupt}
    rows = [row(i, analysis_metadata=None) for i in (1, 2, 3)]
    assert repair.run(FakeSession(rows), apply=True, resolve=paths.get) == {
        "valid_images": 1, "missing_file": 1, "unreadable_image": 1}
    assert all(r.analysis_metadata is None and r.capture_date is not None for r in rows)


def test_repair_leaves_other_imagery_sources_untouched():
    frame = row(1, analysis_metadata={"imagery": {"source": "mapillary"}})
    assert repair.run(FakeSession([frame]), apply=True,
                      resolve=lambda _: (_ for _ in ()).throw(AssertionError("must not read"))) == {}
