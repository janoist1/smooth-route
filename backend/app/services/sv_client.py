"""The one gentle client for Google Street View (images + metadata).

Every Street View request of the code base goes through here so that three
rules hold everywhere:

1. Budget — an image request is booked on the monthly counter (and the job's
   own cap) BEFORE it is sent (``sv_quota``); over the cap → ``QuotaExceeded``
   and nothing is sent.
2. Gentle traffic — one request at a time at a steady low rate (default
   1 request/second for images and metadata together), exponential back-off
   on transient errors. No bursts, no parallelism: the owner's line may run
   through a VPN that reacts badly to them.
3. Stop on trouble — any quota / billing / key signal (HTTP 403 or 429,
   OVER_QUERY_LIMIT, OVER_DAILY_LIMIT, REQUEST_DENIED) raises
   ``StreetViewFatal`` immediately; callers abort the job instead of retrying.

The API key is sent as a request parameter and never appears in a log line,
an exception message or a stored URL.

Config: ``GOOGLE_SV_RATE_PER_S`` (default 1.0), plus the caps in ``sv_quota``.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

from app.services.sv_quota import JobBudget, StreetViewQuota

IMAGE_URL = "https://maps.googleapis.com/maps/api/streetview"
METADATA_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"

DEFAULT_RATE_PER_S = 1.0
IMAGE_SIZE = "600x400"       # what the model was trained on
DEFAULT_PITCH = -20.0        # camera tilted down at the road

FATAL_HTTP = {403, 429}
FATAL_STATUS = {"OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT", "REQUEST_DENIED"}
NO_PANO_STATUS = {"ZERO_RESULTS", "NOT_FOUND"}

# (status_code, content_type, body_bytes) — or raise for a network problem.
HttpGet = Callable[[str, dict, float], tuple[int, str, bytes]]


class StreetViewFatal(RuntimeError):
    """Quota, billing or key problem: stop the whole job."""


class StreetViewError(RuntimeError):
    """This one request failed for good (bad request, no image); skip it."""


class StreetViewPlaceholder(StreetViewError):
    """The response is the no-imagery card rather than a panorama photo."""


def validate_image(body: bytes) -> None:
    """Reject broken images and the flat grey Street View no-imagery card.

    The card has a nearly uniform neutral background around a small central
    message. Inspect pixels as well as HTTP status: old URLs and cached
    responses can still return that card with HTTP 200. Validation never
    changes the bytes passed to the scorer.
    """
    from io import BytesIO

    from PIL import Image

    try:
        with Image.open(BytesIO(body)) as source:
            source.load()
            sample = source.convert("RGB").resize((64, 64))
    except (OSError, ValueError) as exc:
        raise StreetViewError("Street View image: unreadable image") from exc

    # Mostly uniform borders distinguish the error card from a road with a
    # large grey sky. Allow a small footer, JPEG ringing and warm grey tones.
    pixels = [sample.getpixel((x, y)) for y in range(64) for x in range(64)]
    background = pixels[0]
    if not (180 <= min(background) and max(background) - min(background) <= 12):
        return

    def matches(pixel) -> bool:
        return max(abs(a - b) for a, b in zip(pixel, background)) <= 8

    border = [pixels[y * 64 + x] for y in range(64) for x in range(64)
              if x in (0, 63) or y in (0, 63)]
    if (sum(matches(pixel) for pixel in border) >= len(border) * 0.95
            and sum(matches(pixel) for pixel in pixels) >= len(pixels) * 0.9):
        raise StreetViewPlaceholder("Street View image: no-imagery placeholder")


def rate_from_env(default: float = DEFAULT_RATE_PER_S) -> float:
    try:
        rate = float(os.environ.get("GOOGLE_SV_RATE_PER_S", default))
    except ValueError:
        return default
    return rate if rate > 0 else default


def _requests_get(url: str, params: dict, timeout_s: float) -> tuple[int, str, bytes]:
    import requests  # local import keeps the module importable without it

    resp = requests.get(url, params=params, timeout=timeout_s)
    return resp.status_code, resp.headers.get("content-type", ""), resp.content


class SteadyRate:
    """At most one acquisition per ``1 / rate_per_s`` seconds (thread-safe)."""

    def __init__(self, rate_per_s: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        if rate_per_s <= 0:
            raise ValueError("rate_per_s must be > 0")
        self.interval = 1.0 / rate_per_s
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next = clock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            self._next = slot + self.interval
        if slot > now:
            self._sleep(slot - now)


class StreetViewClient:
    def __init__(
        self,
        api_key: Optional[str],
        quota: StreetViewQuota,
        *,
        rate_per_s: Optional[float] = None,
        retries: int = 4,
        timeout_s: float = 30.0,
        http_get: Optional[HttpGet] = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = print,
    ):
        self._key = api_key
        self.quota = quota
        self.retries = retries
        self.timeout_s = timeout_s
        self._get = http_get or _requests_get
        self._sleep = sleep
        self._log = log
        self._rate = SteadyRate(rate_from_env() if rate_per_s is None else rate_per_s,
                                clock=clock, sleep=sleep)

    # -- shared request loop ------------------------------------------------
    def _request(self, url: str, params: dict, what: str,
                 before_attempt: Optional[Callable[[], object]] = None) -> tuple[int, str, bytes]:
        """GET with the steady rate, back-off on transient errors, and an
        immediate ``StreetViewFatal`` on HTTP 403/429."""
        if not self._key:
            raise StreetViewFatal("GOOGLE_MAPS_API_KEY is not configured")
        last = "no attempt"
        for attempt in range(self.retries + 1):
            if before_attempt is not None:
                before_attempt()          # books the image; may raise QuotaExceeded
            self._rate.wait()
            try:
                status, content_type, body = self._get(
                    url, {**params, "key": self._key}, self.timeout_s)
            except Exception as exc:  # network problem — the message may hold the URL+key
                last = f"network error ({type(exc).__name__})"
            else:
                if status in FATAL_HTTP:
                    raise StreetViewFatal(
                        f"Street View {what}: HTTP {status} — quota, billing or key problem; stopping")
                if status < 500:
                    return status, content_type, body
                last = f"HTTP {status}"
            if attempt < self.retries:
                wait = min(60.0, 2.0 * (2 ** attempt))
                self._log(f"  street view {what}: {last}; retry in {wait:.0f}s")
                self._sleep(wait)
        raise StreetViewError(f"Street View {what} failed after {self.retries + 1} attempts: {last}")

    # -- metadata (free) ----------------------------------------------------
    def metadata(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        *,
        pano_id: Optional[str] = None,
        radius: int = 50,
    ) -> Optional[dict]:
        """Panorama at a location (or by id): ``{pano_id, lat, lng, date}``,
        or None when there is none. Free, but paced like everything else."""
        import json

        # source=outdoor: no indoor panoramas for a location query (it does not
        # exclude user outdoor photospheres; is_google_pano does that).
        params: dict = {"pano": pano_id} if pano_id else {
            "location": f"{lat},{lng}", "radius": radius, "source": "outdoor"}
        status, _ctype, body = self._request(METADATA_URL, params, "metadata")
        self.quota.note_metadata()
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise StreetViewError(f"Street View metadata: unreadable answer (HTTP {status})") from exc
        api_status = data.get("status")
        if api_status == "OK":
            location = data.get("location") or {}
            return {
                "pano_id": data.get("pano_id"),
                "lat": location.get("lat"),
                "lng": location.get("lng"),
                "date": data.get("date"),
                # "© Google" for Google's own car imagery; a person's name for
                # user-contributed photospheres (see is_google_pano).
                **({"copyright": data["copyright"]} if data.get("copyright") else {}),
            }
        if api_status in NO_PANO_STATUS:
            return None
        if api_status in FATAL_STATUS:
            raise StreetViewFatal(
                f"Street View metadata: {api_status} — quota, billing or key problem; stopping")
        raise StreetViewError(f"Street View metadata: status {api_status}")

    # -- images (billed) ----------------------------------------------------
    def _image_request(self, url: str, params: dict, job: Optional[JobBudget]) -> bytes:
        status, content_type, body = self._request(
            # Enforce this for every entry point, including legacy queued URLs
            # that omit it or explicitly ask for the grey placeholder.
            url, {**params, "return_error_code": "true"}, "image",
            # Every ATTEMPT is booked: a request that timed out on our side may
            # still have been billed, so the counter must never run behind.
            before_attempt=lambda: self.quota.reserve(1, job),
        )
        if status == 200 and content_type.startswith("image") and body:
            validate_image(body)
            return body
        text = body[:200].decode("utf-8", "replace").lower() if body else ""
        if any(word in text for word in ("quota", "billing", "exceeded", "not authorized")):
            raise StreetViewFatal(
                f"Street View image: HTTP {status} with a quota/billing message; stopping")
        raise StreetViewError(f"Street View image: HTTP {status} ({content_type or 'no content type'})")

    def image(
        self,
        *,
        heading: float,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        pano_id: Optional[str] = None,
        pitch: float = DEFAULT_PITCH,
        size: str = IMAGE_SIZE,
        job: Optional[JobBudget] = None,
    ) -> bytes:
        """One Street View Static image (JPEG bytes). Raises ``QuotaExceeded``
        before sending when over a cap, ``StreetViewFatal`` on a quota/billing
        signal, ``StreetViewError`` when this image cannot be had."""
        params: dict = {"size": size, "heading": heading, "pitch": pitch,
                        # 404 instead of a grey "no imagery" picture
                        "return_error_code": "true"}
        if pano_id:
            params["pano"] = pano_id
        else:
            params["location"] = f"{lat},{lng}"
            params["source"] = "outdoor"
        return self._image_request(IMAGE_URL, params, job)

    def image_from_url(self, url: str, job: Optional[JobBudget] = None,
                       *, pano_id: Optional[str] = None) -> bytes:
        """Fetch a previously built Street View Static URL (rows queued by the
        route collector store one) through the same budget and pacing. The key
        inside the stored URL is dropped and re-added from the config.
        ``pano_id`` pins legacy location URLs to their stored panorama while
        preserving camera settings; it takes precedence over URL selectors."""
        from urllib.parse import parse_qsl, urlsplit

        parts = urlsplit(url)
        if parts.netloc != "maps.googleapis.com" or not parts.path.startswith("/maps/api/streetview"):
            raise StreetViewError("not a Street View Static URL")
        params = {k: v for k, v in parse_qsl(parts.query) if k != "key"}
        if pano_id:
            for selector in ("location", "radius", "source"):
                params.pop(selector, None)
            params["pano"] = pano_id
        return self._image_request(IMAGE_URL, params, job)


_default_client: Optional[StreetViewClient] = None


# User-contributed photospheres have ids like "CAoSF0NJSE0w…" (a wrapped photo
# id) and a person's name as copyright; Google's car imagery says "© 2026 Google".
USER_PANO_ID_PREFIX = "CAoS"


def is_google_pano(meta: Optional[dict]) -> bool:
    """True for Google's own Street View imagery (road-level car capture).

    The copyright decides when present (it must name Google); without it, a
    user-photosphere id pattern counts as not Google's."""
    if not meta:
        return False
    copyright_ = meta.get("copyright")
    if copyright_:
        return "google" in copyright_.lower()
    return not str(meta.get("pano_id") or "").startswith(USER_PANO_ID_PREFIX)


def default_client() -> StreetViewClient:
    """Process-wide client on the shared quota counter and the configured key."""
    global _default_client
    if _default_client is None:
        from app.core.config import settings
        from app.services.sv_quota import default_quota

        _default_client = StreetViewClient(settings.GOOGLE_MAPS_API_KEY, default_quota())
    return _default_client
