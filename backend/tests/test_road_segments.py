"""Segment builder core: frames + lines → rows (pure part, no DB), the build
fingerprint, and the job hooks that must never break a job."""
import datetime as dt
from types import SimpleNamespace

import pytest

from app.services.osm_chains import merge_ways
from app.services.osm_overpass import Way
from app.services.road_segments import (
    Frame,
    bounds_intersect,
    bounds_of,
    build_fingerprint,
    build_rows,
    frames_from_rows,
    linestring_wkt,
    segment_id,
)
from app.services.segment_aggregation import config_from_dict, with_overrides
from app.services.segment_geometry import polyline_length_m
from geo_helpers import FLIPPED_CONFIG, at, make_config

TODAY = dt.date(2026, 11, 26)
DEFAULT_CONFIG = make_config()          # pinned test config (150 m pieces, 4 classes)

# A 300 m east-west street (→ two 150 m pieces) and a 90 m side street.
MAIN = Way(id=100, coords=(at(0, 0), at(300, 0)), name="Main", highway="secondary")
SIDE = Way(id=200, coords=(at(150, 0), at(150, 90)), name="Side", highway="residential")
FAR = Way(id=300, coords=(at(0, 500), at(300, 500)), name="Far", highway="residential")
WAYS = {w.id: w for w in (MAIN, SIDE, FAR)}


def frame(id, east, north, heading, score, **kw):
    lat, lon = at(east, north)
    return Frame(id=id, lat=lat, lon=lon, heading=heading, score=score, **kw)


def main_frames():
    """8 good frames on the first half of MAIN, 4 bad ones on the second."""
    good = [frame(i, 10 + 15 * i, 2, 90, 1.8) for i in range(8)]            # x = 10…115
    bad = [frame(20 + i, 170 + 30 * i, -2, 270, 3.5) for i in range(4)]      # x = 170…260
    return good + bad


def test_frames_are_split_between_pieces_by_linear_reference():
    rows, stats = build_rows(WAYS, main_frames(), DEFAULT_CONFIG, TODAY)
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {"100:0", "100:1"}          # lines without frames are not stored

    first, second = by_id["100:0"], by_id["100:1"]
    assert (first["n_images"], first["rqi"], first["score"]) == (8, 2, 1.8)
    assert (second["n_images"], second["rqi"], second["score"]) == (4, 4, 3.5)
    assert first["p_bad"] is None                     # frames carried no P(bad)
    assert first["length_m"] == pytest.approx(150, abs=0.2)
    assert first["road_name"] == "Main" and first["highway"] == "secondary"
    assert first["osm_way_id"] == 100 and second["piece_index"] == 1
    # Geometry: two contiguous halves of the way.
    assert first["coords"][0] == MAIN.coords[0] and second["coords"][-1] == MAIN.coords[-1]
    assert first["coords"][-1] == second["coords"][0]
    assert polyline_length_m(second["coords"]) == pytest.approx(150, abs=0.2)

    assert (stats.frames_matched, stats.frames_unmatched) == (12, 0)
    assert (stats.lines, stats.lines_with_frames) == (3, 1)
    assert (stats.pieces, stats.segments) == (2, 2)
    assert stats.class_counts == {2: 1, 4: 1}
    assert stats.km == pytest.approx(0.3, abs=0.001)
    assert stats.median_images == 6 and stats.median_length_m == pytest.approx(150, abs=0.2)


def test_unmatched_frames_are_counted_not_forced_onto_a_road():
    frames = main_frames() + [
        frame(90, 50, 40, 90, 2.0),        # 40 m from any road
        frame(91, 60, 3, 0, 2.0),          # on MAIN but heading across it
    ]
    rows, stats = build_rows(WAYS, frames, DEFAULT_CONFIG, TODAY)
    assert stats.frames_matched == 12
    assert stats.frames_unmatched == 2
    assert sum(r["n_images"] for r in rows) == 12


def test_piece_without_frames_is_not_stored():
    rows, stats = build_rows(WAYS, main_frames()[:8], DEFAULT_CONFIG, TODAY)   # only the first half
    assert [r["id"] for r in rows] == ["100:0"]
    assert (stats.pieces, stats.segments) == (2, 1)
    assert all(r["n_images"] > 0 and r["rqi"] is not None for r in rows)


def test_junction_frames_follow_their_heading():
    frames = [
        frame(1, 150, 4, 90, 2.0),         # at the junction, driving east → MAIN
        frame(2, 152, 6, 0, 3.4),          # at the junction, driving north → SIDE
        frame(3, 150, 40, 180, 3.4),
        frame(4, 150, 70, 0, 3.4),
    ]
    rows, _ = build_rows(WAYS, frames, DEFAULT_CONFIG, TODAY)
    by_way = {}
    for r in rows:
        by_way[r["osm_way_id"]] = by_way.get(r["osm_way_id"], 0) + r["n_images"]
    assert by_way == {100: 1, 200: 3}
    side = next(r for r in rows if r["osm_way_id"] == 200)
    assert side["id"] == "200:0" and side["rqi"] == 4
    assert side["coords"] == list(SIDE.coords)        # short way stays one piece


def test_segment_length_from_config_drives_the_split():
    rows, _ = build_rows(WAYS, main_frames(), with_overrides(DEFAULT_CONFIG, segment_length_m=100), TODAY)
    assert [r["id"] for r in rows] == ["100:0", "100:1", "100:2"]
    assert all(r["length_m"] == pytest.approx(100, abs=0.2) for r in rows)
    assert sum(r["n_images"] for r in rows) == 12


def test_capture_dates_and_p_bad_are_carried_through():
    frames = [
        frame(1, 20, 0, 90, 2.0, p_bad=0.2, capture_date=dt.date(2019, 6, 1)),
        frame(2, 40, 0, 90, 2.0, p_bad=0.4, capture_date=dt.date(2024, 9, 1)),
        frame(3, 60, 0, 90, 2.0, p_bad=None, capture_date=None),
    ]
    rows, _ = build_rows(WAYS, frames, DEFAULT_CONFIG, TODAY)
    first = next(r for r in rows if r["id"] == "100:0")
    assert first["p_bad"] == pytest.approx(0.3)
    assert first["capture_date_min"] == dt.date(2019, 6, 1)
    assert first["capture_date_max"] == dt.date(2024, 9, 1)


def test_only_ids_limits_rows_but_not_matching():
    frames = main_frames() + [frame(50, 150, 45, 0, 3.0)]      # one frame on SIDE
    rows, stats = build_rows(WAYS, frames, DEFAULT_CONFIG, TODAY, only_ids={200})
    assert [r["id"] for r in rows] == ["200:0"]
    # The MAIN frames were still matched to MAIN (not dragged onto SIDE).
    assert rows[0]["n_images"] == 1
    assert stats.frames_matched == 13


def test_bbox_rows_equal_the_full_build_rows():
    """A partial rebuild must write exactly what a full rebuild would."""
    frames = main_frames() + [frame(50, 150, 45, 0, 3.0)]
    full, _ = build_rows(WAYS, frames, DEFAULT_CONFIG, TODAY)
    partial, _ = build_rows(WAYS, frames, DEFAULT_CONFIG, TODAY, only_ids={100})
    assert partial == [r for r in full if r["osm_way_id"] == 100]


def test_build_is_deterministic():
    a, _ = build_rows(WAYS, main_frames(), DEFAULT_CONFIG, TODAY)
    b, _ = build_rows(WAYS, list(reversed(main_frames())), DEFAULT_CONFIG, TODAY)
    assert a == b


def test_stitched_road_gives_full_length_pieces_instead_of_fragments():
    """Five 60 m ways of one road: cut per way → five thin fragments; stitched
    first → two 150 m pieces that pool the frames."""
    ways = {
        i: Way(id=i, coords=(at(60 * (i - 1), 0), at(60 * i, 0)), name="Hosszú út", highway="primary")
        for i in range(1, 6)
    }
    frames = [frame(i, 5 + 10 * i, 1, 90, 2.0) for i in range(30)]          # every 10 m

    per_way, _ = build_rows(ways, frames, DEFAULT_CONFIG, TODAY)
    assert len(per_way) == 5 and max(r["n_images"] for r in per_way) == 6

    lines = merge_ways(ways)
    stitched, stats = build_rows(lines, frames, DEFAULT_CONFIG, TODAY)
    assert [r["id"] for r in stitched] == ["1:0", "1:1"]
    assert [r["n_images"] for r in stitched] == [15, 15]
    assert all(r["length_m"] == pytest.approx(150, abs=0.2) for r in stitched)
    assert all(r["road_name"] == "Hosszú út" for r in stitched)
    assert stitched[0]["confidence"] > max(r["confidence"] for r in per_way)
    assert stats.lines == 1


def test_stats_report_is_printable():
    _, stats = build_rows(WAYS, main_frames(), DEFAULT_CONFIG, TODAY)
    text = "\n".join(stats.report())
    assert "matched:" in text and "RQI 4:" in text and "confidence:" in text


def test_stats_list_the_classes_of_the_configured_scale():
    _, stats = build_rows(WAYS, main_frames(), DEFAULT_CONFIG, TODAY)
    assert stats.classes == (1, 2, 3, 4)
    flipped = config_from_dict(FLIPPED_CONFIG)
    mirrored = [Frame(f.id, f.lat, f.lon, f.heading, 6 - f.score) for f in main_frames()]
    rows, stats = build_rows(WAYS, mirrored, flipped, TODAY)
    assert stats.classes == (2, 3, 4, 5)
    assert {r["id"]: r["rqi"] for r in rows} == {"100:0": 4, "100:1": 2}     # 6 − (2, 4)
    assert "RQI 5:" in "\n".join(stats.report())


# ---- which frames the builder may use --------------------------------------

def _row(id, rqi=2.0, dino_score=None, dino_p_bad=None, usable=None, capture=None):
    return SimpleNamespace(
        id=id, latitude=47.5, longitude=19.05, heading=90.0, dino_rqi_score=rqi,
        capture_date=capture, dino_score=dino_score, dino_p_bad=dino_p_bad, usable=usable,
    )


def test_frames_marked_unusable_are_skipped():
    rows = [
        _row(1),                              # no frame_quality key → used
        _row(2, usable="true"),
        _row(3, usable="false"),              # marked unusable → skipped
        _row(4, rqi=None),                    # not analysed yet → skipped
        _row(5, rqi=None, usable="false"),
    ]
    load = frames_from_rows(rows, DEFAULT_CONFIG)
    assert [f.id for f in load.frames] == [1, 2]
    assert (load.unusable, load.unscored) == (2, 1)


def test_frame_filter_is_a_no_op_without_the_quality_key():
    rows = [_row(i) for i in range(1, 6)]
    load = frames_from_rows(rows, DEFAULT_CONFIG)
    assert len(load.frames) == 5 and load.unusable == 0


def test_frames_carry_continuous_score_and_scale_aware_p_bad():
    rows = [
        _row(1, rqi=3.0, dino_score="2.71", dino_p_bad="0.64", capture=dt.date(2024, 3, 1)),
        _row(2, rqi=3.0),                     # ordinal fallback: class 3 is bad
        _row(3, rqi=2.0),
    ]
    load = frames_from_rows(rows, DEFAULT_CONFIG)
    assert [(f.score, f.p_bad) for f in load.frames] == [(2.71, 0.64), (3.0, 1.0), (2.0, 0.0)]
    assert load.frames[0].capture_date == dt.date(2024, 3, 1)
    flipped = frames_from_rows(rows[1:], config_from_dict(FLIPPED_CONFIG))
    assert [f.p_bad for f in flipped.frames] == [1.0, 1.0]     # on "5 = excellent", 3 and 2 are bad


def test_helpers():
    assert segment_id(123456789012, 3) == "123456789012:3"
    assert linestring_wkt([(47.5, 19.05), (47.6, 19.15)]) == (
        "LINESTRING(19.0500000 47.5000000, 19.1500000 47.6000000)"      # lon lat order
    )
    assert bounds_of([(47.5, 19.1), (47.4, 19.3)]) == (47.4, 19.1, 47.5, 19.3)
    assert bounds_of([]) is None
    box = (47.0, 19.0, 48.0, 20.0)
    assert bounds_intersect(box, (47.5, 19.5, 47.6, 19.6))
    assert bounds_intersect(box, (48.0, 20.0, 49.0, 21.0))      # touching counts
    assert not bounds_intersect(box, (48.1, 19.0, 49.0, 20.0))
    assert not bounds_intersect(box, (47.0, 20.1, 48.0, 21.0))


# ---- fingerprint: when is a bbox rebuild allowed? ---------------------------

def test_fingerprint_changes_with_every_input_of_the_stored_rows():
    tiles = {(950, 381): 1000, (949, 381): 2000}
    base = build_fingerprint(tiles, DEFAULT_CONFIG, True)
    assert len(base) == 40
    assert base == build_fingerprint(dict(reversed(list(tiles.items()))), DEFAULT_CONFIG, True)

    assert base != build_fingerprint({**tiles, (951, 381): 5}, DEFAULT_CONFIG, True)      # new tile
    assert base != build_fingerprint({**tiles, (950, 381): 1001}, DEFAULT_CONFIG, True)   # refetched tile
    assert base != build_fingerprint(tiles, DEFAULT_CONFIG, False)                        # stitching off
    assert base != build_fingerprint(tiles, with_overrides(DEFAULT_CONFIG, segment_length_m=100), True)
    assert base != build_fingerprint(tiles, with_overrides(DEFAULT_CONFIG, aggregator="mean_score"), True)
    assert base != build_fingerprint(tiles, with_overrides(DEFAULT_CONFIG, thresholds=(1.5, 2.5, 3.2)), True)
    assert base != build_fingerprint(tiles, config_from_dict(FLIPPED_CONFIG), True)     # scale flipped


# ---- job hooks: must never break the job ------------------------------------

class _FakeDb:
    """Just enough of a Session for the refresh hooks."""

    def __init__(self, n=5, fail=None):
        self.n, self.fail, self.closed = n, fail, False

    def execute(self, *_a, **_kw):
        if self.fail:
            raise self.fail
        row = SimpleNamespace(south=47.5, west=19.05, north=47.52, east=19.08, n=self.n)
        return SimpleNamespace(one=lambda: row)

    def close(self):
        self.closed = True


def _capture_rebuild(monkeypatch):
    from app.services import road_segments

    seen = {}

    def fake_rebuild(db, *, bbox, client, log):
        seen.update(bbox=bbox, retries=client.retries, timeout=client.timeout_s)
        return road_segments.BuildStats(segments=7, lines_with_frames=3)

    monkeypatch.setattr(road_segments, "rebuild_segments", fake_rebuild)
    return seen


def test_route_hook_rebuilds_the_bbox_of_the_new_frames(monkeypatch):
    from app.services import road_segments

    seen = _capture_rebuild(monkeypatch)
    db = _FakeDb()
    stats = road_segments.refresh_segments_since(dt.datetime(2026, 11, 26), log=lambda _m: None, db=db)
    assert stats.segments == 7
    assert seen["bbox"] == (47.5, 19.05, 47.52, 19.08)       # south, west, north, east
    assert seen["retries"] == 0 and seen["timeout"] <= 60     # fail fast inside a job
    assert db.closed


def test_analysis_hook_rebuilds_everything(monkeypatch):
    from app.services import road_segments

    seen = _capture_rebuild(monkeypatch)
    db = _FakeDb()
    assert road_segments.refresh_segments_full(log=lambda _m: None, db=db).segments == 7
    assert seen["bbox"] is None and seen["retries"] == 0
    assert db.closed


def test_hook_skips_when_overpass_is_unreachable(monkeypatch):
    from app.services import road_segments
    from app.services.osm_overpass import OverpassError

    def unreachable(*_a, **_kw):
        raise OverpassError("tile (950, 381): connect timeout")

    monkeypatch.setattr(road_segments, "rebuild_segments", unreachable)
    messages = []
    db = _FakeDb()
    assert road_segments.refresh_segments_since(dt.datetime(2026, 11, 26), log=messages.append, db=db) is None
    assert any("Overpass unavailable" in m for m in messages)
    assert db.closed


def test_hook_survives_any_failure_and_no_new_frames(monkeypatch):
    from app.services import road_segments

    # e.g. the table is missing because the migration has not run yet
    broken = _FakeDb(fail=RuntimeError("relation road_segments does not exist"))
    assert road_segments.refresh_segments_since(dt.datetime(2026, 11, 26), log=lambda _m: None, db=broken) is None
    assert broken.closed

    called = []
    monkeypatch.setattr(road_segments, "rebuild_segments", lambda *a, **k: called.append(1))
    assert road_segments.refresh_segments_since(dt.datetime(2026, 11, 26), log=lambda _m: None, db=_FakeDb(n=0)) is None
    assert called == []                                       # nothing new → no rebuild


def test_job_wrapper_picks_the_right_refresh_and_swallows_errors(monkeypatch):
    from app.services import road_segments, tasks

    monkeypatch.setattr(tasks, "update_job", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(road_segments, "refresh_segments_since", lambda since: calls.append(("since", since)))
    monkeypatch.setattr(road_segments, "refresh_segments_full", lambda: calls.append(("full",)))

    start = dt.datetime(2026, 11, 26, 12, 0)
    tasks.refresh_road_segments("job-1", start)              # route job
    tasks.refresh_road_segments("job-2")                     # analysis job
    assert calls == [("since", start), ("full",)]

    def boom(*_a):
        raise RuntimeError("anything")

    monkeypatch.setattr(road_segments, "refresh_segments_since", boom)
    monkeypatch.setattr(road_segments, "refresh_segments_full", boom)
    tasks.refresh_road_segments("job-3", start)              # must not raise
    tasks.refresh_road_segments("job-4")


# --- unlabelled-area cap ----------------------------------------------------

from app.services.road_segments import LabelIndex, labelled_points_from_rows  # noqa: E402
from app.services.segment_aggregation import unlabelled_cap  # noqa: E402


def test_label_index_radius():
    idx = LabelIndex([at(0, 0)], radius_km=1.0)
    assert idx.any_within(*at(900, 0))
    assert idx.any_within(*at(0, -990))
    assert not idx.any_within(*at(1100, 0))
    assert not idx.any_within(*at(800, 800))       # 1131 m diagonal
    assert not LabelIndex([], 1.0).any_within(*at(0, 0))


def test_labelled_points_from_db_rows_and_legacy_names():
    rows = [("sv_12_ab.jpg", 47.1, 19.2),
            ("00001_47.496700_19.069360_67.jpg", None, None),
            ("sv_99_zz.jpg", None, None)]                # no position anywhere
    assert labelled_points_from_rows(rows) == [(47.1, 19.2), (47.4967, 19.06936)]


def test_build_rows_caps_segments_far_from_any_label():
    # n_ref 1: the 8 agreeing frames of the first piece reach "high"
    cfg = make_config(unlabelled_area={"radius_km": 1, "cap_level": "medium"},
                      confidence={"n_ref": 1, "spread_ref": 0.6, "margin_ref": 0.3,
                                  "high": 0.66, "medium": 0.33})
    frames = main_frames()
    # labels only near the start of MAIN -> both pieces are within 1 km
    rows, stats = build_rows(WAYS, frames, cfg, TODAY, labelled=[at(0, 50)])
    assert not any(r["unlabelled_area"] for r in rows)
    assert stats.capped_segments == 0 and stats.labelled_points == 1
    uncapped = {r["id"]: r["confidence"] for r in rows}

    # labels 5 km away -> pieces above the cap are lowered and flagged
    rows, stats = build_rows(WAYS, frames, cfg, TODAY, labelled=[at(5000, 0)])
    cap = unlabelled_cap(cfg)
    for r in rows:
        if uncapped[r["id"]] > cap:
            assert r["unlabelled_area"] and r["confidence"] == cap
        else:
            assert not r["unlabelled_area"] and r["confidence"] == uncapped[r["id"]]
    assert stats.capped_segments == sum(r["unlabelled_area"] for r in rows)
    assert any(r["unlabelled_area"] for r in rows)
    assert any("unlabelled area:" in line for line in stats.report())


def test_build_rows_without_labels_leaves_the_rule_off():
    cfg = make_config(unlabelled_area={"radius_km": 1, "cap_level": "medium"})
    rows, stats = build_rows(WAYS, main_frames(), cfg, TODAY)
    assert stats.labelled_points is None
    assert not any(r["unlabelled_area"] for r in rows)
