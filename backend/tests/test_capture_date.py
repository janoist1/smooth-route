"""Street View capture-date handling: parsing, age, backfill rules, GraphQL."""
import datetime as dt
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
import strawberry

from app.graphql.types import Point
from app.services import capture_date as cd
from app.services.image_downloader import fill_capture_metadata

BACKFILL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_capture_date.py"


def _load_backfill():
    spec = importlib.util.spec_from_file_location("backfill_capture_date", BACKFILL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- parsing / formatting -------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2019-06", dt.date(2019, 6, 1)),
        ("2019-6", dt.date(2019, 6, 1)),
        ("2019", dt.date(2019, 1, 1)),
        ("2021-11-23", dt.date(2021, 11, 1)),
        (" 2015-02 ", dt.date(2015, 2, 1)),
    ],
)
def test_parse_capture_date_valid(raw, expected):
    assert cd.parse_capture_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "June 2019", "2019-13", "2019-00", "1800-01", 2019])
def test_parse_capture_date_invalid_is_none(raw):
    assert cd.parse_capture_date(raw) is None


def test_format_capture_date_is_month_precision():
    assert cd.format_capture_date(dt.date(2019, 6, 1)) == "2019-06"
    assert cd.format_capture_date(None) is None


# --- age / staleness -----------------------------------------------------


def test_capture_age_months():
    today = dt.date(2026, 11, 18)
    assert cd.capture_age_months(dt.date(2026, 11, 1), today) == 0
    assert cd.capture_age_months(dt.date(2025, 12, 1), today) == 11
    assert cd.capture_age_months(dt.date(2019, 6, 1), today) == 89
    assert cd.capture_age_months(None, today) is None
    # Future dates (clock skew) never go negative.
    assert cd.capture_age_months(dt.date(2027, 1, 1), today) == 0


def test_is_stale_capture_threshold_is_strictly_more_than_four_years():
    today = dt.date(2026, 11, 18)
    assert cd.is_stale_capture(dt.date(2022, 11, 1), today) is False  # exactly 48 months
    assert cd.is_stale_capture(dt.date(2022, 10, 1), today) is True  # 49 months
    assert cd.is_stale_capture(None, today) is False  # unknown is not "old"


# --- backfill decision -----------------------------------------------------


def test_backfill_by_pano_id_always_trusts_the_date():
    outcome, date = cd.backfill_decision(
        {"date": "2026-03"}, by_pano_id=True, image_fetched_at=dt.datetime(2026, 1, 5)
    )
    assert (outcome, date) == (cd.ACCEPT, dt.date(2026, 3, 1))


def test_backfill_by_location_accepts_pano_older_than_download():
    outcome, date = cd.backfill_decision(
        {"date": "2019-06"}, by_pano_id=False, image_fetched_at=dt.datetime(2026, 1, 5)
    )
    assert (outcome, date) == (cd.ACCEPT, dt.date(2019, 6, 1))


@pytest.mark.parametrize("pano_date", ["2026-01", "2026-04"])
def test_backfill_by_location_rejects_pano_not_older_than_download(pano_date):
    # Same month or later: Google replaced the imagery after (or as) we fetched.
    outcome, date = cd.backfill_decision(
        {"date": pano_date}, by_pano_id=False, image_fetched_at=dt.datetime(2026, 1, 20)
    )
    assert (outcome, date) == (cd.NEWER_PANO, None)


def test_backfill_by_location_without_fetch_time_is_not_trusted():
    outcome, _ = cd.backfill_decision({"date": "2019-06"}, by_pano_id=False, image_fetched_at=None)
    assert outcome == cd.NEWER_PANO


def test_backfill_without_date_field():
    assert cd.backfill_decision({}, by_pano_id=True, image_fetched_at=None) == (cd.NO_DATE, None)
    assert cd.backfill_decision(None, by_pano_id=True, image_fetched_at=None) == (cd.NO_DATE, None)


# --- backfill script --------------------------------------------------------


def test_resolve_row_uses_pano_id_when_present():
    bf = _load_backfill()
    calls = []

    def lookup(**kw):
        calls.append(kw)
        return "OK", {"status": "OK", "date": "2018-07", "pano_id": "P1"}

    row = (1, 47.5, 19.0, "P1", dt.datetime(2026, 1, 3))
    assert bf.resolve_row(row, lookup) == (cd.ACCEPT, dt.date(2018, 7, 1), None)
    assert calls == [{"pano_id": "P1"}]


def test_resolve_row_by_location_fills_pano_id_only_when_accepted():
    bf = _load_backfill()
    old = lambda **kw: ("OK", {"status": "OK", "date": "2018-07", "pano_id": "NEW"})  # noqa: E731
    new = lambda **kw: ("OK", {"status": "OK", "date": "2026-05", "pano_id": "NEW"})  # noqa: E731
    row = (1, 47.5, 19.0, None, dt.datetime(2026, 1, 3))
    assert bf.resolve_row(row, old) == (cd.ACCEPT, dt.date(2018, 7, 1), "NEW")
    assert bf.resolve_row(row, new) == (cd.NEWER_PANO, None, None)


@pytest.mark.parametrize(
    "status, outcome",
    [("ZERO_RESULTS", "no_pano"), ("NOT_FOUND", "no_pano"), ("REQUEST_DENIED", "error:REQUEST_DENIED")],
)
def test_resolve_row_non_ok_statuses_write_nothing(status, outcome):
    bf = _load_backfill()
    row = (1, 47.5, 19.0, None, dt.datetime(2026, 1, 3))
    assert bf.resolve_row(row, lambda **kw: (status, {"status": status})) == (outcome, None, None)


def test_rate_limiter_spaces_calls():
    bf = _load_backfill()
    now = [100.0]
    slept = []

    def sleep(s):
        slept.append(round(s, 6))
        now[0] += s

    limiter = bf.RateLimiter(qps=4, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        limiter.wait()
    assert slept == [0.25, 0.25]  # first call immediate, then 1/qps apart


def test_fetch_metadata_retries_over_query_limit(monkeypatch):
    bf = _load_backfill()
    monkeypatch.setattr(bf.time, "sleep", lambda s: None)
    responses = iter([{"status": "OVER_QUERY_LIMIT"}, {"status": "OK", "date": "2020-01"}])

    class FakeHttp:
        def get(self, url, params, timeout):
            assert params["pano"] == "P1"
            return SimpleNamespace(status_code=200, json=lambda: next(responses))

    limiter = bf.RateLimiter(qps=1000, sleep=lambda s: None)
    status, data = bf.fetch_metadata(FakeHttp(), "k", limiter, pano_id="P1")
    assert status == "OK" and data["date"] == "2020-01"


# --- download-time fill -------------------------------------------------------


def _img(**kw):
    base = dict(id=1, latitude=47.5, longitude=19.0, pano_id=None, capture_date=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_fill_capture_metadata_at_download_sets_date_and_pano():
    img = _img()
    fill_capture_metadata(img, lookup=lambda *a, **kw: {"date": "2021-09", "pano_id": "PX"})
    assert img.capture_date == dt.date(2021, 9, 1)
    assert img.pano_id == "PX"


def test_fill_capture_metadata_prefers_pano_id_and_keeps_existing():
    seen = {}

    def lookup(*a, **kw):
        seen.update(kw)
        return {"date": "2021-09", "pano_id": "OTHER"}

    img = _img(pano_id="P1")
    fill_capture_metadata(img, lookup=lookup)
    assert seen == {"pano_id": "P1"} and img.pano_id == "P1"

    dated = _img(capture_date=dt.date(2015, 1, 1))
    fill_capture_metadata(dated, lookup=lambda *a, **kw: pytest.fail("no lookup needed"))
    assert dated.capture_date == dt.date(2015, 1, 1)


def test_fill_capture_metadata_swallows_lookup_errors():
    img = _img()

    def boom(*a, **kw):
        raise RuntimeError("network")

    fill_capture_metadata(img, lookup=boom)
    assert img.capture_date is None


# --- collection path ----------------------------------------------------------


def test_route_metadata_carries_capture_date(monkeypatch):
    from app.services.google_maps import GoogleMapsService

    svc = GoogleMapsService.__new__(GoogleMapsService)
    svc.client = None
    monkeypatch.setattr(
        svc,
        "get_panorama_metadata",
        lambda lat, lng: {"pano_id": "P1", "lat": lat, "lng": lng, "date": "2017-08"},
    )
    monkeypatch.setattr(svc, "get_street_view_url", lambda *a, **kw: "http://img")
    meta = svc.generate_street_view_metadata([(47.5, 19.0), (47.5001, 19.0)])
    assert meta[0]["capture_date"] == dt.date(2017, 8, 1)
    assert meta[0]["pano_id"] == "P1"


# --- GraphQL ---------------------------------------------------------------


def _point(capture: Optional[dt.date]) -> Point:
    return Point(
        id=1, latitude=47.5, longitude=19.0, heading=90.0, pitch=-20.0, image_url=None,
        rqi_score=2.0, damage_count=0, damage_types=None, analysis_metadata=None,
        created_at=dt.datetime(2026, 1, 1), capture_date_value=capture,
    )


@strawberry.type
class _Q:
    @strawberry.field
    def dated(self) -> Point:
        return _point(dt.date(2019, 6, 1))

    @strawberry.field
    def undated(self) -> Point:
        return _point(None)


def test_graphql_point_exposes_capture_date_as_year_month():
    result = strawberry.Schema(query=_Q).execute_sync("{ dated { captureDate } undated { captureDate } }")
    assert result.errors is None
    assert result.data == {"dated": {"captureDate": "2019-06"}, "undated": {"captureDate": None}}


def test_read_only_schema_exposes_capture_date():
    from app.graphql.schema import read_schema

    sdl = read_schema.as_str()
    point_block = sdl.split("type Point {", 1)[1].split("}", 1)[0]
    assert "captureDate: String" in point_block
    # The private DB value must not leak as its own field.
    assert "captureDateValue" not in sdl


# --- publish -------------------------------------------------------------------


def test_publish_carries_capture_date_and_only_real_columns():
    spec = importlib.util.spec_from_file_location(
        "publish", BACKFILL_PATH.parent / "publish.py"
    )
    publish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publish)

    from app.models.models import StreetViewImage

    assert "capture_date" in publish.PUBLIC_COLUMNS
    assert set(publish.PUBLIC_COLUMNS) <= set(StreetViewImage.__table__.columns.keys())
