"""Mapillary imagery behind the Street View collector's interface (prototype).

Why: Google's terms may forbid ML on Street View content (docs/LANDSCAPE.md);
Mapillary images are CC BY-SA 4.0. Licence, attribution and the model caveats
are in docs/IMAGERY_SOURCES.md.

``MapillaryClient`` has the two calls ``network_collector.process_candidate``
makes on ``StreetViewClient`` (``metadata`` + ``image``), with the same return
shape and the same error classes, so the collection loop, ``DbFrameStore`` and
the resume log work unchanged:

* ``metadata(lat, lng, radius=, heading=)``: one Graph API v4 image search in a
  small bbox around the point. It picks the nearest NON-panorama image within
  ``MAX_RADIUS_M`` whose compass angle is within ``MAX_ANGLE_DEG`` of the road
  bearing. Panoramas are skipped: they would need an equirectangular → perspective
  reprojection; see the doc.
* ``image(pano_id=, ...)``: books one image on the Mapillary counter (and the
  job budget) BEFORE downloading ``thumb_1024_url``, then turns it into our
  600×400 frame (``to_training_view``).

Ids are prefixed ``mly:`` so they never collide with Google pano ids in
``street_view_images.pano_id`` (the duplicate check).

Token: ``MAPILLARY_TOKEN`` (env), sent in the ``Authorization`` header, never
in a URL, a log line or an exception message. Rate: ``MAPILLARY_RATE_PER_S``
(default 2/s, steady, one request at a time). Monthly image cap:
``MAPILLARY_MONTHLY_CAP`` (default 20 000) on ``data/quota/mapillary.json``.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import math
import os
from typing import Callable, Optional

from app.services.sv_client import (
    SteadyRate,
    StreetViewError,
    StreetViewFatal,
)
from app.services.sv_quota import JobBudget, StreetViewQuota, cap_from_env

GRAPH_URL = "https://graph.mapillary.com/images"
SOURCE = "mapillary"
ID_PREFIX = "mly:"
LICENCE = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
FIELDS = ("id,captured_at,compass_angle,computed_compass_angle,geometry,"
          "computed_geometry,is_pano,camera_type,creator,thumb_1024_url")

MAX_RADIUS_M = 15.0       # nearest image must be this close to the planned point
MAX_ANGLE_DEG = 45.0      # camera direction vs road bearing (either direction of travel)
SEARCH_LIMIT = 50
DEFAULT_RATE_PER_S = 2.0
DEFAULT_MONTHLY_CAP = 20_000
VIEW_SIZE = (600, 400)    # what the model was trained on
FATAL_HTTP = {401, 403, 429}


def _requests_get(url: str, params: dict, timeout_s: float,
                  headers: Optional[dict] = None) -> tuple[int, str, bytes]:
    import requests

    resp = requests.get(url, params=params, headers=headers or {}, timeout=timeout_s)
    return resp.status_code, resp.headers.get("content-type", ""), resp.content


# --- pure helpers --------------------------------------------------------------


def bbox_around(lat: float, lng: float, radius_m: float) -> str:
    """"minLon,minLat,maxLon,maxLat" covering radius_m around the point."""
    dlat = radius_m / 111_320.0
    dlng = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    return f"{lng - dlng:.6f},{lat - dlat:.6f},{lng + dlng:.6f},{lat + dlat:.6f}"


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def angle_off_road(compass: float, road_bearing: float) -> float:
    """Degrees between the camera and the road axis, either direction (0..90)."""
    d = abs((compass - road_bearing + 180.0) % 360.0 - 180.0)
    return min(d, 180.0 - d)


def capture_month(captured_at_ms) -> Optional[str]:
    """Mapillary ``captured_at`` (epoch ms) -> "YYYY-MM" like Street View's date."""
    if captured_at_ms is None:
        return None
    moment = dt.datetime.fromtimestamp(int(captured_at_ms) / 1000, tz=dt.timezone.utc)
    return moment.strftime("%Y-%m")


def attribution(image: dict) -> str:
    creator = (image.get("creator") or {}).get("username") or "Mapillary contributor"
    return f"© {creator}, Mapillary, {LICENCE}"


def select_image(images: list[dict], lat: float, lng: float,
                 heading: Optional[float], radius_m: float = MAX_RADIUS_M,
                 max_angle_deg: float = MAX_ANGLE_DEG) -> Optional[dict]:
    """Nearest usable image: not a panorama, within radius, facing along the road."""
    best, best_d = None, None
    for img in images:
        if img.get("is_pano") or img.get("camera_type") in ("spherical", "equirectangular"):
            continue
        geom = img.get("computed_geometry") or img.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 2 or not img.get("thumb_1024_url"):
            continue
        d = distance_m((lat, lng), (coords[1], coords[0]))
        if d > radius_m:
            continue
        compass = img.get("computed_compass_angle", img.get("compass_angle"))
        if heading is not None:
            if compass is None or angle_off_road(float(compass), heading) > max_angle_deg:
                continue
        if best_d is None or d < best_d:
            best, best_d = img, d
    return best


def to_training_view(jpeg: bytes, size: tuple[int, int] = VIEW_SIZE) -> bytes:
    """Mapillary thumbnail -> our frame shape: 3:2, road-weighted, 600×400.

    Our Street View frames look 20° down at the road. A level phone or dashcam
    image puts the horizon mid-frame, so the crop keeps the BOTTOM of the
    picture (drops sky first) at 3:2 before resizing. It is an approximation of
    the pitch, not a reprojection.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    w, h = img.size
    target = size[0] / size[1]
    if w / h > target:              # too wide: trim both sides evenly
        new_w = round(h * target)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:                           # too tall: keep the bottom (road), drop the sky
        new_h = round(w / target)
        img = img.crop((0, h - new_h, w, h))
    out = io.BytesIO()
    img.resize(size, Image.BICUBIC).save(out, format="JPEG", quality=90)
    return out.getvalue()


# --- client --------------------------------------------------------------------


def rate_from_env(default: float = DEFAULT_RATE_PER_S) -> float:
    try:
        rate = float(os.environ.get("MAPILLARY_RATE_PER_S", default))
    except ValueError:
        return default
    return rate if rate > 0 else default


def default_quota(data_dir) -> StreetViewQuota:
    """Own monthly counter, separate from Google's (data/quota/mapillary.json)."""
    from pathlib import Path

    return StreetViewQuota(Path(data_dir) / "quota" / "mapillary.json",
                           monthly_cap=cap_from_env("MAPILLARY_MONTHLY_CAP", DEFAULT_MONTHLY_CAP))


class MapillaryClient:
    """``StreetViewClient``-compatible ``metadata`` / ``image`` for Mapillary."""

    source = SOURCE
    wants_heading = True   # process_candidate passes the road bearing to metadata()

    def __init__(self, token: Optional[str], quota: StreetViewQuota, *,
                 rate_per_s: Optional[float] = None, retries: int = 3,
                 timeout_s: float = 30.0, http_get: Optional[Callable] = None,
                 sleep: Callable[[float], None] = __import__("time").sleep,
                 clock: Callable[[], float] = __import__("time").monotonic,
                 log: Callable[[str], None] = print):
        self._token = token
        self.quota = quota
        self.retries = retries
        self.timeout_s = timeout_s
        # (url, params, timeout_s, headers) -> (status, content_type, body)
        self._get: Callable[..., tuple[int, str, bytes]] = http_get or _requests_get
        self._sleep = sleep
        self._log = log
        self._rate = SteadyRate(rate_from_env() if rate_per_s is None else rate_per_s,
                                clock=clock, sleep=sleep)
        self._thumbs: dict[str, str] = {}   # mly:id -> signed thumbnail URL (memory only)

    def _request(self, url: str, params: dict, what: str, *, auth: bool,
                 before_attempt: Optional[Callable[[], object]] = None):
        if not self._token:
            raise StreetViewFatal("MAPILLARY_TOKEN is not configured")
        headers = {"Authorization": f"OAuth {self._token}"} if auth else None
        last = "no attempt"
        for attempt in range(self.retries + 1):
            if before_attempt is not None:
                before_attempt()
            self._rate.wait()
            try:
                status, ctype, body = self._get(url, params, self.timeout_s, headers)
            except Exception as exc:  # the message may hold the URL: log the type only
                last = f"network error ({type(exc).__name__})"
            else:
                if status in FATAL_HTTP:
                    raise StreetViewFatal(
                        f"Mapillary {what}: HTTP {status}: token, rate or quota problem; stopping")
                if status < 500:
                    return status, ctype, body
                last = f"HTTP {status}"
            if attempt < self.retries:
                wait = min(60.0, 2.0 * (2 ** attempt))
                self._log(f"  mapillary {what}: {last}; retry in {wait:.0f}s")
                self._sleep(wait)
        raise StreetViewError(f"Mapillary {what} failed after {self.retries + 1} attempts: {last}")

    def metadata(self, lat: float, lng: float, *, radius: float = MAX_RADIUS_M,
                 heading: Optional[float] = None, pano_id: Optional[str] = None) -> Optional[dict]:
        """Best image near the point as ``{pano_id, lat, lng, date, source,
        copyright, licence, ...}`` (sv_client's shape plus licence fields), or None."""
        if pano_id is not None:
            raise StreetViewError("lookup by id is not supported for Mapillary")
        r = min(float(radius), MAX_RADIUS_M)
        status, _ctype, body = self._request(GRAPH_URL, {
            "fields": FIELDS, "bbox": bbox_around(lat, lng, r),
            "is_pano": "false", "limit": SEARCH_LIMIT}, "search", auth=True)
        self.quota.note_metadata()
        if status != 200:
            raise StreetViewError(f"Mapillary search: HTTP {status}")
        try:
            images = json.loads(body).get("data") or []
        except (ValueError, AttributeError) as exc:
            raise StreetViewError("Mapillary search: unreadable response") from exc
        img = select_image(images, lat, lng, heading, r)
        if img is None:
            return None
        coords = (img.get("computed_geometry") or img.get("geometry") or {})["coordinates"]
        key = ID_PREFIX + str(img["id"])
        self._thumbs[key] = img["thumb_1024_url"]
        return {
            "pano_id": key, "lat": coords[1], "lng": coords[0],
            "date": capture_month(img.get("captured_at")),
            "source": SOURCE, "copyright": attribution(img),
            "licence": LICENCE, "licence_url": LICENCE_URL,
            "mapillary_id": str(img["id"]),
            "page_url": f"https://www.mapillary.com/app/?pKey={img['id']}",
            "compass_angle": img.get("computed_compass_angle", img.get("compass_angle")),
        }

    def image(self, *, pano_id: str, heading: Optional[float] = None,
              pitch: Optional[float] = None, job: Optional[JobBudget] = None,
              lat: Optional[float] = None, lng: Optional[float] = None) -> bytes:
        """The image found by ``metadata`` as a 600×400 JPEG (books quota first)."""
        url = self._thumbs.get(pano_id)
        if url is None:
            raise StreetViewError("call metadata() first: no thumbnail for this id")
        status, ctype, body = self._request(
            url, {}, "image", auth=False,   # signed CDN URL: no token sent there
            before_attempt=lambda: self.quota.reserve(1, job))
        if status != 200 or not body[:2] == b"\xff\xd8":
            raise StreetViewError(f"Mapillary image: HTTP {status} {ctype}")
        return to_training_view(body)


def imagery_metadata(meta: dict) -> Optional[dict]:
    """What to keep on the frame row (``analysis_metadata.imagery``) for a
    non-Google source: licence + attribution duties travel with the frame."""
    if meta.get("source") != SOURCE:
        return None
    return {k: meta[k] for k in ("source", "copyright", "licence", "licence_url",
                                 "mapillary_id", "page_url") if k in meta}
