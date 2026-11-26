"""DbFrameStore and the second-pass target lookup against a fake session:
duplicate checks in memory, one row + one JPEG per new frame, no database."""
import datetime as dt
import re
from types import SimpleNamespace

import pytest

from app.services import frame_store
from app.services.frame_store import DbFrameStore, low_confidence_lines
from app.services.network_collector import NewFrame
from app.services.network_sampling import SamplingConfig
from geo_helpers import at

JPEG = b"\xff\xd8" + b"x" * 64


def stored(id, east, north=0.0, heading=90.0, pano_id=None):
    lat, lon = at(east, north)
    return SimpleNamespace(id=id, latitude=lat, longitude=lon, heading=heading, pano_id=pano_id)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeSession:
    def __init__(self, rows=(), commit_error=None):
        self.rows = list(rows)
        self.commit_error = commit_error
        self.executed = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.next_id = 100

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return FakeResult(self.rows)

    def add(self, row):
        self.added.append(row)

    def flush(self):
        for row in self.added:
            if row.id is None:
                row.id = self.next_id
                self.next_id += 1

    def commit(self):
        if self.commit_error:
            raise self.commit_error
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def new_frame(east, pano_id="new-pano", imagery=None):
    lat, lon = at(east, 0.0)
    return NewFrame(lat=lat, lon=lon, heading=90.0, pitch=-10.0, pano_id=pano_id,
                    capture_date=dt.date(2024, 3, 1), imagery=imagery)


def test_store_loads_stored_frames_and_their_pano_ids(tmp_path):
    db = FakeSession([stored(1, 0, pano_id="a"), stored(2, 500, pano_id=None)])
    store = DbFrameStore(db, tmp_path)
    assert [f.id for f in store.frames] == [1, 2]
    assert store.frames[0].heading == 90.0
    assert store.has_pano("a") and not store.has_pano("b") and not store.has_pano(None)
    assert "street_view_images" in db.executed[0][0]


def test_near_existing_is_a_radius_check_across_grid_cells(tmp_path):
    store = DbFrameStore(FakeSession([stored(1, 0)]), tmp_path)
    for east, north in [(0, 0), (10, 0), (-10, 0), (0, 10), (0, -10), (8, 8)]:
        assert store.near_existing(*at(east, north), 15.0), (east, north)
    assert not store.near_existing(*at(20, 0), 15.0)        # in reach of the grid, too far
    assert not store.near_existing(*at(5000, 0), 15.0)      # nowhere near
    assert not DbFrameStore(FakeSession(), tmp_path).near_existing(*at(0, 0), 15.0)


def test_save_writes_one_row_and_one_jpeg_and_remembers_the_frame(tmp_path):
    db = FakeSession()
    images = tmp_path / "images"                            # created on first save
    store = DbFrameStore(db, images)
    frame = new_frame(250)

    frame_id = store.save(frame, JPEG)

    (row,) = db.added
    assert frame_id == row.id == 100
    assert re.fullmatch(r"images/sv_100_[0-9a-f]{8}\.jpg", row.image_url)
    assert (images / row.image_url.split("/")[1]).read_bytes() == JPEG
    assert (row.latitude, row.longitude) == (frame.lat, frame.lon)
    assert (row.heading, row.pitch, row.pano_id) == (90.0, -10.0, "new-pano")
    assert row.capture_date == dt.date(2024, 3, 1)
    assert row.rqi_score is None and row.analysis_metadata is None      # pending analysis
    assert db.commits == 1 and db.rollbacks == 0
    # the new frame now counts for the duplicate checks of the same run
    assert store.has_pano("new-pano")
    assert store.near_existing(frame.lat, frame.lon, 5.0)
    assert store.frames[-1].id == 100


def test_non_google_frame_keeps_its_licence_and_gets_its_own_prefix(tmp_path):
    db = FakeSession()
    imagery = {"source": "mapillary", "license": "CC BY-SA 4.0", "creator": "someone"}
    DbFrameStore(db, tmp_path).save(new_frame(0, imagery=imagery), JPEG)
    (row,) = db.added
    assert row.image_url.startswith("images/mly_100_")
    assert row.analysis_metadata == {"imagery": imagery}


def test_failed_commit_rolls_back_and_leaves_no_orphan_file(tmp_path):
    db = FakeSession(commit_error=RuntimeError("db down"))
    store = DbFrameStore(db, tmp_path)
    frame = new_frame(0)
    with pytest.raises(RuntimeError, match="db down"):
        store.save(frame, JPEG)
    assert db.rollbacks == 1
    assert list(tmp_path.iterdir()) == []
    assert not store.has_pano("new-pano") and store.frames == []
    assert not store.near_existing(frame.lat, frame.lon, 5.0)


# -------------------------------------------------------- low_confidence_lines

def segment(id, x0, x1, level, reason=None):
    return SimpleNamespace(id=id, path=[at(x0, 0.0), at(x1, 0.0)], rqi=3, score=3.1,
                           confidence_level=level, confidence_reason=reason)


SAMPLING = SamplingConfig(50.0, 30.0, ("low_confidence",))


def test_no_rule_or_no_frames_means_no_second_pass_and_no_query():
    db = FakeSession()
    assert low_confidence_lines(db, (0, 0, 1, 1), [1, 2], SamplingConfig(50, 30, ())) == {}
    assert low_confidence_lines(db, (0, 0, 1, 1), [], SAMPLING) == {}
    assert db.executed == []


def test_low_confidence_lines_reads_segments_in_the_box_and_the_jobs_frames(monkeypatch):
    from app.services import segment_read

    boxes_seen = []
    segments = [segment("sure", 0, 200, "high"), segment("shaky", 200, 400, "low"),
                segment("shaky-elsewhere", 5000, 5200, "low")]

    def fake_fetch(db, boxes):
        boxes_seen.append(boxes)
        return segments

    monkeypatch.setattr(segment_read, "fetch_segments_in_boxes", fake_fetch)
    db = FakeSession([stored(i, east, north=1.0) for i, east in enumerate(range(25, 400, 50))])

    lines = low_confidence_lines(db, (47.0, 19.0, 47.1, 19.2), [0, 1, 2], SAMPLING)

    assert boxes_seen == [[(19.0, 47.0, 19.2, 47.1)]]       # (west, south, east, north)
    assert db.executed[0][1] == {"ids": [0, 1, 2]}
    assert list(lines) == ["shaky"] and lines["shaky"].coords == segments[1].path


def test_reason_rule_selects_segments_by_confidence_reason():
    segments = [segment("few", 0, 200, "medium", reason="few_images"),
                segment("old", 200, 400, "medium", reason="old_images")]
    frames = [SimpleNamespace(lat=lat, lon=lon, heading=90.0)
              for lat, lon in (at(x, 1.0) for x in range(25, 400, 50))]
    targets = frame_store.segments_to_densify(
        segments, frames, SamplingConfig(50, 30, ("few_images",)))
    assert list(targets) == ["few"]
