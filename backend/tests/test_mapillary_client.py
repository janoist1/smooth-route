"""Mapillary collector prototype: fixture JSON + fake HTTP, no network, no DB.
Fixture: tests/fixtures/mapillary_images_search.json (shape of the Graph API v4
/images response; hand-built, see its _note)."""
import datetime as dt
import io
import json
from pathlib import Path

import pytest

from app.services import mapillary_client as mc
from app.services.map_matching import LineIndex
from app.services.network_collector import SAVED, USER_PANO, process_candidate
from app.services.network_sampling import sample_line
from app.services.sv_client import StreetViewError, StreetViewFatal
from app.services.sv_quota import JobBudget, QuotaExceeded, StreetViewQuota
from geo_helpers import FakeLine, at

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "mapillary_images_search.json").read_text())
TOKEN = "MLY|1234567890|deadbeefcafe"
ROAD = FakeLine(10, [at(0, 0), at(1000, 0)])   # heading east
CANDIDATE = sample_line(ROAD, 50)[3]           # 175 m along: the fixture's centre
P = at(175, 0)


def jpeg(w=1024, h=768, top=(255, 255, 255), bottom=(0, 0, 0)) -> bytes:
    img = Image.new("RGB", (w, h), top)
    img.paste(Image.new("RGB", (w, h // 2), bottom), (0, h // 2))
    out = io.BytesIO()
    img.save(out, format="JPEG")
    return out.getvalue()


class FakeHttp:
    def __init__(self, search=FIXTURE, search_status=200, image_status=200, raise_exc=None):
        self.calls = []
        self.search, self.search_status = search, search_status
        self.image_status, self.raise_exc = image_status, raise_exc

    def __call__(self, url, params, timeout_s, headers=None):
        self.calls.append((url, dict(params), dict(headers or {})))
        if self.raise_exc:
            raise self.raise_exc
        if url == mc.GRAPH_URL:
            return self.search_status, "application/json", json.dumps(self.search).encode()
        return self.image_status, "image/jpeg", jpeg()


def client(tmp_path, http=None, cap=100):
    quota = StreetViewQuota(tmp_path / "mapillary.json", monthly_cap=cap,
                            now=lambda: dt.datetime(2026, 11, 26))
    logs = []
    c = mc.MapillaryClient(TOKEN, quota, rate_per_s=1000, http_get=http or FakeHttp(),
                           sleep=lambda s: None, log=logs.append)
    return c, quota, logs


# --- pure helpers ----------------------------------------------------------------


def test_select_picks_nearest_non_pano_along_the_road():
    picked = mc.select_image(FIXTURE["data"], *P, heading=90.0)
    assert picked["id"] == "4"
    # Without a bearing the compass is ignored: the nearest non-pano wins.
    assert mc.select_image(FIXTURE["data"], *P, heading=None)["id"] == "3"
    assert mc.select_image(FIXTURE["data"], *P, heading=90.0, radius_m=2) is None


def test_angle_off_road_counts_both_directions():
    assert mc.angle_off_road(92, 90) == pytest.approx(2)
    assert mc.angle_off_road(271, 90) == pytest.approx(1)     # facing back along the road
    assert mc.angle_off_road(180, 90) == pytest.approx(90)
    assert mc.angle_off_road(5, 355) == pytest.approx(10)


def test_small_helpers():
    assert mc.capture_month(1716800000000) == "2024-05"
    assert mc.capture_month(None) is None
    assert mc.attribution({"creator": {"username": "anna"}}) == "© anna, Mapillary, CC BY-SA 4.0"
    assert mc.attribution({}).startswith("© Mapillary contributor")
    w, s, e, n = map(float, mc.bbox_around(47.5, 19.05, 15).split(","))
    assert w < 19.05 < e and s < 47.5 < n
    assert mc.distance_m((47.5, 19.05), (47.5 + 15 / 111_195, 19.05)) == pytest.approx(15, abs=0.1)


def test_training_view_is_600x400_and_keeps_the_road():
    out = Image.open(io.BytesIO(mc.to_training_view(jpeg(1024, 768))))
    assert out.size == (600, 400)
    # 4:3 -> 3:2 crops from the top: the dark (road) half grows from 50% to 56%.
    dark = sum(1 for y in range(0, 400, 8) if out.getpixel((300, y))[0] < 128)
    assert dark / 50 > 0.53
    wide = Image.open(io.BytesIO(mc.to_training_view(jpeg(2048, 768))))
    assert wide.size == (600, 400)


# --- client ----------------------------------------------------------------------


def test_metadata_searches_with_the_token_in_a_header_only(tmp_path):
    http = FakeHttp()
    c, quota, _ = client(tmp_path, http)
    meta = c.metadata(*P, radius=25, heading=90.0)
    url, params, headers = http.calls[0]
    assert url == mc.GRAPH_URL and headers == {"Authorization": f"OAuth {TOKEN}"}
    assert TOKEN not in json.dumps(params) and params["is_pano"] == "false"
    assert meta["pano_id"] == "mly:4" and meta["source"] == "mapillary"
    assert meta["licence"] == "CC BY-SA 4.0" and "budapest_rider" in meta["copyright"]
    assert meta["date"] == "2024-05" and meta["page_url"].endswith("pKey=4")
    assert quota.used("metadata") == 1 and quota.used() == 0
    # The search box is capped at 15 m even when the collector asks for 25 m.
    w, s, e, n = map(float, params["bbox"].split(","))
    assert (n - s) * 111_195 / 2 == pytest.approx(15, rel=0.01)


def test_image_books_quota_first_and_sends_no_token_to_the_cdn(tmp_path):
    http = FakeHttp()
    c, quota, _ = client(tmp_path, http)
    meta = c.metadata(*P, heading=90.0)
    data = c.image(pano_id=meta["pano_id"], heading=90, pitch=-20, job=JobBudget(5))
    assert Image.open(io.BytesIO(data)).size == (600, 400)
    url, _params, headers = http.calls[1]
    assert url.startswith("https://scontent.example.invalid/") and headers == {}
    assert quota.used() == 1


def test_image_refused_when_the_quota_is_spent(tmp_path):
    http = FakeHttp()
    c, _, _ = client(tmp_path, http, cap=0)
    meta = c.metadata(*P, heading=90.0)
    with pytest.raises(QuotaExceeded):
        c.image(pano_id=meta["pano_id"])
    assert len(http.calls) == 1          # nothing was downloaded


def test_no_match_unknown_id_and_errors(tmp_path):
    c, _, _ = client(tmp_path, FakeHttp(search={"data": []}))
    assert c.metadata(*P, heading=90.0) is None
    with pytest.raises(StreetViewError):
        c.image(pano_id="mly:999")
    for status in (401, 403, 429):
        c, _, _ = client(tmp_path, FakeHttp(search_status=status))
        with pytest.raises(StreetViewFatal):
            c.metadata(*P)
    c, _, _ = client(tmp_path, FakeHttp(search_status=400))
    with pytest.raises(StreetViewError):
        c.metadata(*P)
    no_token = mc.MapillaryClient(None, StreetViewQuota(tmp_path / "q.json", monthly_cap=1))
    with pytest.raises(StreetViewFatal, match="MAPILLARY_TOKEN"):
        no_token.metadata(*P)


def test_network_error_text_never_logged(tmp_path):
    boom = ConnectionError(f"https://graph.mapillary.com/images?access_token={TOKEN}")
    c, _, logs = client(tmp_path, FakeHttp(raise_exc=boom))
    with pytest.raises(StreetViewError) as err:
        c.metadata(*P)
    assert TOKEN not in str(err.value) and all(TOKEN not in line for line in logs)
    assert logs and "ConnectionError" in logs[0]


# --- the unchanged collection loop ---------------------------------------------------


class FakeStore:
    def __init__(self):
        self.saved = []

    def has_pano(self, pano_id):
        return False

    def near_existing(self, lat, lon, radius_m):
        return False

    def save(self, frame, jpeg):
        self.saved.append((frame, jpeg))
        return 1


def run_one(c, store):
    return process_candidate(CANDIDATE, client=c, store=store,
                             index=LineIndex([ROAD]), lines={ROAD.id: ROAD},
                             seen_panos=set(), job=None, radius_m=25)


def test_collector_saves_a_mapillary_frame_with_licence(tmp_path):
    c, _, _ = client(tmp_path)
    store = FakeStore()
    status, frame_id, size = run_one(c, store)
    assert status == SAVED and frame_id == 1 and size > 0
    frame, data = store.saved[0]
    assert frame.pano_id == "mly:4" and frame.capture_date == dt.date(2024, 5, 1)
    assert frame.imagery["source"] == "mapillary" and frame.imagery["licence"] == "CC BY-SA 4.0"
    assert frame.imagery["page_url"].endswith("pKey=4")
    assert Image.open(io.BytesIO(data)).size == (600, 400)


def test_google_user_photosphere_rule_unchanged():
    class Google:
        def metadata(self, lat, lon, *, radius=50, pano_id=None):
            return {"pano_id": "CAoSabc", "lat": lat, "lng": lon, "copyright": "© Someone"}

    assert run_one(Google(), FakeStore())[0] == USER_PANO
