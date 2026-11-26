"""The route job's step order and its two-pass sampling (no torch, DB or
Google: the heavy services are replaced by recording fakes)."""
import sys
import types

import pytest

from app.services import tasks
from app.services.sv_client import StreetViewFatal
from app.services.sv_quota import JobBudget


class FakeRoadQuality:
    def __init__(self, added=0, densify_error=None):
        self.calls = []
        self.added = added
        self.densify_error = densify_error
        self.budgets = []

    def collect_points(self, origin, destination, job_id):
        self.calls.append("collect")

    def download_images(self, job_id, budget=None):
        self.calls.append("download")
        self.budgets.append(budget)

    def analyze_points(self, job_id=None, strategy="YOLO"):
        self.calls.append(f"analyze:{strategy}")

    def densify_low_confidence(self, job_id, since, budget=None):
        self.calls.append("densify")
        self.budgets.append(budget)
        if self.densify_error:
            raise self.densify_error
        return self.added


@pytest.fixture
def job(monkeypatch):
    """Run run_route_processing with fakes; returns (service, job updates)."""
    updates = []

    def run(service):
        fake_rq = types.ModuleType("app.services.road_quality")
        fake_rq.road_quality_service = service
        fake_gm = types.ModuleType("app.services.google_maps")
        fake_gm.google_maps_service = object()
        monkeypatch.setitem(sys.modules, "app.services.road_quality", fake_rq)
        monkeypatch.setitem(sys.modules, "app.services.google_maps", fake_gm)
        monkeypatch.setattr(tasks, "update_job", lambda job_id, **kw: updates.append(kw))
        monkeypatch.setattr(tasks, "refresh_road_segments",
                            lambda job_id, since=None: service.calls.append("segments"))
        monkeypatch.setenv("GOOGLE_SV_JOB_CAP", "321")
        tasks.run_route_processing("job-1", "47.5,19.05", "47.6,19.10")
        return service, updates

    return run


def statuses(updates):
    return [u["status"].value for u in updates if "status" in u]


def test_single_pass_when_nothing_is_low_confidence(job):
    service, updates = job(FakeRoadQuality(added=0))
    assert service.calls == [
        "collect", "download", "analyze:YOLO", "analyze:CLASSIFICATION", "segments", "densify",
    ]
    assert statuses(updates)[-1] == "completed"


def test_second_pass_scores_and_rebuilds_again(job):
    service, updates = job(FakeRoadQuality(added=12))
    assert service.calls == [
        "collect", "download", "analyze:YOLO", "analyze:CLASSIFICATION", "segments",
        "densify", "analyze:YOLO", "analyze:CLASSIFICATION", "segments",
    ]
    assert statuses(updates)[-1] == "completed"


def test_both_passes_share_one_job_budget(job):
    service, _updates = job(FakeRoadQuality(added=3))
    first, second = service.budgets
    assert isinstance(first, JobBudget) and first is second      # one allowance per job
    assert first.cap == 321                                       # GOOGLE_SV_JOB_CAP


def test_second_pass_failure_does_not_fail_the_job(job):
    service, updates = job(FakeRoadQuality(densify_error=RuntimeError("segments table missing")))
    assert service.calls[-1] == "densify"
    assert statuses(updates)[-1] == "completed"


def test_quota_or_billing_signal_in_the_second_pass_fails_the_job(job):
    service, updates = job(FakeRoadQuality(
        densify_error=StreetViewFatal("Street View image: HTTP 403 — quota, billing or key problem")))
    assert statuses(updates)[-1] == "failed"
    failure = [u for u in updates if u.get("error")][-1]
    assert "403" in failure["error"]
