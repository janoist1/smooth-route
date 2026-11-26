"""Segment lookups against a fake session: the box query's parameters, which
segment a frame belongs to, and which frames belong to a segment. No DB."""
import datetime as dt
from types import SimpleNamespace

import pytest

from app.services import road_segments, segment_read
from app.services.segment_read import (
    _ENVELOPE_PAD_DEG,
    fetch_segments_in_boxes,
    fetch_segments_near_path,
    frame_ids_on_segment,
    segment_id_for_point,
)
from geo_helpers import at, make_config

CFG = make_config()
PAD = _ENVELOPE_PAD_DEG


def row(id, x0, x1, north=0.0):
    (lat0, lon0), (lat1, lon1) = at(x0, north), at(x1, north)
    geojson = f'{{"type":"LineString","coordinates":[[{lon0},{lat0}],[{lon1},{lat1}]]}}'
    return SimpleNamespace(
        id=id, geojson=geojson, rqi=2, score=1.8, p_bad=0.1, confidence=0.8, n_images=12,
        length_m=float(abs(x1 - x0)), road_name="Teszt utca", highway="residential",
        capture_date_min=None, capture_date_max=None, updated_at=dt.datetime(2026, 11, 26),
        mid_lat=None, mid_lng=None, mid_heading=None, unlabelled_area=False)


class FakeDb:
    def __init__(self, rows=(), first=None):
        self.rows = list(rows)
        self.first_row = first
        self.calls = []

    def execute(self, clause, params=None):
        self.calls.append((str(clause), params))
        db = self

        class Result:
            def fetchall(self):
                return db.rows

            def first(self):
                return db.first_row

        return Result()


def test_no_boxes_means_no_query():
    db = FakeDb()
    assert fetch_segments_in_boxes(db, []) == []
    assert db.calls == []


def test_box_query_sends_the_boxes_as_four_parallel_arrays():
    from app.services.segment_read import MAX_SEGMENT_CANDIDATES
    db = FakeDb([row("1:0", 0, 200), row("1:1", 200, 400)])
    records = fetch_segments_in_boxes(db, [(19.0, 47.0, 19.1, 47.1), (20.0, 46.0, 20.5, 46.5)], CFG)

    sql, params = db.calls[0]
    assert params == {"west": [19.0, 20.0], "south": [47.0, 46.0],
                      "east": [19.1, 20.5], "north": [47.1, 46.5],
                      "cap": MAX_SEGMENT_CANDIDATES + 1}
    assert "LIMIT :cap" in sql
    assert "s.n_images > 0" not in sql and "DISTINCT ON (s.id)" in sql  # all matching geometry
    assert [r.id for r in records] == ["1:0", "1:1"]
    start, end = records[0].path                                         # (lat, lng) order
    assert start == pytest.approx(at(0, 0)) and end == pytest.approx(at(200, 0))
    assert records[0].rqi == 2 and records[0].n_images == 12


def test_near_path_query_covers_the_whole_path():
    db = FakeDb()
    path = [at(0, 0), at(300, 0)]
    assert fetch_segments_near_path(db, path, CFG) == []
    _, params = db.calls[0]
    assert min(params["west"]) < path[0][1] and max(params["east"]) > path[1][1]
    assert min(params["south"]) < path[0][0] < max(params["north"])


def test_frame_belongs_to_the_segment_it_snaps_to():
    db = FakeDb([row("main", 0, 200), row("parallel", 0, 200, north=40.0)])
    lat, lng = at(100, 2)
    assert segment_id_for_point(db, lat, lng, 90.0) == "main"
    lat, lng = at(100, 38)
    assert segment_id_for_point(db, lat, lng, 90.0) == "parallel"
    _, params = db.calls[0]                             # one small box around the frame
    assert params["west"][0] == pytest.approx(at(100, 2)[1] - PAD)
    assert params["north"][0] == pytest.approx(at(100, 2)[0] + PAD)


def test_frame_far_from_every_segment_or_without_segments_has_no_segment():
    lat, lng = at(100, 2)
    assert segment_id_for_point(FakeDb(), lat, lng, 90.0) is None
    far = FakeDb([row("elsewhere", 5000, 5200)])
    assert segment_id_for_point(far, lat, lng, 90.0) is None


def frame(id, east, north=1.0, heading=90.0):
    lat, lon = at(east, north)
    return SimpleNamespace(id=id, lat=lat, lon=lon, heading=heading)


def test_unknown_segment_has_no_frames(monkeypatch):
    monkeypatch.setattr(segment_read, "load_config", lambda: CFG)
    db = FakeDb(first=None)
    assert frame_ids_on_segment(db, "nope") == []
    assert db.calls[0][1] == {"id": "nope"}


def test_segment_frames_are_loaded_around_its_bbox_and_matched(monkeypatch):
    seen = {}

    def fake_load_frames(db, cfg, bounds=None):
        seen["bounds"] = bounds
        return SimpleNamespace(frames=seen["frames"])

    monkeypatch.setattr(segment_read, "load_config", lambda: CFG)
    monkeypatch.setattr(road_segments, "load_frames", fake_load_frames)
    (south, west), (north, east) = at(0, 0), at(200, 0)
    bbox = SimpleNamespace(west=west, south=south, east=east, north=north)

    seen["frames"] = []
    empty = FakeDb([row("main", 0, 200)], first=bbox)
    assert frame_ids_on_segment(empty, "main") == []
    assert len(empty.calls) == 1                        # no frames → no segment query
    assert seen["bounds"] == pytest.approx((south - PAD, west - PAD, north + PAD, east + PAD))

    # frames on the segment, one on the neighbouring segment, out of order
    seen["frames"] = [frame(3, 150), frame(1, 50), frame(9, 300), frame(2, 100)]
    db = FakeDb([row("main", 0, 200), row("next", 200, 400)], first=bbox)
    assert frame_ids_on_segment(db, "main") == [1, 2, 3]
    _, params = db.calls[1]                             # twice the pad: rival segments too
    assert params["west"] == [pytest.approx(west - 2 * PAD)]
    assert params["north"] == [pytest.approx(north + 2 * PAD)]


def test_path_lookup_keeps_unmeasured_parallel_geometry():
    measured, unmeasured = row("1:0", 0, 200), row("2:0", 0, 200, north=10)
    unmeasured.n_images, unmeasured.rqi, unmeasured.score = 0, None, None
    db = FakeDb([measured, unmeasured])
    records = fetch_segments_near_path(db, [at(0, 10), at(200, 10)], CFG)
    assert {r.id for r in records} == {"1:0", "2:0"}
    assert segment_read.summarize_route([at(0, 10), at(200, 10)], records, CFG).covered_length_m == 0
    assert "s.n_images > 0" not in db.calls[0][0]


@pytest.mark.parametrize("missing", ["images", "score", "class"])
def test_map_query_excludes_unmeasured_rows(missing):
    measured, empty = row("1:0", 0, 200), row("2:0", 0, 200, north=10)
    if missing == "images":
        empty.n_images = 0
    elif missing == "score":
        empty.score = None
    else:
        empty.rqi = None
    db = FakeDb([measured, empty])
    records = segment_read.fetch_segments_in_bbox(db, [19.0, 47.0, 19.1, 47.6], 15, CFG)
    assert [r.id for r in records] == [measured.id]
    sql = db.calls[0][0]
    assert "s.n_images > 0" in sql
    assert "s.score IS NOT NULL" in sql and "s.rqi IS NOT NULL" in sql


def test_segment_frames_query_rejects_unmeasured_target():
    db = FakeDb(first=None)
    assert frame_ids_on_segment(db, "empty:0") == []
    sql = db.calls[0][0]
    assert "n_images > 0" in sql
    assert "score IS NOT NULL" in sql and "rqi IS NOT NULL" in sql
