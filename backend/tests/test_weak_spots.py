"""Era 16 targeting: pure fixtures and fake storage, no Postgres/network/model."""
from collections import Counter
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.core.rqi_scale import SCALE
from app.services import label_queue as lq
from app.services import label_queue_store as store
from app.services import weak_spots as weak
from app.services.label_queue import Frame

CUTS = tuple((a + b) / 2 for a, b in zip(
    SCALE.severity_values(SCALE.model_levels), SCALE.severity_values(SCALE.model_levels)[1:]))
BP = lq.AREAS["budapest"]


def frame(fid, lat=47.49, lon=19.06, key="excellent", **kw):
    score = None if key is None else SCALE.to_severity(SCALE.value_of(key))
    return Frame(fid, lat, lon, score=score, **kw)


@pytest.fixture
def config():
    return weak.load_config()


@pytest.fixture
def pools():
    """Disjoint, well-spaced pools: highways outside Budapest, city, outer Budapest."""
    return {
        "motorway_top": [frame(i + 1, 47.0 + i * .003, 18.0, highway="motorway")
                         for i in range(50)],
        "inner_city_fair": [frame(i + 101, 47.477 + (i // 10) * .004,
                                  19.047 + (i % 10) * .004, key="fair") for i in range(50)],
        "new_budapest_cells": [frame(i + 201, 47.54 + (i // 10) * .004,
                                      19.047 + (i % 10) * .004, key=None) for i in range(50)],
    }


def test_rule_selection_uses_tuned_levels_and_existing_inner_bbox(config):
    south, west, north, east = next(r.bbox for r in config.rules if r.key == "inner_city_fair")
    # This is the coverage report's existing approximate inner (V-IX) sector.
    assert (south, west, north, east) == (47.475, 19.045, 47.515, 19.095)
    highways = ("motorway", "trunk", "motorway_link", "trunk_link")
    frames = [frame(i + 1, 47.0, 18.0 + i * .01, highway=h) for i, h in enumerate(highways)]
    frames += [frame(10, highway="residential"), frame(11, key="good", highway="motorway"),
               frame(12, key=None, highway="motorway"), frame(13, key="fair"),
               frame(14, lat=north, key="fair"), frame(15, lon=east, key="fair"),
               frame(16, lat=south, lon=west, key="fair"), frame(17, key="good")]
    got = weak.rule_pools(frames, [], CUTS, config)
    assert {f.id for f in got["motorway_top"]} == {1, 2, 3, 4}
    assert {f.id for f in got["inner_city_fair"]} == {13, 16}
    # Classification must use the live tuned cut-point, rather than rounding.
    score = CUTS[0] + .1
    candidate = replace(frames[0], score=score)
    assert weak.predicted_rqi(score, CUTS) == SCALE.value_of("good")
    tuned = (CUTS[0] + .2, *CUTS[1:])
    assert candidate in weak.rule_pools([candidate], [], tuned, config)["motorway_top"]


def test_new_cells_are_budapest_only_and_have_no_label_in_same_grid_cell(config):
    ky, kx = lq.grid_cell(*BP)
    lat = (ky + .1) * lq.CELL_M / lq.M_PER_DEG
    lon = (kx + .1) * lq.CELL_M / (lq.M_PER_DEG * lq._COS_REF)
    labelled = [(lat, lon)]
    frames = [frame(1, lat + 500 / lq.M_PER_DEG, lon, key=None),
              frame(2, lat + 2000 / lq.M_PER_DEG, lon, key=None),
              frame(3, 47.0, 18.0, key=None)]
    assert [f.id for f in weak.rule_pools(frames, labelled, CUTS, config)["new_budapest_cells"]] == [2]


def test_configured_shares_and_fallback_when_a_rule_runs_dry(config, pools):
    frames = sum(pools.values(), [])
    items = weak.pick(frames, [], 20, CUTS, config)
    kind = {f.id: name for name, fs in pools.items() for f in fs}
    assert Counter(kind[it.frame.id] for it in items) == {
        "motorway_top": 9, "inner_city_fair": 9, "new_budapest_cells": 2,
    }
    # The fallback fills the whole batch even with no targeted prediction left.
    assert len(weak.pick(pools["new_budapest_cells"], [], 20, CUTS, config)) == 20
    # Shares are weights; zero disables a rule, including during backfill.
    only_city = replace(config, rules=tuple(replace(r, share=1 if r.key == "inner_city_fair" else 0)
                                            for r in config.rules))
    assert {kind[it.frame.id] for it in weak.pick(frames, [], 20, CUTS, only_city)} == {"inner_city_fair"}
    dry = weak.pick(pools["motorway_top"][:2] + pools["inner_city_fair"], [], 20, CUTS, config)
    assert len(dry) == 20
    assert Counter(kind[it.frame.id] for it in dry) == {"motorway_top": 2, "inner_city_fair": 18}


def test_shared_exclusions_thinning_overlap_and_held_neighbours(config, monkeypatch):
    monkeypatch.setattr(weak, "load_config", lambda: config)
    base = frame(1, key="fair", pano_id="same")
    frames = [base, replace(base, id=2),  # same panorama
              frame(3, lat=base.lat + 20 / lq.M_PER_DEG, key="excellent", highway="trunk"),
              frame(4, lat=base.lat + 300 / lq.M_PER_DEG, key="fair"),
              frame(5, lat=base.lat + 320 / lq.M_PER_DEG, key="fair"),
              frame(6, lat=base.lat + 650 / lq.M_PER_DEG, key="fair"),
              frame(7, lat=base.lat + 750 / lq.M_PER_DEG, key="fair")]
    result = lq.build_queue(frames, [(frames[3].lat, frames[3].lon)], "weak_spots", 20,
                            cut_points=CUTS, exclude_ids=[6])
    ids = {it.frame.id for it in result.items}
    assert len(ids) == 1 and ids <= {1, 3}
    assert not ids & {2, 4, 5, 6, 7}
    # Inner-city frames also match the new-cell fallback: still served only once.
    items = weak.pick(frames, [], 20, CUTS, config)
    assert len({it.frame.id for it in items}) == len(items)
    for i, a in enumerate(items):
        ax, ay = lq.to_xy(a.frame.lat, a.frame.lon)
        for b in items[i + 1:]:
            bx, by = lq.to_xy(b.frame.lat, b.frame.lon)
            assert (ax - bx) ** 2 + (ay - by) ** 2 >= config.thin_radius_m ** 2


@pytest.mark.parametrize("seed", [0, 17])
def test_blind_hash_order_is_deterministic_independent_of_rule_position(config, pools, seed):
    frames = sum(pools.values(), [])
    a = weak.pick(frames, [], 40, CUTS, config, seed=seed)
    b = weak.pick(list(reversed(frames)), [], 40, CUTS,
                  replace(config, rules=tuple(reversed(config.rules))), seed=seed)
    ids = [it.frame.id for it in a]
    assert ids == [it.frame.id for it in b]
    assert ids == sorted(ids, key=lambda fid: (lq.stable_rank(("weak_spots_order", fid), seed), fid))
    assert {it.reason for it in a} == {"weak_spots"}
    assert all(it.boundary is None and it.uncertainty is None for it in a)
    # Neither sorted classes nor a repeated class schedule survives the shuffle.
    levels = [weak.predicted_rqi(it.frame.score, CUTS) for it in a]
    assert levels != sorted(levels, key=lambda v: -1 if v is None else v)
    assert levels[:10] != levels[10:20]


def test_prediction_is_scale_direction_aware_and_missing_scores_are_not_top(monkeypatch):
    for scale in (SCALE, SCALE.mirrored()):
        monkeypatch.setattr(weak, "SCALE", scale)
        for key in ("excellent", "good", "fair", "poor"):
            assert weak.predicted_rqi(SCALE.to_severity(SCALE.value_of(key)), CUTS) == scale.value_of(key)
        for invalid in (None, float("nan"), float("inf")):
            assert weak.predicted_rqi(invalid, CUTS) is None


@pytest.mark.parametrize("change", [
    {"thin_radius_m": 1}, {"thin_radius_m": float("nan")},
    {"rules": []}, {"rules": [{"key": "x", "share": -1}]},
    {"rules": [{"key": "x", "share": 0}]},
    {"rules": [{"key": "x", "share": 1, "bbox": [48, 19, 47, 20]}]},
])
def test_config_rejects_invalid_thinning_shares_and_bbox(change):
    with pytest.raises(ValueError):
        weak.config_from_dict({"thin_radius_m": 150, "rules": [{"key": "x", "share": 1}], **change})


def test_loader_excludes_labelled_missing_and_unusable_then_build_wires_rules(monkeypatch):
    class DB:
        def execute(self, statement):
            if "training_data" in str(statement):
                return [("labelled.jpg",)]
            assert "frame_quality" in str(statement)
            return [(3,)]

    def row(fid, name, lat):
        return (fid, f"images/{name}", lat, 18.0, 90, 0, None, None,
                SCALE.to_severity(SCALE.best), None)

    rows = [row(1, "labelled.jpg", 47.0), row(2, "missing.jpg", 47.01),
            row(3, "unusable.jpg", 47.02), row(4, "valid.jpg", 47.03)]
    monkeypatch.setattr(store, "_frame_rows", lambda db: rows)
    monkeypatch.setattr(store, "image_files", lambda: {"labelled.jpg", "unusable.jpg", "valid.jpg"})
    monkeypatch.setattr(store, "load_score_cache", lambda: {})
    monkeypatch.setattr(store, "cut_points", lambda: CUTS)
    from app.services import segment_read
    seen = []

    def highways(db, frames):
        seen.extend(f.id for f in frames)
        return {4: "motorway_link"}

    monkeypatch.setattr(segment_read, "highways_for_frames", highways)
    result, info, cuts = store.build(DB(), "weak_spots", 20)
    assert [it.frame.id for it in result.items] == [4]
    assert result.eligible == 1 and result.scored == 1
    assert set(info) == {4} and cuts == CUTS and seen == [4]
    assert store.build(DB(), "weak_spots", 20, [4])[0].items == []


def test_frame_highway_uses_heading_measured_status_and_rival_roads(monkeypatch):
    from app.services import segment_read as read
    from test_segment_read import record
    from geo_helpers import at

    motorway = replace(record("1:0", 0, 200, SCALE.best, SCALE.best), highway="motorway")
    rival = replace(record("2:0", 0, 200, SCALE.best, SCALE.best, north=10), highway="residential")
    unmeasured = replace(record("3:0", 0, 200, None, None, north=30, n=0), highway="trunk")
    # A north/south trunk crossing the motorway must respect the frame heading.
    crossing = replace(motorway, id="4:0", path=[at(100, -100), at(100, 100)], highway="trunk_link")
    monkeypatch.setattr(read, "fetch_segments_in_boxes", lambda db, boxes: [motorway, rival, unmeasured, crossing])
    frames = [SimpleNamespace(id=i, lat=at(x, y)[0], lon=at(x, y)[1], heading=heading)
              for i, x, y, heading in [(1, 50, 0, 90), (2, 50, 10, 90),
                                        (3, 50, 30, 90), (4, 100, 0, 0), (5, 500, 0, 90)]]
    assert read.highways_for_frames(None, frames) == {1: "motorway", 2: "residential", 4: "trunk_link"}


def test_sprint_count_includes_both_targeted_label_modes():
    class DB:
        def execute(self, statement):
            query = str(statement)
            assert "IN ('sprint', 'weak_spots')" in query
            assert "created_row" in query and "manual_rqi IS NOT NULL" in query
            return SimpleNamespace(scalar=lambda: 12)

    assert store.sprint_count(DB()) == 12


def test_read_only_report_counts_the_same_rule_matches_and_thinned_capacity(config):
    from scripts.weak_spots_report import rule_counts

    frames = [frame(1, 47.0, 18.0, highway="motorway"),
              frame(2, 47.0 + 100 / lq.M_PER_DEG, 18.0, highway="motorway"),
              frame(3, 47.0 + 1000 / lq.M_PER_DEG, 18.0, highway="trunk"),
              frame(4, key="fair")]
    assert rule_counts(frames, [], CUTS, config) == [
        ("motorway_top", .45, 3, 2),
        ("inner_city_fair", .45, 1, 1),
        ("new_budapest_cells", .1, 1, 1),
    ]


def test_graphql_accepts_weak_spots_and_keeps_it_admin_only(monkeypatch):
    from app.core.auth import Identity
    from app.graphql import label_queue as gql_queue
    from app.graphql.schema import schema

    db = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(gql_queue, "get_db_session", lambda: db)

    def build(db, strategy, limit, excluded):
        assert strategy == "weak_spots" and limit == 20 and excluded == [42]
        return lq.QueueResult([], 0, 0), {}, CUTS

    monkeypatch.setattr(store, "build", build)
    monkeypatch.setattr(store, "label_counts", lambda db: (0, 0))
    monkeypatch.setattr(store, "sprint_count", lambda db: 0)
    monkeypatch.setattr(store, "recheck_consistency", lambda db: {"n": 0, "same": None, "within_one": None})
    query = "{ labelQueue(strategy: WEAK_SPOTS, excludeIds: [42]) { strategy items { id } } }"
    admin = Identity(user_id="admin", clerk_id="admin", email=None, role="admin")
    result = schema.execute_sync(query, context_value={"identity": admin})
    assert result.errors is None
    assert result.data == {"labelQueue": {"strategy": "WEAK_SPOTS", "items": []}}
    denied = schema.execute_sync(query, context_value={"identity": None})
    assert "Admin privileges required" in denied.errors[0].message
