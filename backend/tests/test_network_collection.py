"""Planning where to take frames, and the collection loop (no network/DB)."""
import datetime as dt
import json
from types import SimpleNamespace

import pytest

from app.services import network_collector as nc
from app.services.network_collector import ResumeLog, process_candidate, run_plan
from app.services.network_sampling import (
    SamplingConfig,
    cell_of,
    covered_offsets,
    district_of,
    group_by_cell,
    is_covered,
    load_sampling,
    order_cells,
    plan_collection,
    sample_line,
    sampling_from_dict,
    take_budget,
    uncovered,
)
from app.services.map_matching import LineIndex
from app.services.segment_geometry import haversine_m
from app.services.sv_client import StreetViewClient, StreetViewError, StreetViewFatal
from app.services.sv_quota import JobBudget, QuotaExceeded, StreetViewQuota
from geo_helpers import FakeLine, at

ROAD = FakeLine(10, [at(0, 0), at(1000, 0)])                 # 1 km, heading east
SIDE = FakeLine(20, [at(500, 0), at(500, 400)])              # heading north
LINES = {ROAD.id: ROAD, SIDE.id: SIDE}


def frame(east, north, heading):
    lat, lon = at(east, north)
    return SimpleNamespace(lat=lat, lon=lon, heading=heading)


# ---- sampling config --------------------------------------------------------

def test_sampling_config_defaults_and_validation():
    assert sampling_from_dict(None) == SamplingConfig(50.0, 30.0, ("low_confidence",))
    cfg = sampling_from_dict({"base_spacing_m": 40, "dense_spacing_m": 20, "densify_if": []})
    assert (cfg.base_spacing_m, cfg.dense_spacing_m, cfg.densify_if) == (40.0, 20.0, ())
    for bad in ({"base_spacing_m": 0}, {"dense_spacing_m": 80}, "50 m"):
        with pytest.raises(ValueError):
            sampling_from_dict(bad)


def test_shipped_config_carries_the_ml_sampling_recipe():
    cfg = load_sampling()
    assert (cfg.base_spacing_m, cfg.dense_spacing_m) == (50.0, 30.0)
    assert cfg.densify_if == ("low_confidence",)


# ---- where along a road -----------------------------------------------------

def test_sample_line_every_50_m_with_road_heading():
    points = sample_line(ROAD, 50)
    assert len(points) == 20
    assert [round(p.offset_m) for p in points[:3]] == [25, 75, 125]
    assert all(p.heading == pytest.approx(90, abs=0.2) for p in points)
    gaps = [haversine_m((a.lat, a.lon), (b.lat, b.lon)) for a, b in zip(points, points[1:])]
    assert all(g == pytest.approx(50, abs=0.2) for g in gaps)
    assert points[0].key == "10:250" and len({p.key for p in points}) == 20


def test_sample_line_spreads_evenly_and_skips_stubs():
    assert len(sample_line(FakeLine(1, [at(0, 0), at(120, 0)]), 50)) == 2      # 60 m apart
    assert len(sample_line(FakeLine(1, [at(0, 0), at(30, 0)]), 50)) == 1
    assert sample_line(FakeLine(1, [at(0, 0), at(20, 0)]), 50) == []           # under half a step
    assert sample_line(FakeLine(1, [at(0, 0)]), 50) == []
    with pytest.raises(ValueError):
        sample_line(ROAD, 0)


def test_heading_follows_a_bend():
    bent = FakeLine(5, [at(0, 0), at(100, 0), at(100, 100)])
    points = sample_line(bent, 50)
    assert [round(p.heading) % 360 for p in points] == [90, 90, 0, 0]


# ---- which stretches are empty ----------------------------------------------

def test_existing_frames_cover_only_their_own_road():
    frames = [frame(100, 2, 90), frame(150, -3, 270), frame(502, 100, 0)]
    covered = covered_offsets(LineIndex(LINES.values()), frames)
    assert [round(o) for o in covered[10]] == [100, 150]
    assert [round(o) for o in covered[20]] == [100]
    # a frame heading north at the junction does not cover the east-west road
    assert is_covered(covered[10], 125, 25) and not is_covered(covered[10], 200, 25)
    assert not is_covered((), 10, 25)

    left = uncovered(sample_line(ROAD, 50), covered, 25)
    assert [round(c.offset_m) for c in left][:3] == [25, 225, 275]             # 75–175 are taken
    assert len(left) == 17


def test_plan_skips_covered_stretches_and_respects_bounds():
    frames = [frame(x, 1, 90) for x in range(0, 500, 10)]                       # first half driven
    plan = plan_collection(LINES, frames, 50)
    planned = [c for _cell, members in plan for c in members]
    on_road = [c for c in planned if c.line_id == 10]
    assert on_road and min(c.offset_m for c in on_road) > 500
    assert len([c for c in planned if c.line_id == 20]) == 8                    # side street untouched

    south, west = at(-10, -10)
    north, east = at(600, 50)
    inside = plan_collection(LINES, [], 50, bounds=(south, west, north, east))
    assert all(south <= c.lat <= north and west <= c.lon <= east
               for _cell, members in inside for c in members)


# ---- in what order ----------------------------------------------------------

def test_cells_are_about_one_kilometre():
    a = cell_of(*at(0, 0))
    assert cell_of(*at(400, 300)) == a or cell_of(*at(400, 300)) != cell_of(*at(1500, 300))
    assert cell_of(*at(2500, 0)) != a and cell_of(*at(0, 2500)) != a
    assert district_of((10, 10)) == district_of((14, 14)) != district_of((15, 10))


def test_order_is_round_robin_across_districts_and_deterministic():
    cells = [(0, 0), (0, 1), (1, 0), (1, 1),        # district (0, 0): four cells
             (0, 5), (1, 6),                         # district (0, 1): two cells
             (7, 7)]                                 # district (1, 1): one cell
    order = order_cells(cells)
    assert sorted(order) == sorted(cells) and order == order_cells(list(reversed(cells)))
    # the first round visits every district once before any district repeats
    assert {district_of(c) for c in order[:3]} == {(0, 0), (0, 1), (1, 1)}
    assert {district_of(c) for c in order[3:5]} == {(0, 0), (0, 1)}
    assert all(district_of(c) == (0, 0) for c in order[5:])
    assert order_cells([]) == []


def test_group_by_cell_keeps_road_order_and_budget_takes_whole_cells():
    long_road = FakeLine(30, [at(0, 0), at(3000, 0)])
    plan = plan_collection({30: long_road}, [], 50)
    assert sum(len(members) for _cell, members in plan) == 60
    for _cell, members in plan:
        offsets = [c.offset_m for c in members]
        assert offsets == sorted(offsets)
    assert group_by_cell([]) == {}
    first = len(plan[0][1])
    assert take_budget(plan, first) == plan[:1]
    assert take_budget(plan, first - 1) == []
    assert take_budget(plan, 10_000) == list(plan)


# ---- the collection loop ----------------------------------------------------

JPEG = b"\xff\xd8" + b"x" * 6000


class FakeStore:
    def __init__(self, panos=(), near=False):
        self.panos = set(panos)
        self.near = near
        self.saved = []

    def has_pano(self, pano_id):
        return pano_id in self.panos

    def near_existing(self, lat, lon, radius_m):
        return self.near

    def save(self, new_frame, jpeg):
        self.saved.append((new_frame, jpeg))
        self.panos.add(new_frame.pano_id)
        return 1000 + len(self.saved)


class FakeGoogle:
    """Answers metadata at the candidate's own position; counts every call."""

    def __init__(self, tmp_path, cap=100, shift_north_m=0.0, no_pano_keys=(), fatal_after=None):
        self.meta_calls = []
        self.image_calls = []
        self.shift = shift_north_m
        self.no_pano = set(no_pano_keys)
        self.fatal_after = fatal_after
        self.quota = StreetViewQuota(tmp_path / "quota.json", monthly_cap=cap,
                                     now=lambda: dt.datetime(2026, 11, 26))

    def metadata(self, lat, lon, *, radius=50, pano_id=None):
        self.meta_calls.append((lat, lon, radius))
        key = f"{lat:.6f},{lon:.6f}"
        if key in self.no_pano:
            return None
        return {"pano_id": f"pano@{key}", "lat": lat + self.shift / 111_195.0, "lng": lon,
                "date": "2024-06"}

    def image(self, *, pano_id, heading, pitch, job=None):
        if self.fatal_after is not None and len(self.image_calls) >= self.fatal_after:
            raise StreetViewFatal("Street View image: HTTP 403 — quota, billing or key problem")
        self.quota.reserve(1, job)                      # the real client books first, too
        self.image_calls.append((pano_id, heading, pitch))
        return JPEG


def one(candidate, google, store, **kw):
    return process_candidate(
        candidate, client=google, store=store, index=LineIndex(LINES.values()), lines=LINES,
        seen_panos=kw.pop("seen", set()), job=kw.pop("job", None), radius_m=25,
    )


def test_point_is_saved_like_a_training_frame(tmp_path):
    google, store = FakeGoogle(tmp_path), FakeStore()
    candidate = sample_line(ROAD, 50)[3]
    status, frame_id, size = one(candidate, google, store)
    assert (status, frame_id, size) == ("saved", 1001, len(JPEG))
    saved, jpeg = store.saved[0]
    assert jpeg == JPEG
    assert saved.pitch == -20.0 and saved.heading == pytest.approx(90, abs=0.2)
    assert saved.capture_date == dt.date(2024, 6, 1)
    assert saved.pano_id.startswith("pano@")
    assert google.meta_calls[0][2] == 25                                  # half the spacing
    assert google.image_calls == [(saved.pano_id, saved.heading, -20.0)]
    assert google.quota.used() == 1


def test_no_image_is_requested_when_metadata_says_skip(tmp_path):
    candidates = sample_line(ROAD, 50)
    key = f"{candidates[0].lat:.6f},{candidates[0].lon:.6f}"

    google = FakeGoogle(tmp_path, no_pano_keys=[key])
    assert one(candidates[0], google, FakeStore())[0] == "no_pano"

    stored = FakeStore(panos=[f"pano@{candidates[1].lat:.6f},{candidates[1].lon:.6f}"])
    assert one(candidates[1], google, stored)[0] == "dup_pano"            # already in the DB

    seen = set()
    assert one(candidates[2], google, FakeStore(), seen=seen)[0] == "saved"
    assert one(candidates[2], google, FakeStore(), seen=seen)[0] == "dup_pano"   # same run

    far = FakeGoogle(tmp_path / "b", shift_north_m=40)                    # pano on another street
    assert one(candidates[3], far, FakeStore())[0] == "off_road"

    assert one(candidates[4], google, FakeStore(near=True))[0] == "near_existing"
    assert len(google.image_calls) == 1 and far.image_calls == []        # only the saved one cost


def test_bad_or_failed_images_are_skipped_not_stored(tmp_path, monkeypatch):
    google, store = FakeGoogle(tmp_path), FakeStore()
    candidates = sample_line(ROAD, 50)
    monkeypatch.setattr(google, "image", lambda **kw: b"tiny")
    assert one(candidates[0], google, store)[0] == "bad_image"

    def boom(**kw):
        raise StreetViewError("Street View image: HTTP 404")

    monkeypatch.setattr(google, "image", boom)
    assert one(candidates[1], google, store)[0] == "image_error"

    def meta_boom(*a, **kw):
        raise StreetViewError("metadata: unreadable answer")

    monkeypatch.setattr(google, "metadata", meta_boom)
    assert one(candidates[2], google, store)[0] == "meta_error"
    assert store.saved == []


def plan_for(lines=None):
    return plan_collection(lines or {10: ROAD}, [], 50)


def test_run_stops_cleanly_at_the_job_cap_and_resumes(tmp_path):
    google, store = FakeGoogle(tmp_path), FakeStore()
    resume = ResumeLog(tmp_path / "job.jsonl")
    job = JobBudget(cap=7)
    result = run_plan(plan_for(), client=google, store=store, lines=LINES, resume=resume, job=job)
    assert result.stop == nc.STOP_BUDGET and "per-job" in result.detail
    assert len(store.saved) == 7 and result.counts["saved"] == 7
    assert google.quota.used() == 7

    # Same command again with a fresh budget: nothing is asked twice.
    asked_before = len(google.meta_calls)
    resume2 = ResumeLog(tmp_path / "job.jsonl")
    assert len(resume2.frame_ids) == 7 and resume2.bytes_saved == 7 * len(JPEG)
    result2 = run_plan(plan_for(), client=google, store=store, lines=LINES, resume=resume2,
                       job=JobBudget(cap=100))
    assert result2.stop == nc.STOP_DONE
    assert len(store.saved) == 20 and result2.counts["saved"] == 13
    # the point that hit the cap had its (free) metadata asked once more — nothing else
    assert len(google.meta_calls) == asked_before + 13
    assert len({f.pano_id for f, _ in store.saved}) == 20


def test_monthly_cap_megabyte_ceiling_and_trouble_all_stop_the_run(tmp_path):
    google = FakeGoogle(tmp_path / "a", cap=3)
    result = run_plan(plan_for(), client=google, store=FakeStore(), lines=LINES,
                      resume=ResumeLog(tmp_path / "a.jsonl"), job=JobBudget(cap=50))
    assert result.stop == nc.STOP_BUDGET and "monthly" in result.detail
    assert google.quota.used() == 3

    google = FakeGoogle(tmp_path / "b")
    resume = ResumeLog(tmp_path / "b.jsonl")
    result = run_plan(plan_for(), client=google, store=FakeStore(), lines=LINES, resume=resume,
                      max_bytes=2 * len(JPEG))
    assert result.stop == nc.STOP_BUDGET and "megabyte" in result.detail
    assert len(resume.frame_ids) == 2

    google = FakeGoogle(tmp_path / "c", fatal_after=4)
    store = FakeStore()
    result = run_plan(plan_for(), client=google, store=store, lines=LINES,
                      resume=ResumeLog(tmp_path / "c.jsonl"))
    assert result.stop == nc.STOP_TROUBLE and "403" in result.detail
    assert len(store.saved) == 4                                          # stopped at once


def test_progress_callback_and_interrupt(tmp_path):
    google, store = FakeGoogle(tmp_path), FakeStore()
    notes = []
    resume = ResumeLog(tmp_path / "job.jsonl")
    run_plan(plan_for(), client=google, store=store, lines=LINES, resume=resume,
             on_progress=lambda result, log: notes.append(len(log.frame_ids)), progress_every=5)
    assert notes == [5, 10, 15, 20]

    class Impatient(FakeStore):
        def save(self, new_frame, jpeg):
            if len(self.saved) == 3:
                raise KeyboardInterrupt
            return super().save(new_frame, jpeg)

    result = run_plan(plan_for(), client=FakeGoogle(tmp_path / "x"), store=Impatient(),
                      lines=LINES, resume=ResumeLog(tmp_path / "x.jsonl"))
    assert result.stop == nc.STOP_INTERRUPT and result.counts["saved"] == 3


def test_resume_log_survives_a_torn_last_line(tmp_path):
    path = tmp_path / "job.jsonl"
    log = ResumeLog(path)
    log.add("10:250", "saved", 5, 45_000)
    log.add("10:750", "no_pano")
    with open(path, "a") as fh:
        fh.write('{"k": "10:1250", "s": "sav')                            # crash mid-write
    again = ResumeLog(path)
    assert "10:250" in again and "10:750" in again and "10:1250" not in again
    assert again.frame_ids == [5] and again.bytes_saved == 45_000
    assert again.counts() == {"saved": 1, "no_pano": 1}
    assert [json.loads(line)["k"] for line in path.read_text().splitlines()[:2]] == ["10:250", "10:750"]


def test_real_client_stops_the_run_on_http_403(tmp_path):
    """End to end through the real client: one 403 on an image ends the job
    and no further request is sent."""
    calls = []

    def http_get(url, params, timeout_s):
        calls.append(url)
        if url.endswith("/metadata"):
            body = {"status": "OK", "pano_id": f"p{len(calls)}",
                    "location": {"lat": float(params["location"].split(",")[0]),
                                 "lng": float(params["location"].split(",")[1])},
                    "date": "2025-03"}
            return 200, "application/json", json.dumps(body).encode()
        return 403, "text/plain", b"quota exceeded"

    client = StreetViewClient(
        "KEY", StreetViewQuota(tmp_path / "q.json", monthly_cap=50,
                               now=lambda: dt.datetime(2026, 11, 26)),
        http_get=http_get, sleep=lambda s: None, rate_per_s=1000, log=lambda m: None)
    result = run_plan(plan_for(), client=client, store=FakeStore(), lines=LINES,
                      resume=ResumeLog(tmp_path / "job.jsonl"), job=JobBudget(cap=10))
    assert result.stop == nc.STOP_TROUBLE
    assert len(calls) == 2                                                 # 1 metadata + 1 image
    with pytest.raises(QuotaExceeded):
        client.quota.reserve(50)
