"""Image download step with fakes: no database, no Street View, no API key.

Covers exact-panorama capture metadata at download time and the download loop's
stop / skip rules (quota and billing signals end the job, a single bad image
is skipped, unfetched points keep their queued URL)."""
import datetime as dt
import json
import re
from types import SimpleNamespace

import pytest

from app.services import image_downloader as idl
from app.services.sv_client import StreetViewError, StreetViewFatal
from app.services.sv_quota import JobBudget, QuotaExceeded

JPEG = b"\xff\xd8" + b"x" * 64
KNOWN_DATE = dt.date(2022, 6, 1)


def point(id, **overrides):
    values = dict(id=id, image_url=f"https://example.invalid/sv?p={id}", latitude=47.0,
                  longitude=19.0, pano_id=f"pano{id}", capture_date=KNOWN_DATE)
    values.update(overrides)
    return SimpleNamespace(**values)


# -------------------------------------------------------- get_capture_metadata

def test_known_capture_date_is_refreshed_by_the_stored_pano():
    calls = []
    img = point(1)

    def lookup(*a, **k):
        calls.append((a, k))
        return {"date": "2024-07", "pano_id": "pano1"}

    assert idl.get_capture_metadata(img, lookup=lookup) == ("pano1", dt.date(2024, 7, 1))
    assert calls == [((), {"pano_id": "pano1"})]
    assert img.capture_date == KNOWN_DATE  # nothing is written before the image succeeds


def test_lookup_by_pano_id_fills_the_capture_month():
    calls = []

    def lookup(*args, **kwargs):
        calls.append((args, kwargs))
        return {"date": "2023-05", "pano_id": "pano1"}

    img = point(1, capture_date=None)
    assert idl.get_capture_metadata(img, lookup=lookup) == ("pano1", dt.date(2023, 5, 1))
    assert calls == [((), {"pano_id": "pano1"})]
    assert img.capture_date is None and img.pano_id == "pano1"


def test_lookup_by_position_also_fills_a_missing_pano_id():
    calls = []

    def lookup(*args, **kwargs):
        calls.append((args, kwargs))
        return {"date": "2021", "pano_id": "found"}

    img = point(1, capture_date=None, pano_id=None)
    assert idl.get_capture_metadata(img, lookup=lookup) == ("found", dt.date(2021, 1, 1))
    assert calls == [((47.0, 19.0), {})]
    assert img.capture_date is None and img.pano_id is None


def test_failed_or_empty_lookup_cannot_supply_metadata():
    def failing(*args, **kwargs):
        raise RuntimeError("metadata down")

    img = point(1, capture_date=None, pano_id=None)
    with pytest.raises(RuntimeError, match="metadata down"):
        idl.get_capture_metadata(img, lookup=failing)
    with pytest.raises(StreetViewError, match="panorama unavailable"):
        idl.get_capture_metadata(img, lookup=lambda *a, **k: None)
    assert img.capture_date is None and img.pano_id is None


def test_malformed_date_gives_no_capture_date():
    img = point(1, capture_date=None)
    assert idl.get_capture_metadata(img, lookup=lambda **k: {
        "pano_id": "pano1", "date": "sometime"}) == ("pano1", None)
    assert img.capture_date is None


# ------------------------------------------------------------- download_images

class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *criteria):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(self.rows)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class FakeClient:
    """Answers per stored URL: bytes, or an exception to raise."""

    def __init__(self, answers=None, metadata_answers=None):
        self.answers = answers or {}
        self.metadata_answers = metadata_answers or {}
        self.requests = []
        self.metadata_requests = []
        self.panos = []

    def metadata(self, *args, **kwargs):
        self.metadata_requests.append((args, kwargs))
        pano_id = kwargs.get("pano_id", "resolved")
        answer = self.metadata_answers.get(pano_id, {"pano_id": pano_id, "date": "2022-06"})
        if isinstance(answer, Exception):
            raise answer
        return answer

    def image_from_url(self, url, job=None, *, pano_id):
        self.requests.append((url, job))
        self.panos.append(pano_id)
        answer = self.answers.get(url, JPEG)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def rig(monkeypatch, tmp_path):
    """Wire the module to fakes; returns (start, updates, images_dir)."""
    updates = []
    monkeypatch.setattr(idl, "update_job", lambda job_id, **kw: updates.append((job_id, kw)))
    monkeypatch.setattr(idl, "settings", SimpleNamespace(resolve_data_dir=lambda: str(tmp_path)))

    def start(rows, client=None):
        session = FakeSession(rows)
        client = client or FakeClient()
        monkeypatch.setattr(idl, "SessionLocal", lambda: session)
        monkeypatch.setattr(idl, "default_client", lambda: client)
        return session, client

    return start, updates, tmp_path / "images"


def test_nothing_pending_reports_and_stops(rig):
    start, updates, images_dir = rig
    session, client = start([])
    idl.download_images("job1")
    assert client.requests == [] and not images_dir.exists()
    assert updates[0][1]["current_step"] is idl.JobStep.DOWNLOADING
    assert updates[-1] == ("job1", {"progress": 50, "message": "Nincs új letöltendő kép."})
    assert session.closed


def test_downloaded_images_are_stored_and_relinked_to_local_paths(rig):
    start, updates, images_dir = rig
    rows = [point(1), point(2)]
    urls = [r.image_url for r in rows]
    budget = JobBudget(10)
    session, client = start(rows)

    idl.download_images("job1", budget)

    assert client.requests == [(urls[0], budget), (urls[1], budget)]
    assert client.panos == ["pano1", "pano2"]
    assert client.metadata_requests == [((), {"pano_id": "pano1"}), ((), {"pano_id": "pano2"})]
    for row in rows:
        assert re.fullmatch(rf"images/sv_{row.id}_[0-9a-f]{{8}}\.jpg", row.image_url)
        assert (images_dir / row.image_url.split("/")[1]).read_bytes() == JPEG
    assert updates[-1][1] == {"progress": 50, "message": "2 kép letöltve."}
    assert session.commits >= 1 and session.closed


def test_progress_runs_from_30_to_50_percent(rig):
    start, updates, _ = rig
    start([point(i) for i in range(1, 11)])
    idl.download_images("job1", JobBudget(100))
    progress = [kw["progress"] for _, kw in updates]
    assert progress == [30, 30, 40, 50]                # start, i=0, i=5, done
    assert updates[2][1]["message"] == "Letöltés: 6/10"


def test_one_bad_image_is_skipped_and_keeps_its_queued_url(rig):
    start, updates, images_dir = rig
    rows = [point(1), point(2), point(3)]
    queued = {r.id: r.image_url for r in rows}
    session, client = start(rows, FakeClient({
        queued[1]: StreetViewError("no imagery here"),
        queued[2]: ValueError("unexpected"),
    }))

    idl.download_images("job1", JobBudget(10))

    assert rows[0].image_url == queued[1] and rows[1].image_url == queued[2]
    assert rows[2].image_url.startswith("images/sv_3_")
    assert len(list(images_dir.iterdir())) == 1
    assert updates[-1][1]["message"] == "1 kép letöltve."


@pytest.mark.parametrize("signal", [QuotaExceeded("monthly cap"), StreetViewFatal("billing")])
def test_quota_or_billing_signal_ends_the_job_but_keeps_what_was_fetched(rig, signal):
    start, updates, images_dir = rig
    rows = [point(1), point(2), point(3)]
    queued = {r.id: r.image_url for r in rows}
    session, client = start(rows, FakeClient({queued[2]: signal}))

    with pytest.raises(RuntimeError, match=r"stopped after 1 of 3 images: " + str(signal)):
        idl.download_images("job1", JobBudget(10))

    assert [url for url, _ in client.requests] == [queued[1], queued[2]]   # 3 never asked
    assert rows[0].image_url.startswith("images/sv_1_")
    assert rows[1].image_url == queued[2] and rows[2].image_url == queued[3]
    assert session.commits >= 1 and session.closed     # the fetched image is committed
    assert "letöltve" not in updates[-1][1].get("message", "")


def test_without_a_budget_the_job_cap_comes_from_the_environment(rig, monkeypatch):
    start, _, _ = rig
    monkeypatch.setattr(idl, "cap_from_env", lambda name, default: 7)
    _, client = start([point(1)])
    idl.download_images("job1")
    (_, budget), = client.requests
    assert isinstance(budget, JobBudget) and budget.cap == 7


def test_download_fills_a_missing_capture_date(rig):
    start, _, _ = rig
    rows = [point(1, capture_date=None), point(2)]
    start(rows)
    idl.download_images("job1", JobBudget(10))
    assert [r.capture_date for r in rows] == [KNOWN_DATE, KNOWN_DATE]


def test_legacy_location_queue_resolves_pano_before_fetch_and_replaces_stale_date(rig):
    start, _, _ = rig
    img = point(1, pano_id=None, capture_date=dt.date(2010, 1, 1))
    _, client = start([img])
    idl.download_images("job1", JobBudget(10))
    assert client.metadata_requests == [((47.0, 19.0), {})]
    assert client.panos == ["resolved"]
    assert img.pano_id == "resolved" and img.capture_date == KNOWN_DATE


@pytest.mark.parametrize("metadata", [None, {}, {"pano_id": "replacement", "date": "2026-11"},
                                      StreetViewError("metadata down")])
def test_unavailable_or_replaced_stored_pano_stays_queued_without_an_image_request(rig, metadata):
    start, _, images_dir = rig
    img = point(1)
    queued = img.image_url
    _, client = start([img], FakeClient(metadata_answers={"pano1": metadata}))
    idl.download_images("job1", JobBudget(10))
    assert client.metadata_requests == [((), {"pano_id": "pano1"})]
    assert client.requests == [] and list(images_dir.iterdir()) == []
    assert (img.image_url, img.pano_id, img.capture_date) == (queued, "pano1", KNOWN_DATE)


@pytest.mark.parametrize("date", [None, "invalid"])
def test_missing_or_invalid_exact_pano_date_clears_a_stale_date(rig, date):
    start, _, _ = rig
    img = point(1)
    start([img], FakeClient(metadata_answers={"pano1": {"pano_id": "pano1", "date": date}}))
    idl.download_images("job1", JobBudget(10))
    assert img.capture_date is None and img.pano_id == "pano1"


def test_metadata_fatal_signal_stops_without_spending_an_image_request(rig):
    start, _, _ = rig
    rows = [point(1), point(2)]
    session, client = start(rows, FakeClient(metadata_answers={"pano1": StreetViewFatal("billing")}))
    with pytest.raises(RuntimeError, match="stopped after 0 of 2 images: billing"):
        idl.download_images("job1", JobBudget(10))
    assert client.requests == [] and len(client.metadata_requests) == 1
    assert session.closed


def test_failed_image_leaves_old_capture_metadata_untouched(rig):
    start, _, _ = rig
    img = point(1, pano_id=None, capture_date=dt.date(2010, 1, 1))
    start([img], FakeClient({img.image_url: StreetViewError("gone")}))
    idl.download_images("job1", JobBudget(10))
    assert img.pano_id is None and img.capture_date == dt.date(2010, 1, 1)


def test_resumed_download_fetches_only_stored_pano_and_its_capture_date(rig, tmp_path):
    from app.services.sv_client import StreetViewClient
    from app.services.sv_quota import StreetViewQuota
    from test_sv_quota_client import JPEG as real_jpeg

    start, _, images_dir = rig
    calls = []

    def http(url, params, timeout):
        calls.append((url, params))
        assert params["pano"] == "original" and "location" not in params
        if url.endswith("/metadata"):
            return 200, "application/json", json.dumps({
                "status": "OK", "pano_id": "original", "date": "2018-04",
            }).encode()
        assert params["return_error_code"] == "true"
        assert params["heading"] == "67.6" and params["pitch"] == "-20"
        return 200, "image/jpeg", real_jpeg

    client = StreetViewClient("KEY", StreetViewQuota(tmp_path / "quota.json"),
                              http_get=http, sleep=lambda _: None)
    img = point(1, pano_id="original", image_url=(
        "https://maps.googleapis.com/maps/api/streetview?location=47,19&heading=67.6&pitch=-20"))
    start([img], client)
    budget = JobBudget(1)
    idl.download_images("job1", budget)
    assert len(calls) == 2
    assert img.capture_date == dt.date(2018, 4, 1) and img.pano_id == "original"
    assert (images_dir / img.image_url.split("/")[1]).read_bytes() == real_jpeg
    assert client.quota.used() == budget.used == 1 and client.quota.used("metadata") == 1


def test_placeholder_is_never_saved_and_a_retry_can_fetch_the_same_pano(rig, tmp_path):
    from app.services.sv_client import StreetViewClient
    from app.services.sv_quota import StreetViewQuota
    from test_sv_quota_client import FakeHttp, OK_IMAGE, image_bytes, meta

    start, _, images_dir = rig
    metadata = meta(pano_id="pano1", date="2018-04")
    http = FakeHttp(metadata, (200, "image/jpeg", image_bytes(placeholder=True)), metadata, OK_IMAGE)
    client = StreetViewClient("KEY", StreetViewQuota(tmp_path / "quota.json"),
                              http_get=http, sleep=lambda _: None)
    img = point(1, image_url="https://maps.googleapis.com/maps/api/streetview?location=47,19")
    queued = img.image_url
    start([img], client)
    idl.download_images("job1", JobBudget(1))
    assert img.image_url == queued and img.capture_date == KNOWN_DATE
    assert list(images_dir.iterdir()) == []
    idl.download_images("job2", JobBudget(1))
    assert img.image_url.startswith("images/sv_1_") and len(list(images_dir.iterdir())) == 1
    assert img.capture_date == dt.date(2018, 4, 1)
    assert client.quota.used() == 2 and client.quota.used("metadata") == 2
