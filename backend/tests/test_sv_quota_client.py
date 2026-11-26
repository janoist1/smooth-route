"""Street View budget counter and the gentle client (no network, no DB)."""
import datetime as dt
import json

import pytest

from app.services.sv_client import (
    SteadyRate,
    StreetViewClient,
    StreetViewError,
    StreetViewFatal,
    rate_from_env,
)
from app.services.sv_quota import (
    DEFAULT_MONTHLY_CAP,
    JobBudget,
    QuotaExceeded,
    StreetViewQuota,
    cap_from_env,
    month_key,
)

NOV = dt.datetime(2026, 11, 26, 12, 0)
DEC = dt.datetime(2026, 12, 1, 0, 5)


class Clock:
    def __init__(self, moment=NOV):
        self.moment = moment

    def __call__(self):
        return self.moment


def quota(tmp_path, cap=10, clock=None):
    return StreetViewQuota(tmp_path / "quota" / "street_view.json", monthly_cap=cap,
                           now=clock or Clock())


# ---- quota ----------------------------------------------------------------

def test_reserve_counts_and_persists(tmp_path):
    q = quota(tmp_path)
    assert q.used() == 0 and q.remaining() == 10
    assert q.reserve() == 1
    assert q.reserve(3) == 4
    # A second process (new object, same file) sees the same number.
    assert quota(tmp_path).used() == 4
    data = json.loads((tmp_path / "quota" / "street_view.json").read_text())
    assert data["months"]["2026-11"]["static_images"] == 4
    assert not list((tmp_path / "quota").glob("*.tmp*"))


def test_monthly_cap_is_a_hard_stop_before_the_request(tmp_path):
    q = quota(tmp_path, cap=3)
    q.reserve(3)
    with pytest.raises(QuotaExceeded, match="monthly"):
        q.reserve()
    assert q.used() == 3                       # the refused request was not booked
    with pytest.raises(QuotaExceeded):
        quota(tmp_path, cap=3).reserve()       # nor can another process sneak one in
    q2 = quota(tmp_path, cap=5)
    with pytest.raises(QuotaExceeded):
        q2.reserve(3)                          # 3 + 3 > 5: all-or-nothing
    assert q2.used() == 3
    assert q2.reserve(2) == 5


def test_per_job_cap(tmp_path):
    q = quota(tmp_path, cap=100)
    job = JobBudget(cap=2)
    q.reserve(job=job)
    q.reserve(job=job)
    assert job.remaining == 0
    with pytest.raises(QuotaExceeded, match="per-job"):
        q.reserve(job=job)
    assert (q.used(), job.used) == (2, 2)
    q.reserve(job=JobBudget(cap=5))            # another job still has room
    assert q.used() == 3


def test_job_is_not_charged_when_the_month_is_full(tmp_path):
    q = quota(tmp_path, cap=1)
    job = JobBudget(cap=10)
    q.reserve(job=job)
    with pytest.raises(QuotaExceeded):
        q.reserve(job=job)
    assert job.used == 1


def test_counter_starts_fresh_each_month(tmp_path):
    clock = Clock(NOV)
    q = quota(tmp_path, cap=2, clock=clock)
    q.reserve(2)
    clock.moment = DEC
    assert q.used() == 0
    assert q.reserve() == 1
    data = json.loads(q.path.read_text())
    assert data["months"]["2026-11"]["static_images"] == 2     # history is kept
    assert month_key(DEC) == "2026-12"


def test_metadata_is_counted_but_never_capped(tmp_path):
    q = quota(tmp_path, cap=1)
    for _ in range(5):
        q.note_metadata()
    assert q.used("metadata") == 5 and q.used() == 0
    assert "0/1 images, 5 metadata" in q.summary()


def test_broken_quota_file_blocks_instead_of_guessing(tmp_path):
    q = quota(tmp_path)
    q.reserve()
    q.path.write_text("{half a file")
    with pytest.raises(QuotaExceeded, match="unreadable"):
        q.reserve()


def test_set_used_and_argument_checks(tmp_path):
    q = quota(tmp_path, cap=100)
    q.set_used(40)
    assert q.remaining() == 60
    with pytest.raises(ValueError):
        q.reserve(0)
    with pytest.raises(ValueError):
        q.set_used(-1)


def test_caps_from_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_SV_MONTHLY_CAP", raising=False)
    assert cap_from_env("GOOGLE_SV_MONTHLY_CAP", DEFAULT_MONTHLY_CAP) == 5000
    monkeypatch.setenv("GOOGLE_SV_MONTHLY_CAP", "1200")
    assert cap_from_env("GOOGLE_SV_MONTHLY_CAP", 5000) == 1200
    assert StreetViewQuota("unused.json").monthly_cap == 1200
    for junk in ("", "lots", "-5"):            # junk never means "unlimited"
        monkeypatch.setenv("GOOGLE_SV_MONTHLY_CAP", junk)
        assert cap_from_env("GOOGLE_SV_MONTHLY_CAP", 5000) == 5000
    monkeypatch.setenv("GOOGLE_SV_MONTHLY_CAP", "0")
    assert cap_from_env("GOOGLE_SV_MONTHLY_CAP", 5000) == 0    # 0 = fetch nothing


# ---- pacing ---------------------------------------------------------------

class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_steady_rate_spaces_requests_evenly():
    t = FakeTime()
    rate = SteadyRate(1.0, clock=t.clock, sleep=t.sleep)
    for _ in range(4):
        rate.wait()
    assert t.sleeps == [1.0, 1.0, 1.0]         # first goes at once, then 1 s apart
    t.now += 10                                 # a long pause does not earn a burst
    rate.wait()
    rate.wait()
    assert t.sleeps[-1] == 1.0
    with pytest.raises(ValueError):
        SteadyRate(0)


def test_rate_from_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_SV_RATE_PER_S", raising=False)
    assert rate_from_env() == 1.0
    monkeypatch.setenv("GOOGLE_SV_RATE_PER_S", "0.5")
    assert rate_from_env() == 0.5
    for junk in ("fast", "0", "-2"):
        monkeypatch.setenv("GOOGLE_SV_RATE_PER_S", junk)
        assert rate_from_env() == 1.0


# ---- client ---------------------------------------------------------------

JPEG = b"\xff\xd8\xff\xe0 fake jpeg"
OK_IMAGE = (200, "image/jpeg", JPEG)


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, params, timeout_s):
        self.calls.append((url, dict(params)))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(tmp_path, http, cap=10, **kw):
    t = FakeTime()
    logs = []
    c = StreetViewClient("SECRET-KEY", quota(tmp_path, cap=cap), http_get=http,
                         sleep=t.sleep, clock=t.clock, log=logs.append, **kw)
    return c, t, logs


def meta(status="OK", **extra):
    body = {"status": status, **extra}
    return (200, "application/json", json.dumps(body).encode())


def test_image_request_is_booked_then_sent_like_the_training_frames(tmp_path):
    http = FakeHttp(OK_IMAGE)
    c, _t, _logs = client(tmp_path, http)
    job = JobBudget(cap=5)
    assert c.image(pano_id="PANO1", heading=123.4, job=job) == JPEG
    url, params = http.calls[0]
    assert url == "https://maps.googleapis.com/maps/api/streetview"
    assert params == {"size": "600x400", "heading": 123.4, "pitch": -20.0,
                      "return_error_code": "true", "pano": "PANO1", "key": "SECRET-KEY"}
    assert (c.quota.used(), job.used) == (1, 1)

    http.responses.append(OK_IMAGE)
    c.image(lat=47.5, lng=19.05, heading=0.0)
    assert http.calls[1][1]["location"] == "47.5,19.05"


def test_over_the_cap_nothing_is_sent(tmp_path):
    http = FakeHttp(OK_IMAGE, OK_IMAGE)
    c, _t, _logs = client(tmp_path, http, cap=1)
    c.image(pano_id="A", heading=0)
    with pytest.raises(QuotaExceeded):
        c.image(pano_id="B", heading=0)
    assert len(http.calls) == 1

    http2 = FakeHttp(OK_IMAGE)
    c2, _t, _logs = client(tmp_path / "other", http2, cap=100)
    with pytest.raises(QuotaExceeded, match="per-job"):
        c2.image(pano_id="A", heading=0, job=JobBudget(cap=0))
    assert http2.calls == []


@pytest.mark.parametrize("status", [403, 429])
def test_quota_or_billing_http_status_aborts_without_retry(tmp_path, status):
    http = FakeHttp((status, "text/plain", b"The request is over quota / billing not enabled"))
    c, t, _logs = client(tmp_path, http)
    with pytest.raises(StreetViewFatal, match=str(status)):
        c.image(pano_id="A", heading=0)
    assert len(http.calls) == 1 and t.sleeps == []
    assert "SECRET-KEY" not in str(http.calls[0][0])


def test_transient_errors_back_off_and_every_attempt_is_booked(tmp_path):
    http = FakeHttp((503, "text/html", b"busy"), ConnectionError("https://…?key=SECRET-KEY"),
                    OK_IMAGE)
    c, t, logs = client(tmp_path, http)
    assert c.image(pano_id="A", heading=0) == JPEG
    assert len(http.calls) == 3
    assert c.quota.used() == 3                 # never under-count what Google may bill
    assert 2.0 in t.sleeps and 4.0 in t.sleeps  # exponential back-off
    assert all("SECRET-KEY" not in line for line in logs)       # key never logged


def test_gives_up_after_the_retries(tmp_path):
    http = FakeHttp(*[(500, "text/html", b"")] * 3)
    c, _t, _logs = client(tmp_path, http, retries=2)
    with pytest.raises(StreetViewError, match="3 attempts"):
        c.image(pano_id="A", heading=0)


def test_missing_image_is_a_skip_not_a_stop(tmp_path):
    http = FakeHttp((404, "text/plain", b"no imagery"), (200, "text/html", b"<html>"),
                    (400, "text/plain", b"You have exceeded your daily request quota"))
    c, _t, _logs = client(tmp_path, http)
    with pytest.raises(StreetViewError):
        c.image(pano_id="A", heading=0)
    with pytest.raises(StreetViewError):
        c.image(pano_id="B", heading=0)        # 200 but not an image
    with pytest.raises(StreetViewFatal):
        c.image(pano_id="C", heading=0)        # quota wording in the body → stop


def test_requests_are_paced_across_metadata_and_images(tmp_path):
    http = FakeHttp(meta(pano_id="P", location={"lat": 1.0, "lng": 2.0}, date="2024-05"),
                    OK_IMAGE, meta("ZERO_RESULTS"))
    c, t, _logs = client(tmp_path, http, rate_per_s=1.0)
    assert c.metadata(47.5, 19.05, radius=25) == {"pano_id": "P", "lat": 1.0, "lng": 2.0,
                                                  "date": "2024-05"}
    c.image(pano_id="P", heading=10)
    assert c.metadata(47.6, 19.05) is None
    assert t.sleeps == [1.0, 1.0]              # one shared, steady queue
    assert http.calls[0][1] == {"location": "47.5,19.05", "radius": 25, "key": "SECRET-KEY"}
    assert c.quota.used("metadata") == 2 and c.quota.used() == 1


@pytest.mark.parametrize("status", ["OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT", "REQUEST_DENIED"])
def test_metadata_quota_status_is_fatal(tmp_path, status):
    c, _t, _logs = client(tmp_path, FakeHttp(meta(status)))
    with pytest.raises(StreetViewFatal, match=status):
        c.metadata(47.5, 19.05)


def test_metadata_by_pano_id_and_odd_answers(tmp_path):
    http = FakeHttp(meta("NOT_FOUND"), meta("UNKNOWN_ERROR"), (200, "text/html", b"<html>"))
    c, _t, _logs = client(tmp_path, http)
    assert c.metadata(pano_id="GONE") is None
    assert http.calls[0][1] == {"pano": "GONE", "key": "SECRET-KEY"}
    with pytest.raises(StreetViewError):
        c.metadata(47.5, 19.05)
    with pytest.raises(StreetViewError):
        c.metadata(47.5, 19.05)


def test_no_api_key_is_fatal_before_any_request(tmp_path):
    http = FakeHttp(OK_IMAGE)
    c = StreetViewClient(None, quota(tmp_path), http_get=http, sleep=lambda s: None)
    with pytest.raises(StreetViewFatal, match="GOOGLE_MAPS_API_KEY"):
        c.metadata(47.5, 19.05)
    assert http.calls == []


def test_stored_url_is_fetched_through_the_guard_with_the_configured_key(tmp_path):
    http = FakeHttp(OK_IMAGE)
    c, _t, _logs = client(tmp_path, http, cap=1)
    stored = ("https://maps.googleapis.com/maps/api/streetview?size=600x400"
              "&location=47.5,19.05&heading=67.6&pitch=-20.0&key=OLD-LEAKED-KEY")
    assert c.image_from_url(stored) == JPEG
    params = http.calls[0][1]
    assert params["key"] == "SECRET-KEY" and params["location"] == "47.5,19.05"
    assert params["heading"] == "67.6" and params["pitch"] == "-20.0"
    with pytest.raises(QuotaExceeded):
        c.image_from_url(stored)               # cap of 1 is used up
    with pytest.raises(StreetViewError):
        c.image_from_url("https://example.com/maps/api/streetview?x=1")
