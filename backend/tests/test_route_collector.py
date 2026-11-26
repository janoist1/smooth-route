"""Route collection with fakes: no Google, no database, no files.

First pass (``collect_points``): one pending point per sampled route point,
minus the ones that already have a stored neighbour. Second pass
(``densify_low_confidence``): only when the job left low-confidence segments,
and a quota / billing stop is an error, not a silent short run."""
import datetime as dt
from collections import Counter
from types import SimpleNamespace

import pytest

from app.services import frame_store, network_collector, network_sampling, sv_client
from app.services import route_collector as rc
from app.services.network_collector import STOP_BUDGET, STOP_DONE, STOP_TROUBLE, RunResult
from app.services.network_sampling import SamplingConfig
from app.services.sv_client import StreetViewFatal
from geo_helpers import at

SAMPLING = SamplingConfig(50.0, 30.0, ("low_confidence",))


class FakeQuery:
    def __init__(self, session):
        self.session = session

    def filter(self, *criteria):
        return self

    def first(self):
        self.session.lookups += 1
        return self.session.existing.pop(0) if self.session.existing else None


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeSession:
    def __init__(self, existing=(), rows=()):
        self.existing = list(existing)      # answers of the "neighbour within 5 m?" lookups
        self.rows = list(rows)              # answer of the raw SQL query
        self.executed = []
        self.added = []
        self.lookups = 0
        self.commits = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(self)

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return FakeResult(self.rows)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class FakeMaps:
    def __init__(self, route):
        self.route = route
        self.sampled = None

    def get_route(self, origin, destination):
        if isinstance(self.route, Exception):
            raise self.route
        return self.route

    def generate_street_view_metadata(self, points):
        self.sampled = list(points)
        return [{"latitude": lat, "longitude": lon, "heading": 90.0, "pitch": -10.0,
                 "image_url": f"https://example.invalid/sv?n={i}", "pano_id": f"pano{i}",
                 "capture_date": dt.date(2023, 5, 1)}
                for i, (lat, lon) in enumerate(points)]


@pytest.fixture
def updates(monkeypatch):
    seen = []
    monkeypatch.setattr(rc, "update_job", lambda job_id, **kw: seen.append((job_id, kw)))
    monkeypatch.setattr(rc, "load_sampling", lambda: SAMPLING)
    return seen


def route_dicts(length_m):
    return [{"lat": lat, "lng": lon} for lat, lon in (at(0, 0), at(length_m, 0))]


# -------------------------------------------------------------- collect_points

def test_no_route_stores_nothing(monkeypatch, updates):
    opened = []
    monkeypatch.setattr(rc, "google_maps_service", FakeMaps([]))
    monkeypatch.setattr(rc, "SessionLocal", lambda: opened.append(1))
    assert rc.collect_points("A", "B", "job1") is None
    assert opened == []
    assert [kw.get("progress") for _, kw in updates] == [0]
    assert updates[0][1]["current_step"] is rc.JobStep.COLLECTING


def test_first_pass_stores_one_pending_point_per_50_m(monkeypatch, updates):
    maps = FakeMaps(route_dicts(500))
    session = FakeSession()
    monkeypatch.setattr(rc, "google_maps_service", maps)
    monkeypatch.setattr(rc, "SessionLocal", lambda: session)

    rc.collect_points("A", "B", "job1")

    assert len(maps.sampled) == 10                      # 500 m at the 50 m base spacing
    assert session.lookups == 10 and len(session.added) == 10
    first = session.added[0]
    assert (first.latitude, first.longitude) == maps.sampled[0]
    assert (first.heading, first.pitch, first.pano_id) == (90.0, -10.0, "pano0")
    assert first.capture_date == dt.date(2023, 5, 1)
    assert first.image_url.startswith("https://") and first.rqi_score is None   # pending
    assert updates[-1] == ("job1", {"progress": 30, "message": "10 új mérési pont rögzítve."})
    assert all(20 <= kw["progress"] <= 30 for _, kw in updates[3:])
    assert session.commits >= 2 and session.closed


def test_points_with_a_stored_neighbour_are_not_stored_again(monkeypatch, updates):
    maps = FakeMaps(route_dicts(200))
    session = FakeSession(existing=[object(), None, object()])   # 1st and 3rd already known
    monkeypatch.setattr(rc, "google_maps_service", maps)
    monkeypatch.setattr(rc, "SessionLocal", lambda: session)

    rc.collect_points("A", "B", "job1")

    assert len(maps.sampled) == 4
    assert [row.pano_id for row in session.added] == ["pano1", "pano3"]
    assert updates[-1][1]["message"] == "2 új mérési pont rögzítve."


def test_route_lookup_failure_is_raised_to_the_job(monkeypatch, updates):
    monkeypatch.setattr(rc, "google_maps_service", FakeMaps(RuntimeError("directions down")))
    with pytest.raises(RuntimeError, match="directions down"):
        rc.collect_points("A", "B", "job1")


# ------------------------------------------------------ densify_low_confidence

def job_frame(id, east):
    lat, lon = at(east, 0.0)
    return SimpleNamespace(id=id, latitude=lat, longitude=lon)


@pytest.fixture
def second_pass(monkeypatch, updates, tmp_path):
    """Fakes for everything the second pass touches; returns a call record."""
    seen = SimpleNamespace(session=None, bounds=None, frame_ids=None, run=None, plan_args=None,
                           lines={"shaky": SimpleNamespace(id="shaky", coords=[at(0, 0), at(200, 0)])},
                           result=RunResult(stop=STOP_DONE, counts=Counter(saved=3, skipped=1)))

    def start(rows):
        seen.session = FakeSession(rows=rows)
        monkeypatch.setattr(rc, "SessionLocal", lambda: seen.session)
        return seen.session

    def fake_lines(db, bounds, frame_ids, sampling):
        seen.bounds, seen.frame_ids = bounds, list(frame_ids)
        return seen.lines

    def fake_plan(lines, existing, spacing_m):
        seen.plan_args = (lines, existing, spacing_m)
        return "the-plan"

    def fake_run(plan, **kwargs):
        seen.run = (plan, kwargs)
        return seen.result

    store = SimpleNamespace(frames=["stored-frame"])
    monkeypatch.setattr(frame_store, "low_confidence_lines", fake_lines)
    monkeypatch.setattr(frame_store, "DbFrameStore", lambda db, images_dir: store)
    monkeypatch.setattr(network_sampling, "plan_collection", fake_plan)
    monkeypatch.setattr(network_collector, "run_plan", fake_run)
    monkeypatch.setattr(network_collector, "ResumeLog", lambda path: ("resume", path))
    monkeypatch.setattr(sv_client, "default_client", lambda: "the-client")
    monkeypatch.setattr("app.core.paths.data_path", lambda *parts: tmp_path.joinpath(*parts))
    seen.start, seen.store, seen.tmp = start, store, tmp_path
    return seen


def test_job_without_new_frames_has_no_second_pass(second_pass):
    session = second_pass.start([])
    since = dt.datetime(2026, 1, 1)
    assert rc.densify_low_confidence("job1", since) == 0
    assert session.executed[0][1] == {"since": since}
    assert second_pass.bounds is None and second_pass.run is None and session.closed


def test_job_without_low_confidence_segments_has_no_second_pass(second_pass):
    session = second_pass.start([job_frame(1, 0), job_frame(2, 400)])
    second_pass.lines = {}
    assert rc.densify_low_confidence("job1", dt.datetime(2026, 1, 1)) == 0
    assert second_pass.frame_ids == [1, 2]
    assert second_pass.run is None and session.closed


def test_second_pass_runs_the_dense_plan_on_the_low_confidence_segments(second_pass, updates):
    rows = [job_frame(1, 0), job_frame(2, 400)]
    session = second_pass.start(rows)
    budget = object()

    assert rc.densify_low_confidence("job1", dt.datetime(2026, 1, 1), budget) == 3

    south, west, north, east = second_pass.bounds       # the job's frames + ~100 m
    assert south == pytest.approx(rows[0].latitude - 0.001)
    assert north == pytest.approx(rows[0].latitude + 0.001)
    assert west == pytest.approx(rows[0].longitude - 0.001)
    assert east == pytest.approx(rows[1].longitude + 0.001)
    assert second_pass.plan_args == (second_pass.lines, ["stored-frame"], 30.0)
    plan, kwargs = second_pass.run
    assert plan == "the-plan"
    assert kwargs["client"] == "the-client" and kwargs["store"] is second_pass.store
    assert kwargs["lines"] is second_pass.lines and kwargs["job"] is budget
    assert kwargs["radius_m"] == 15.0                   # half the dense spacing
    assert kwargs["resume"] == ("resume", second_pass.tmp / "collect" / "job_job1_dense.jsonl")
    assert updates[-1][1]["message"] == "Sűrítés: 1 bizonytalan szakasz..."
    assert session.closed


def test_second_pass_stopping_at_the_budget_is_not_an_error(second_pass):
    second_pass.start([job_frame(1, 0)])
    second_pass.result = RunResult(stop=STOP_BUDGET, counts=Counter())
    assert rc.densify_low_confidence("job1", dt.datetime(2026, 1, 1)) == 0


def test_quota_or_billing_stop_fails_the_job(second_pass):
    session = second_pass.start([job_frame(1, 0)])
    second_pass.result = RunResult(stop=STOP_TROUBLE, detail="OVER_QUERY_LIMIT",
                                   counts=Counter(saved=1))
    with pytest.raises(StreetViewFatal, match="OVER_QUERY_LIMIT"):
        rc.densify_low_confidence("job1", dt.datetime(2026, 1, 1))
    assert session.closed
