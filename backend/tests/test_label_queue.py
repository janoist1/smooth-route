"""Label queue: pure selection logic (no DB, no torch) + GraphQL permission wiring."""
import math
from collections import Counter

import pytest

from app.core.auth import Identity
from app.services import label_queue as lq
from app.services.label_queue import Frame, Strategy

USER = Identity(user_id="u1", clerk_id="user_1", email=None, role="user")

# Budapest VII. ker. (inside the "budapest" area) and a point far from all areas.
BP = (47.4981, 19.0713)
FAR = (47.65, 21.60)   # Debrecen direction, > 15 km from every area centroid
CUTS = (1.5, 2.5, 3.2)


def at(base, dx_m=0.0, dy_m=0.0):
    """(lat, lon) dx_m east / dy_m north of base, in the module's projection."""
    lat = base[0] + dy_m / lq.M_PER_DEG
    lon = base[1] + dx_m / (lq.M_PER_DEG * math.cos(math.radians(lq.LAT_REF)))
    return lat, lon


def frame(fid, base=BP, dx=0.0, dy=0.0, score=None, p_bad=None, pano=None):
    lat, lon = at(base, dx, dy)
    return Frame(id=fid, lat=lat, lon=lon, pano_id=pano, score=score, p_bad=p_bad)


def dist_m(a: Frame, b: Frame) -> float:
    ax, ay = lq.to_xy(a.lat, a.lon)
    bx, by = lq.to_xy(b.lat, b.lon)
    return math.hypot(ax - bx, ay - by)


def cell_center(base):
    """Centre of the 1 km grid cell containing base (keeps test streets
    clear of cell edges)."""
    ky, kx = lq.grid_cell(*base)
    lat = (ky + 0.5) * lq.CELL_M / lq.M_PER_DEG
    lon = (kx + 0.5) * lq.CELL_M / (lq.M_PER_DEG * math.cos(math.radians(lq.LAT_REF)))
    return lat, lon


def ids(items):
    return [it.frame.id for it in items]


# --- geometry / scoring -----------------------------------------------------

class TestGeometry:
    def test_grid_cell_matches_spatial_cv_formula(self):
        lat, lon = 47.5012, 19.0456
        ky = math.floor(lat * 111_320.0 / 1000)
        kx = math.floor(lon * 111_320.0 * math.cos(math.radians(47.0)) / 1000)
        assert lq.grid_cell(lat, lon) == (ky, kx)

    def test_area_of(self):
        assert lq.area_of(*BP) == "budapest"
        assert lq.area_of(46.87, 17.39) == "tapolca"
        assert lq.area_of(*FAR) == "other"

    def test_point_index_radius_is_strict(self):
        idx = lq.PointIndex(50)
        idx.add(*BP)
        assert idx.near(*at(BP, 49), 50)
        assert not idx.near(*at(BP, 51), 50)
        assert idx.near(*at(BP, 140), 150)  # radius larger than the bucket


class TestUncertainty:
    def test_on_cut_point_is_one_and_band_edge_is_zero(self):
        assert lq.uncertainty(2.5, None, CUTS) == pytest.approx(1.0)
        assert lq.uncertainty(2.0, None, CUTS) == pytest.approx(0.0)  # 0.5 from 1.5 and 2.5
        assert lq.uncertainty(2.25, None, CUTS) == pytest.approx(0.5)

    def test_p_bad_is_only_a_fallback(self):
        assert lq.uncertainty(None, 0.5, CUTS) == pytest.approx(1.0)
        assert lq.uncertainty(None, 0.9, CUTS) == pytest.approx(0.2)
        # With a score, P(bad) does not override it.
        assert lq.uncertainty(1.0, 0.5, CUTS) == pytest.approx(0.0)
        assert lq.uncertainty(None, None, CUTS) is None

    def test_boundary(self):
        assert lq.boundary(1.45, None, CUTS) == 0
        assert lq.boundary(2.6, None, CUTS) == 1
        assert lq.boundary(3.9, None, CUTS) == 2
        assert lq.boundary(None, 0.3, CUTS) == 1
        assert lq.boundary_label(0) == "1|2"


# --- exclusions -------------------------------------------------------------

class TestEligible:
    def test_frames_near_labelled_are_excluded(self):
        labelled = [BP]
        frames = [frame(1, dx=30), frame(2, dx=49), frame(3, dx=60), frame(4, dx=500)]
        kept = lq.eligible_frames(frames, labelled)
        assert [f.id for f in kept] == [3, 4]

    def test_one_frame_per_panorama_preferring_a_scored_one(self):
        frames = [frame(1, pano="P"), frame(2, pano="P", score=2.0), frame(3, dx=200, pano="Q")]
        kept = lq.eligible_frames(frames, [])
        assert sorted(f.id for f in kept) == [2, 3]

    def test_excluded_ids_are_dropped(self):
        frames = [frame(1), frame(2, dx=500)]
        assert [f.id for f in lq.eligible_frames(frames, [], exclude_ids=[1])] == [2]


# --- uncertain --------------------------------------------------------------

class TestPickUncertain:
    def test_most_uncertain_first_and_unscored_ignored(self):
        frames = [
            frame(1, dx=0, score=2.45),     # 0.05 from 2.5
            frame(2, dx=1000, score=2.30),  # 0.20 from 2.5
            frame(3, dx=2000, score=2.49),  # 0.01 from 2.5
            frame(4, dx=3000),              # no score
        ]
        items = lq.pick_uncertain(frames, 10, CUTS)
        assert ids(items) == [3, 1, 2]
        assert all(it.reason == "uncertain" for it in items)
        assert items[0].boundary == "2|3"

    def test_round_robin_over_boundaries(self):
        frames = [frame(i, dx=i * 500, score=2.5 + 0.001 * i) for i in range(1, 6)]  # all 2|3
        frames += [frame(10, dx=10_000, score=1.4), frame(20, dx=20_000, score=3.3)]
        items = lq.pick_uncertain(frames, 4, CUTS)
        # One per boundary first (1|2, 2|3, 3|4), only then the 2nd 2|3 frame.
        assert [it.boundary for it in items] == ["1|2", "2|3", "3|4", "2|3"]
        got = ids(items)
        assert got[0] == 10 and got[2] == 20 and got[1] in {1, 2, 3, 4, 5}

    def test_no_near_duplicates(self):
        frames = [frame(1, dx=0, score=2.5), frame(2, dx=20, score=2.5),
                  frame(3, dx=80, score=2.5)]
        items = lq.pick_uncertain(frames, 10, CUTS, dup_radius_m=50)
        picked = [it.frame for it in items]
        assert len(picked) == 2
        assert dist_m(picked[0], picked[1]) >= 50

    def test_budapest_breaks_near_ties(self):
        frames = [frame(1, base=FAR, score=2.50), frame(2, base=BP, score=2.47)]
        assert ids(lq.pick_uncertain(frames, 2, CUTS)) == [2, 1]


# --- diverse ----------------------------------------------------------------

def street(fid0, n, base, step_m=10.0, dx0=0.0, dy0=0.0):
    """n frames ~step_m apart along one street (Street View spacing)."""
    return [frame(fid0 + i, base=base, dx=dx0 + i * step_m, dy=dy0) for i in range(n)]


class TestPickDiverse:
    def test_thinned_to_150m(self):
        frames = street(1, 100, BP, step_m=10)  # 1 km of street, one cell row
        items = lq.pick_diverse(frames, [], 50, thin_radius_m=150)
        picked = [it.frame for it in items]
        assert len(picked) >= 3
        for i, a in enumerate(picked):
            for b in picked[i + 1:]:
                assert dist_m(a, b) >= 150

    def test_one_per_cell_per_round(self):
        # Three 1 km cells with a dense street each.
        c = cell_center(BP)
        frames = (street(1, 30, c, dx0=-150) + street(101, 30, c, dx0=2850)
                  + street(201, 30, c, dx0=5850))
        items = lq.pick_diverse(frames, [], 3)
        cells = {lq.grid_cell(it.frame.lat, it.frame.lon) for it in items}
        assert len(cells) == 3

    def test_empty_cells_before_labelled_ones(self):
        c1 = cell_center(BP)
        c2 = cell_center(at(BP, 5000))
        labelled = [at(c1, 0, 300)]  # one label in the first street's cell
        frames = street(1, 20, c1, dx0=-100) + street(101, 20, c2, dx0=-100)
        items = lq.pick_diverse(frames, labelled, 2)
        assert items[0].frame.id >= 101 and items[0].cell_labels == 0
        assert items[1].frame.id < 101 and items[1].cell_labels == 1

    def test_budapest_first_then_areas_with_fewest_labels(self):
        tapolca = (46.8681, 17.3897)
        labelled = [at(tapolca, 5000, 5000)]  # tapolca has a label, "other" none
        frames = (street(1, 5, tapolca) + street(101, 5, FAR) + street(201, 5, BP))
        items = lq.pick_diverse(frames, labelled, 3)
        assert [it.area for it in items] == ["budapest", "other", "tapolca"]

    def test_thinning_also_respects_labelled_frames(self):
        labelled = [BP]
        frames = [frame(1, dx=100), frame(2, dx=400)]
        assert ids(lq.pick_diverse(frames, labelled, 5, thin_radius_m=150)) == [2]


# --- build_queue / mixed ----------------------------------------------------

class TestBuildQueue:
    def scenario(self):
        frames = []
        for c in range(6):  # 6 cells, a street of scored frames in each
            for i in range(30):
                frames.append(frame(c * 100 + i, dx=c * 2000 + i * 10,
                                    score=1.0 + (i % 30) / 10))
        return frames

    def test_mixed_interleaves_diverse_and_uncertain(self):
        res = lq.build_queue(self.scenario(), [], Strategy.MIXED, 8, cut_points=CUTS)
        reasons = [it.reason for it in res.items]
        assert reasons[:4] == ["diverse", "uncertain", "diverse", "uncertain"]
        assert len(set(ids(res.items))) == len(res.items)

    def test_mixed_has_no_near_duplicates_across_halves(self):
        res = lq.build_queue(self.scenario(), [], "mixed", 20, cut_points=CUTS)
        picked = [it.frame for it in res.items]
        for i, a in enumerate(picked):
            for b in picked[i + 1:]:
                assert dist_m(a, b) >= lq.DUP_RADIUS_M

    def test_mixed_falls_back_when_nothing_is_scored(self):
        frames = street(1, 100, BP, step_m=50)
        res = lq.build_queue(frames, [], "mixed", 5)
        assert len(res.items) == 5 and res.scored == 0
        assert {it.reason for it in res.items} == {"diverse"}

    def test_excluded_ids_and_their_neighbours_are_not_served(self):
        frames = [frame(1, score=2.5), frame(2, dx=20, score=2.5),
                  frame(3, dx=500, score=2.5)]
        res = lq.build_queue(frames, [], "uncertain", 10, cut_points=CUTS, exclude_ids=[1])
        assert ids(res.items) == [3]  # 2 is a near-duplicate of the held frame 1

    def test_labelled_neighbourhood_is_excluded_for_every_strategy(self):
        frames = [frame(1, dx=10, score=2.5), frame(2, dx=1000, score=2.5)]
        for strategy in (Strategy.UNCERTAIN, Strategy.DIVERSE, Strategy.MIXED):
            res = lq.build_queue(frames, [BP], strategy, 10, cut_points=CUTS)
            assert 1 not in ids(res.items)
            assert res.eligible == 1

    def test_limit_is_clamped_and_order_is_deterministic(self):
        frames = self.scenario()
        a = lq.build_queue(frames, [], "mixed", 10_000, cut_points=CUTS)
        b = lq.build_queue(list(reversed(frames)), [], "mixed", 10_000, cut_points=CUTS)
        assert len(a.items) <= lq.MAX_LIMIT
        assert ids(a.items) == ids(b.items)
        assert lq.build_queue(frames, [], "mixed", 0).items == []

    def test_unknown_strategy_is_rejected(self):
        with pytest.raises(ValueError):
            lq.build_queue([], [], "random", 5)


# --- store helpers (pure parts) ----------------------------------------------

def test_model_rqi_uses_the_cut_points():
    from app.core.rqi_scale import SCALE
    from app.services.label_queue_store import model_rqi

    # raw model scores are severity (1 = Kiváló); the class comes out canonical
    sv = SCALE.from_severity
    assert model_rqi(None, CUTS) is None
    assert model_rqi(1.49, CUTS) == sv(1)
    assert model_rqi(1.5, CUTS) == sv(2)
    assert model_rqi(3.19, CUTS) == sv(3)
    assert model_rqi(3.9, CUTS) == sv(4)


def test_every_scale_level_can_be_labelled_and_nothing_else():
    from app.core.rqi_scale import SCALE
    from app.services import label_queue_store as store

    assert store.VALID_RQI == tuple(SCALE.values)
    assert SCALE.worst in store.VALID_RQI  # Nagyon rossz: never predicted, still labelable
    for bad in (SCALE.min_value - 1, SCALE.max_value + 1):
        # Validation runs before any DB access (db=None would fail later).
        with pytest.raises(store.QuickLabelError):
            store.save_quick_label(None, 1, bad)


def test_model_outputs_are_converted_to_the_canonical_direction(monkeypatch):
    from app.core.rqi_scale import SCALE
    from app.services import label_queue_store as store

    # Severity in, canonical out (5 = Kiváló since 2026-11-26: 6 - x).
    sv = SCALE.from_severity
    assert store.canonical_boundary("2|3") == f"{int(sv(2))}|{int(sv(3))}"
    assert store.canonical_score(2.4) == pytest.approx(sv(2.4))
    # With the other numbering only the conversion changes, not the queue logic.
    mirrored = SCALE.mirrored()
    monkeypatch.setattr(store, "SCALE", mirrored)
    mv = mirrored.from_severity
    assert store.model_rqi(1.0, CUTS) == mv(1)
    assert store.canonical_boundary("1|2") == f"{int(mv(1))}|{int(mv(2))}"
    assert store.canonical_score(1.0) == pytest.approx(mv(1.0))
    assert store.canonical_boundary(None) is None


# --- GraphQL wiring (guards fire before any resolver touches the DB) --------

@pytest.fixture(scope="module")
def schemas():
    from app.graphql.schema import read_schema, schema

    return schema, read_schema


class TestGraphQLPermissions:
    @pytest.mark.parametrize("query", [
        "{ labelQueue { items { id } } }",
        "{ labelExamples { id } }",
        "mutation { quickLabel(input: {pointId: 1, rqi: 2}) { rqi } }",
        "mutation { undoQuickLabel(pointId: 1) }",
    ])
    def test_admin_only(self, schemas, query):
        schema, _ = schemas
        for identity in (None, USER):
            result = schema.execute_sync(query, context_value={"identity": identity})
            assert result.data is None
            assert "Admin privileges required" in result.errors[0].message

    def test_not_on_the_public_read_schema(self, schemas):
        _, read_schema = schemas
        fields = read_schema.get_type_by_name("Query").fields
        names = {f.python_name for f in fields}
        assert "label_queue" not in names and "label_examples" not in names


# --- re-check strategy ------------------------------------------------------

class TestRecheck:
    def frames(self):
        return [frame(i, dx=i * 10) for i in range(1, 13)]  # dense: no spatial rules apply

    @pytest.mark.parametrize("seed", [0, 17])
    def test_suspicious_first_then_blind_sample_with_unchanged_level_counts(self, seed):
        from app.core.rqi_scale import SCALE

        levels = sorted(SCALE.values, key=SCALE.worst_first_key, reverse=True)
        frames = [frame(i, dx=i * 10) for i in range(1, len(levels) * 3 + 1)]
        level_of = {f.id: levels[(f.id - 1) % len(levels)] for f in frames}
        items = lq.pick_recheck(frames, level_of, [7, 3, 99], 8, levels, seed=seed)
        assert ids(items)[:2] == [7, 3]  # unknown id 99 ignored
        assert [it.reason for it in items[:2]] == ["recheck_suspicious"] * 2
        sample = items[2:]
        assert {it.reason for it in sample} == {"recheck_sample"}
        old_levels = [level_of[it.frame.id] for it in sample]
        round_robin = [*levels, levels[0]]
        assert Counter(old_levels) == Counter(round_robin)
        assert old_levels != round_robin
        assert old_levels != sorted(old_levels)
        assert old_levels != sorted(old_levels, reverse=True)
        repeated = lq.pick_recheck(list(reversed(frames)), level_of, [7, 3, 99], 8,
                                   levels, seed=seed)
        assert ids(items) == ids(repeated)

    def test_excluded_and_limit(self):
        level_of = {i: 1 for i in range(1, 13)}
        items = lq.pick_recheck(self.frames(), level_of, [1, 2], 3, [1, 2, 3], exclude_ids=[1])
        assert ids(items)[0] == 2 and len(items) == 3 and 1 not in ids(items)

    def test_build_queue_refuses_recheck(self):
        with pytest.raises(ValueError):
            lq.build_queue([], [], "recheck", 5)


def test_consistency_stats_original_vs_latest_and_direction_aware():
    from app.core.rqi_scale import SCALE

    d = SCALE.direction
    other = next(x for x in ("lower_is_better", "higher_is_better") if x != d)
    lo, hi = SCALE.best, SCALE.worst
    histories = [
        [{"old": 2, "new": 2, "direction": d}],                       # same
        [{"old": 2, "new": 3, "direction": d}],                       # +1
        [{"old": 2, "new": 4, "direction": d}],                       # far
        [{"old": 1, "new": 3, "direction": d}, {"old": 3, "new": 1, "direction": d}],  # original 1 vs latest 1
        # Written before a direction flip: stored values are mirrored.
        [{"old": lo + hi - 1, "new": lo + hi - 2, "direction": other}],  # canonical 1 -> 2
        [],
    ]
    st = lq.consistency_stats(histories, SCALE)
    assert st["n"] == 5
    assert st["same"] == pytest.approx(2 / 5, abs=1e-3)
    assert st["within_one"] == pytest.approx(4 / 5, abs=1e-3)
    assert st["per_level"][2] == {"n": 3, "same": pytest.approx(1 / 3, abs=1e-3),
                                  "within_one": pytest.approx(2 / 3, abs=1e-3)}
    assert st["per_level"][1]["n"] == 2
    assert lq.consistency_stats([], SCALE)["same"] is None
    mixed = [[{"old": 2, "new": 2, "direction": d, "reason": "recheck_sample"}],
             [{"old": 2, "new": 4, "direction": d, "reason": "recheck_suspicious"}]]
    only_sample = lq.consistency_stats(mixed, SCALE, reason="recheck_sample")
    assert only_sample["n"] == 1 and only_sample["same"] == 1.0


def test_rubric_examples_need_enough_labels_the_model_agrees_with():
    from app.services.label_queue_store import pick_examples

    def c(gap, pid, dx=0.0):
        lat, lon = at(BP, dx)
        return (gap, pid, pid, f"f{pid}.jpg", lat, lon)

    cands = {
        1: [c(0.1, 1), c(0.2, 2, dx=1000), c(0.4, 3, dx=2000), c(1.5, 4)],   # 3 agree
        2: [c(0.1, 10), c(0.2, 11, dx=1000), c(2.0, 12, dx=2000)],           # only 2 agree
        3: [c(None, 20), c(None, 21), c(None, 22)],                          # no model view
        4: [c(0.3, 31), c(0.4, 30, dx=1000), c(0.1, 32, dx=2000)],
    }
    got = pick_examples(cands, per_class=1, min_agreeing=3)
    assert got == [(1, 1, "f1.jpg"), (4, 32, "f32.jpg")]  # smallest current gap first
    assert [r[1] for r in pick_examples(cands, per_class=3, min_agreeing=3) if r[0] == 1] == [1, 2, 3]


@pytest.fixture
def rubric_store(monkeypatch):
    """In-memory query results: no Postgres, image files or model artifact needed."""
    from app.services import label_queue_store as store

    class Result(list):
        def all(self):
            return self

    class Database:
        examples = Result()
        labels = Result()

        def execute(self, statement, *args):
            return self.examples if "JOIN street_view_images" in str(statement) else self.labels

    db, files, cache = Database(), set(), {}
    monkeypatch.setattr(store, "image_files", lambda: files)
    monkeypatch.setattr(store, "load_score_cache", lambda: cache)
    monkeypatch.setattr(store, "cut_points", lambda: CUTS)
    return store, db, files, cache


def rubric_row(pid, level, score, *, quality=None, pano=None, name=None):
    lat, lon = at(BP, dx_m=pid * 1000)
    metadata = {"dino_score": score}
    if quality is not None:
        metadata["frame_quality"] = quality
    return (float(level), pid, name or f"f{pid}.jpg", lat, lon, pano, metadata)


def test_rubric_examples_require_current_label_and_model_level_agreement(rubric_store):
    from app.core.rqi_scale import SCALE

    store, db, files, _ = rubric_store
    level = SCALE.from_severity(2)
    # A stale export error cannot qualify these: the CURRENT label disagrees.
    db.examples.extend(rubric_row(i, level, SCALE.best) for i in range(1, 4))
    # Even a small continuous gap is insufficient across the tuned cut-point.
    db.examples.extend(rubric_row(i, SCALE.from_severity(3), SCALE.from_severity(3.3))
                       for i in range(4, 7))
    db.examples.extend(rubric_row(i, level, SCALE.from_severity(2 + gap))
                       for i, gap in ((10, 0.2), (11, 0.0), (12, 0.1)))
    files.update(row[2] for row in db.examples)
    assert store.label_examples(db, per_class=3) == [
        (level, 11, "f11.jpg"), (level, 12, "f12.jpg"), (level, 10, "f10.jpg"),
    ]


@pytest.mark.parametrize("invalid", [
    "unusable_bool", "unusable_text", "photosphere", "missing_image", "missing_score",
    "nan", "infinite", "fractional_label",
])
def test_rubric_examples_filter_untrustworthy_frames_before_counting(rubric_store, invalid):
    from app.core.rqi_scale import SCALE

    store, db, files, _ = rubric_store
    level = SCALE.from_severity(2)
    kwargs = {}
    score = level
    label = level
    if invalid.startswith("unusable"):
        kwargs["quality"] = {"usable": False if invalid == "unusable_bool" else "false"}
    elif invalid == "photosphere":
        kwargs["pano"] = "CAoSF0NJSE0w-user-photo"
    elif invalid == "missing_score":
        score = None
    elif invalid == "nan":
        score = "nan"
    elif invalid == "infinite":
        score = "inf"
    elif invalid == "fractional_label":
        label += 0.5
    db.examples.extend([rubric_row(1, level, level), rubric_row(2, level, level),
                       rubric_row(3, label, score, **kwargs)])
    files.update(row[2] for row in db.examples if invalid != "missing_image" or row[1] != 3)
    # Two trustworthy frames cannot meet the three-frame minimum.
    assert store.label_examples(db) == []


def test_rubric_examples_convert_cache_severity_and_prefer_stored_canonical_scores(rubric_store):
    from app.core.rqi_scale import SCALE

    store, db, files, cache = rubric_store
    level = SCALE.from_severity(2)
    db.examples.extend(rubric_row(i, level, None) for i in range(1, 4))
    db.examples.append(rubric_row(4, level, SCALE.best))
    files.update(row[2] for row in db.examples)
    cache.update({row[2]: (2.0, None) for row in db.examples})
    assert store.label_examples(db, per_class=6) == [
        (level, i, f"f{i}.jpg") for i in range(1, 4)
    ]


def test_rubric_examples_leave_unpredicted_level_without_thumbnail(rubric_store):
    from app.core.rqi_scale import SCALE

    store, db, files, _ = rubric_store
    # Even a zero gap cannot turn an unsupported model class into a trusted example.
    db.examples.extend(rubric_row(i, SCALE.worst, SCALE.worst) for i in range(1, 4))
    files.update(row[2] for row in db.examples)
    assert store.label_examples(db) == []


def test_rubric_examples_do_not_count_duplicate_images(rubric_store):
    from app.core.rqi_scale import SCALE

    store, db, files, _ = rubric_store
    db.examples.extend(rubric_row(i, SCALE.best, SCALE.best, name="same.jpg")
                       for i in range(1, 4))
    files.add("same.jpg")
    assert store.label_examples(db) == []


def test_recheck_excludes_all_rubric_examples_and_duplicate_image_rows(rubric_store, monkeypatch):
    from app.core.rqi_scale import SCALE

    store, db, files, _ = rubric_store
    db.examples.extend(rubric_row(i, SCALE.best, SCALE.best) for i in range(1, 8))
    db.examples.extend(rubric_row(i, SCALE.worst, SCALE.best) for i in range(8, 11))
    # Another point using the same photo must not leak the known label either.
    db.examples.append(rubric_row(11, SCALE.best, SCALE.best, name="f1.jpg"))
    files.update(row[2] for row in db.examples)
    db.labels.extend((name, level, False) for level, _, name, *_ in db.examples)
    frame_rows = [(pid, f"images/{name}", lat, lon, 0, 0, pano, None,
                   SCALE.to_severity(meta["dino_score"]), None)
                  for _, pid, name, lat, lon, pano, meta in db.examples]
    monkeypatch.setattr(store, "_frame_rows", lambda db: frame_rows)
    monkeypatch.setattr(store, "_audit_order", lambda: ["f1.jpg", "f7.jpg"])
    examples = store.label_examples(db, per_class=store.EXAMPLE_MAX_PER_CLASS)
    assert len(examples) == 6
    result, info, _ = store.build_recheck(db, limit=20, exclude_ids=[8])
    assert set(ids(result.items)) == {7, 9, 10}
    assert not {pid for _, pid, _ in examples} & set(info)
    assert 11 not in info
    assert result.items[0].reason == "recheck_suspicious"


def test_stored_canonical_scores_become_severity_once():
    """Since the 0006 flip analysis_metadata.dino_score is canonical; the queue
    works in the model's severity orientation (regression: they were mixed)."""
    from app.core.rqi_scale import SCALE
    from app.services.label_queue_store import _severity_row

    best = SCALE.best  # canonical value of Kiváló, whatever the direction
    row = _severity_row((1, "images/x.jpg", 47.5, 19.0, 0.0, 0.0, None, None, str(best), "0.1"))
    assert row[8] == pytest.approx(1.0)  # severity 1 = best
    assert _severity_row((1, "u", 0, 0, 0, 0, None, None, None, None))[8] is None
