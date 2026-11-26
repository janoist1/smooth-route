"""Background job wrappers: how each job ends (completed / cancelled /
failed), address geocoding before a route job, and the best-effort segment
refresh. The heavy services are recording fakes: no torch, DB or Google."""
import sys
import types

import pytest

from app.services import road_segments, tasks
from app.services.job_service import JobStatus


@pytest.fixture
def updates(monkeypatch):
    seen = []
    monkeypatch.setattr(tasks, "update_job", lambda job_id, **kw: seen.append(kw))
    return seen


def install(monkeypatch, module_name, **attributes):
    module = types.ModuleType(module_name)
    for name, value in attributes.items():
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, module_name, module)


def statuses(updates):
    return [kw["status"] for kw in updates if "status" in kw]


# -------------------------------------------------------- refresh_road_segments

@pytest.fixture
def refreshes(monkeypatch):
    calls = []
    monkeypatch.setattr(road_segments, "refresh_segments_full", lambda: calls.append("full"))
    monkeypatch.setattr(road_segments, "refresh_segments_since",
                        lambda since: calls.append(("since", since)))
    return calls


def test_analysis_refresh_is_a_full_rebuild(updates, refreshes):
    tasks.refresh_road_segments("job1")
    assert refreshes == ["full"]
    assert updates == [{"message": "Útszakaszok frissítése..."}]


def test_route_refresh_is_limited_to_the_jobs_frames(updates, refreshes):
    tasks.refresh_road_segments("job1", "t0")
    assert refreshes == [("since", "t0")]


def test_failed_refresh_never_fails_the_job(updates, monkeypatch):
    def unreachable():
        raise RuntimeError("Overpass unreachable")

    monkeypatch.setattr(road_segments, "refresh_segments_full", unreachable)
    tasks.refresh_road_segments("job1")                 # logged and skipped


# ------------------------------------------------- route job: address geocoding

class RouteService:
    def __init__(self, collect_error=None):
        self.collected = None
        self.collect_error = collect_error

    def collect_points(self, origin, destination, job_id):
        self.collected = (origin, destination)
        if self.collect_error:
            raise self.collect_error

    def download_images(self, job_id, budget=None):
        pass

    def analyze_points(self, job_id=None, strategy="YOLO"):
        pass

    def densify_low_confidence(self, job_id, since, budget=None):
        return 0


class Geocoder:
    def __init__(self, known):
        self.known = known
        self.asked = []

    def geocode(self, address):
        self.asked.append(address)
        return self.known.get(address)


def run_route(monkeypatch, origin, destination, known=None, service=None):
    service = service or RouteService()
    geocoder = Geocoder(known or {})
    install(monkeypatch, "app.services.road_quality", road_quality_service=service)
    install(monkeypatch, "app.services.google_maps", google_maps_service=geocoder)
    monkeypatch.setattr(tasks, "refresh_road_segments", lambda job_id, since=None: None)
    tasks.run_route_processing("job1", origin, destination)
    return service, geocoder


def test_coordinates_are_used_as_they_are(monkeypatch, updates):
    service, geocoder = run_route(monkeypatch, "47.5,19.05", " -33.9,151.2 ")
    assert geocoder.asked == []
    assert service.collected == ("47.5,19.05", " -33.9,151.2 ")
    assert statuses(updates) == [JobStatus.RUNNING, JobStatus.COMPLETED]


def test_addresses_are_geocoded_before_collection(monkeypatch, updates):
    service, geocoder = run_route(
        monkeypatch, "Budapest, Fő utca 1", "Szeged",
        known={"Budapest, Fő utca 1": "47.5,19.04", "Szeged": "46.25,20.15"})
    assert geocoder.asked == ["Budapest, Fő utca 1", "Szeged"]
    assert service.collected == ("47.5,19.04", "46.25,20.15")
    messages = [kw.get("message") for kw in updates]
    assert "Cím feloldása: Budapest, Fő utca 1..." in messages
    assert "Cím feloldása: Szeged..." in messages


def test_unresolved_address_is_passed_on_unchanged(monkeypatch, updates):
    service, geocoder = run_route(monkeypatch, "Nowhere Lane", "47.6,19.1")
    assert geocoder.asked == ["Nowhere Lane"]
    assert service.collected == ("Nowhere Lane", "47.6,19.1")


def test_failed_route_job_records_the_error(monkeypatch, updates):
    run_route(monkeypatch, "47.5,19.05", "47.6,19.1",
              service=RouteService(collect_error=RuntimeError("no route")))
    last = updates[-1]
    assert last["status"] is JobStatus.FAILED and last["error"] == "no route"
    assert last["message"] == "Hiba történt: no route" and last["completed_at"] is not None


def test_failing_to_record_the_failure_does_not_raise(monkeypatch):
    def broken_update(job_id, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(tasks, "update_job", broken_update)
    install(monkeypatch, "app.services.road_quality", road_quality_service=RouteService())
    install(monkeypatch, "app.services.google_maps", google_maps_service=Geocoder({}))
    tasks.run_route_processing("job1", "47.5,19.05", "47.6,19.1")


# ----------------------------------------------------------------- analysis job

class AnalysisService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.kwargs = None

    def analyze_points(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


def run_analysis(monkeypatch, service, **kwargs):
    refreshed = []
    install(monkeypatch, "app.services.road_quality", road_quality_service=service)
    monkeypatch.setattr(tasks, "refresh_road_segments",
                        lambda job_id, since=None: refreshed.append((job_id, since)))
    tasks.run_analysis_job("job1", **kwargs)
    return refreshed


def test_analysis_job_completes_and_refreshes_all_segments(monkeypatch, updates):
    result = {"status": "success", "analyzed": 12, "strategy_used": "CLASSIFICATION"}
    service = AnalysisService(result)
    refreshed = run_analysis(monkeypatch, service, strategy="CLASSIFICATION", limit=50,
                             reanalyze=True)
    assert service.kwargs == {"strategy": "CLASSIFICATION", "limit": 50, "reanalyze": True,
                              "job_id": "job1"}
    assert refreshed == [("job1", None)]                # scores may have changed anywhere
    assert statuses(updates) == [JobStatus.RUNNING, JobStatus.COMPLETED]
    done = updates[-1]
    assert done["message"] == "Elemzés sikeresen befejezve (CLASSIFICATION)"
    assert done["result"] == {"status": "success", "counts": result}
    assert done["completed_at"] is not None


def test_cancelled_analysis_job_is_not_marked_completed(monkeypatch, updates):
    refreshed = run_analysis(monkeypatch, AnalysisService({"status": "cancelled"}),
                             strategy="YOLO")
    assert refreshed == [] and statuses(updates) == [JobStatus.RUNNING]


def test_failed_analysis_job_records_the_error(monkeypatch, updates):
    refreshed = run_analysis(monkeypatch, AnalysisService(error=RuntimeError("model missing")),
                             strategy="YOLO")
    last = updates[-1]
    assert refreshed == [] and last["status"] is JobStatus.FAILED
    assert last["error"] == "model missing"
    assert last["message"] == "Hiba az elemzés során: model missing"


# ----------------------------------------------------------------- training job

class TrainingService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def run_training(self, job_id):
        if self.error:
            raise self.error
        return self.result


def run_training(monkeypatch, service):
    install(monkeypatch, "app.services.training_service", training_service=service)
    tasks.run_training_job("job1")


def test_training_job_completes_with_the_providers_message(monkeypatch, updates):
    result = {"status": "success", "message": "Kész: best.pt"}
    run_training(monkeypatch, TrainingService(result))
    done = updates[-1]
    assert statuses(updates) == [JobStatus.RUNNING, JobStatus.COMPLETED]
    assert done["progress"] == 100 and done["message"] == "Kész: best.pt"
    assert done["result"] == result


def test_training_job_has_a_default_completion_message(monkeypatch, updates):
    run_training(monkeypatch, TrainingService({"status": "success"}))
    assert updates[-1]["message"] == "Modell finomhangolva és élesítve!"


def test_cancelled_training_job_is_not_marked_completed(monkeypatch, updates):
    run_training(monkeypatch, TrainingService({"status": "cancelled"}))
    assert statuses(updates) == [JobStatus.RUNNING]


def test_failed_training_job_records_the_error(monkeypatch, updates):
    run_training(monkeypatch, TrainingService(error=RuntimeError("out of memory")))
    last = updates[-1]
    assert last["status"] is JobStatus.FAILED and last["error"] == "out of memory"
    assert last["message"] == "Hiba a tanítás során: out of memory"
