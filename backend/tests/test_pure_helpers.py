"""Unit tests for small pure modules CI never exercised (T-18 coverage pass).
No DB, no torch, no network: Google and Street View are faked."""
import threading
from types import SimpleNamespace

import pytest

# --- core/security_headers --------------------------------------------------


def _app_with_headers(extra_headers=()):
    from app.core.security_headers import SecurityHeadersMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"), *extra_headers]})
        await send({"type": "http.response.body", "body": b"{}"})

    return SecurityHeadersMiddleware(app)


async def _call(asgi, scope_type="http"):
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    await asgi({"type": scope_type, "path": "/", "headers": []}, receive, send)
    return sent


def test_security_headers_added_to_every_response():
    import asyncio

    from app.core.security_headers import SECURITY_HEADERS

    start = asyncio.run(_call(_app_with_headers()))[0]
    headers = dict(start["headers"])
    for name, value in SECURITY_HEADERS.items():
        assert headers[name.encode()] == value.encode()
    assert headers[b"content-type"] == b"application/json"


def test_security_headers_keep_a_value_the_app_set():
    import asyncio

    start = asyncio.run(_call(_app_with_headers([(b"X-Frame-Options", b"SAMEORIGIN")])))[0]
    names = [k.lower() for k, _ in start["headers"]]
    assert names.count(b"x-frame-options") == 1
    assert (b"X-Frame-Options", b"SAMEORIGIN") in start["headers"]


def test_security_headers_pass_non_http_scopes_through():
    import asyncio

    from app.core.security_headers import SecurityHeadersMiddleware

    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(_call(SecurityHeadersMiddleware(app), scope_type="lifespan"))
    assert seen == ["lifespan"]


# --- core/paths ---------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", ".", "..", "../etc/passwd", "a/b.jpg", "/abs.jpg"])
def test_image_path_rejects_anything_but_a_bare_filename(bad):
    from app.core.paths import image_path

    with pytest.raises(ValueError):
        image_path(bad)


def test_paths_resolve_under_the_data_dir(monkeypatch, tmp_path):
    from app.core import paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    assert paths.image_path("a.jpg") == tmp_path / "images" / "a.jpg"
    assert paths.data_path("static", "x") == tmp_path / "static" / "x"
    assert paths.resolve_stored_image("https://maps.googleapis.com/x.jpg") is None
    assert paths.resolve_stored_image("images/missing.jpg") is None
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "a.jpg").write_bytes(b"jpg")
    # A stored URL with a directory part resolves by its file name only.
    assert paths.resolve_stored_image("/old/tree/a.jpg") == tmp_path / "images" / "a.jpg"


# --- services/job_runner ---------------------------------------------------------


def test_threaded_task_runs_the_target():
    from app.services.job_runner import job_runner

    done = threading.Event()
    thread = job_runner.run_threaded_task(done.set)
    thread.join(5)
    assert done.is_set() and thread.daemon


def _noop():
    pass


def test_background_task_runs_in_a_process():
    from app.services.job_runner import job_runner

    process = job_runner.run_background_task(_noop)
    process.join(30)
    assert process.exitcode == 0


# --- services/google_maps (fake client: no network) --------------------------


def _svc(client=None):
    from app.services.google_maps import GoogleMapsService

    svc = GoogleMapsService.__new__(GoogleMapsService)
    svc.client = client
    return svc


ENCODED = "_p~iF~ps|U_ulLnnqC"  # (38.5, -120.2) -> (40.7, -120.95)


def test_get_route_decodes_the_first_route():
    calls = []

    def directions(o, d, mode, alternatives, **kwargs):
        calls.append((o, d, alternatives))
        return [{"overview_polyline": {"points": ENCODED}}]

    points = _svc(SimpleNamespace(directions=directions)).get_route("a", "b")
    assert calls == [("a", "b", False)]
    assert points[0] == {"lat": pytest.approx(38.5), "lng": pytest.approx(-120.2)}
    assert len(points) == 2


def test_get_route_retries_with_geocoded_inputs():
    calls = []

    def directions(o, d, mode, alternatives, **kwargs):
        calls.append((o, d))
        return [] if o == "town" else [{"overview_polyline": {"points": ENCODED}}]

    def geocode(address):
        return [{"geometry": {"location": {"lat": 47.5, "lng": 19.0}}}]

    svc = _svc(SimpleNamespace(directions=directions, geocode=geocode))
    assert len(svc.get_route("town", "village")) == 2
    assert calls == [("town", "village"), ("47.5,19.0", "47.5,19.0")]


def test_get_route_without_key_raises():
    with pytest.raises(ValueError, match="not configured"):
        _svc(None).get_route("a", "b")
    with pytest.raises(ValueError, match="not configured"):
        _svc(None).get_routes("a", "b")
    assert _svc(None).geocode("x") is None


def test_geocode_variants():
    assert _svc(SimpleNamespace(geocode=lambda a: [])).geocode("x") is None

    def boom(a):
        raise RuntimeError("down")

    assert _svc(SimpleNamespace(geocode=boom)).geocode("x") is None


def test_geometry_helpers():
    svc = _svc()
    assert svc.decode_polyline(ENCODED)[0] == (pytest.approx(38.5), pytest.approx(-120.2))
    # 0.001 deg of latitude ~ 111 m
    assert svc._haversine_distance((47.0, 19.0), (47.001, 19.0)) == pytest.approx(111.2, abs=0.5)
    assert svc.calculate_heading((47.0, 19.0), (47.1, 19.0)) == pytest.approx(0.0, abs=1e-6)
    assert svc.calculate_heading((47.0, 19.0), (47.0, 19.1)) == pytest.approx(90.0, abs=0.1)
    assert svc.calculate_heading((47.0, 19.0), (46.9, 19.0)) == pytest.approx(180.0, abs=1e-6)
    assert svc.interpolate_points([]) == []
    pts = svc.interpolate_points([(47.0, 19.0), (47.001, 19.0)], interval_meters=10)
    assert pts[0] == (47.0, 19.0) and pts[-1] == (47.001, 19.0)
    gaps = [svc._haversine_distance(a, b) for a, b in zip(pts, pts[1:])]
    assert max(gaps) <= 10.0 and len(pts) == 13


def test_street_view_url_never_carries_the_key():
    url = _svc().get_street_view_url(47.5, 19.05, heading=90, pitch=-20)
    assert url.startswith("https://maps.googleapis.com/maps/api/streetview?")
    assert "location=47.5,19.05" in url and "heading=90" in url and "pitch=-20" in url
    assert "key=" not in url
    assert "return_error_code=true" in url


def test_street_view_metadata_snaps_and_dedups(monkeypatch):
    svc = _svc()
    metas = iter([
        {"pano_id": "p1", "lat": 47.50001, "lng": 19.0, "date": "2021-06"},
        {"pano_id": "p1", "lat": 47.50001, "lng": 19.0, "date": "2021-06"},  # same pano
        None,                                                               # no pano
        {"pano_id": "p2", "lat": 47.503, "lng": 19.0, "date": None},
    ])
    monkeypatch.setattr(svc, "get_panorama_metadata", lambda lat, lng: next(metas))
    out = svc.generate_street_view_metadata(
        [(47.5, 19.0), (47.501, 19.0), (47.502, 19.0), (47.503, 19.0)])
    assert [m["pano_id"] for m in out] == ["p1", "p2"]
    assert out[0]["latitude"] == 47.50001 and out[0]["heading"] == pytest.approx(0.0, abs=1e-6)
    assert out[-1]["heading"] == pytest.approx(0.0, abs=1e-6)  # last point: from previous
    assert "key=" not in out[0]["image_url"]
    from urllib.parse import parse_qs, urlsplit

    for row in out:
        params = parse_qs(urlsplit(row["image_url"]).query)
        assert params["pano"] == [row["pano_id"]]
        assert params["return_error_code"] == ["true"]
        assert "location" not in params
    assert out[0]["capture_date"] is not None and out[1]["capture_date"] is None


def test_panorama_metadata_without_key_makes_no_call(monkeypatch):
    from app.services import google_maps

    monkeypatch.setattr(google_maps.settings, "GOOGLE_MAPS_API_KEY", None)
    assert _svc().get_panorama_metadata(47.5, 19.0) is None


# --- Vercel entry point --------------------------------------------------------


def test_vercel_entry_exposes_the_asgi_app():
    """@vercel/python serves the module-level name `app` of api/index.py; a lint
    auto-fix once deleted the import as "unused". Checked by AST: importing
    app.main in-process would run startup side effects."""
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parents[1] / "api" / "index.py").read_text())
    imports = [(n.module, a.name, a.asname) for n in tree.body if isinstance(n, ast.ImportFrom)
               for a in n.names]
    assert ("app.main", "app", None) in imports
