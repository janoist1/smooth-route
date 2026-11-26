"""Smoke-check a public read-only API deploy with a handful of normal reads.

Usage (from backend/; stdlib only, any Python 3.10+):
    python3 scripts/smoke_public_api.py https://smooth-route-api.vercel.app \
        --origin https://smooth-route-chi.vercel.app
    python3 scripts/smoke_public_api.py http://127.0.0.1:8006     # rehearsal

About 15 requests in total. Never calls getRoute, so it uses no Google quota.
Safe to run against production. It is not a load test: do not loop it.

Exit code 0 means every check passed. Each check prints PASS or FAIL.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request

# Budapest centre: the densest published area, small enough for zoom 14.
DEFAULT_BBOX = [19.0, 47.45, 19.15, 47.55]
DEFAULT_ZOOM = 14
# Anything that looks like a Google key in any response body is a failure.
KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{20,}|[?&]key=[0-9A-Za-z_\-]{10,}")
REQUIRED_HEADERS = ("x-content-type-options", "x-frame-options", "referrer-policy")

POINTS = """query($bbox: [Float!], $limit: Int) {
  points(bbox: $bbox, limit: $limit) {
    id latitude longitude rqiScore dinoRqiScore rqiSource captureDate
  }
}"""
POINT_DETAIL = """query($id: Int!) {
  point(id: $id) { id imageUrl streetViewUrl dinoRqiScore captureDate }
}"""
SEGMENTS = """query($bbox: [Float!]!, $zoom: Int!) {
  roadSegments(bbox: $bbox, zoom: $zoom) {
    id path rqi score pBad confidence confidenceLevel nImages lengthM
  }
}"""
ROUTE_QUALITY = """query($path: [[Float!]!]!) {
  routeQuality(path: $path) { totalLengthM coveredLengthM lengthByRqi meanScore }
}"""
GRID = """query($zoom: Int!, $bbox: [Float!]) { roadQualityGrid(zoom: $zoom, bbox: $bbox) }"""


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def scale_direction(segments: list[dict]) -> str:
    """'higher_is_better' when the low classes carry the higher P(bad road).

    pBad means "bad road" on either numbering, so it gives away the direction
    of rqi. This catches a flip that ran twice or not at all (data vs. code).
    """
    low = mean([s["pBad"] for s in segments if s["rqi"] <= 2 and s["pBad"] is not None])
    high = mean([s["pBad"] for s in segments if s["rqi"] >= 4 and s["pBad"] is not None])
    if low is None or high is None:
        return "unknown (need segments rated <= 2 and >= 4)"
    return "higher_is_better" if low > high else "lower_is_better"


class Smoke:
    def __init__(self, base: str, origin: str | None, timeout: float):
        self.base = base.rstrip("/")
        self.origin = origin
        self.timeout = timeout
        self.failures: list[str] = []

    # --- transport ---------------------------------------------------------

    def request(self, method: str, path: str, body: dict | None = None,
                headers: dict | None = None) -> tuple[int, dict, str]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("User-Agent", "smooth-route-smoke/1")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status, hdrs, text = resp.status, resp.headers, resp.read().decode()
        except urllib.error.HTTPError as exc:
            status, hdrs, text = exc.code, exc.headers, exc.read().decode(errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            self.fail(f"{method} {path}: no response ({reason})")
            return 0, {}, ""
        lowered = {k.lower(): v for k, v in hdrs.items()}
        if KEY_PATTERN.search(text):
            self.fail(f"{method} {path}: response contains something that looks like an API key")
        return status, lowered, text

    def gql(self, query: str, variables: dict | None = None) -> dict:
        headers = {"Origin": self.origin} if self.origin else None
        status, _, text = self.request(
            "POST", "/graphql", {"query": query, "variables": variables or {}}, headers)
        try:
            return {"_status": status, **json.loads(text)}
        except json.JSONDecodeError:
            return {"_status": status, "errors": [{"message": text[:200]}]}

    # --- reporting ---------------------------------------------------------

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        print(f"{'PASS' if ok else 'FAIL'}  {label}{'  — ' + detail if detail else ''}")
        if not ok:
            self.failures.append(label)
        return ok

    def fail(self, label: str) -> None:
        self.check(False, label)

    # --- checks ------------------------------------------------------------

    def run(self, bbox: list[float], zoom: int) -> int:
        status, headers, _ = self.request("GET", "/health")
        self.check(status == 200, "GET /health is 200", str(status))
        missing = [h for h in REQUIRED_HEADERS if h not in headers]
        self.check(not missing, "security headers present", ", ".join(missing))

        for path in ("/api/v1/config", "/api/v1/points", "/docs", "/openapi.json"):
            status, _, _ = self.request("GET", path)
            self.check(status == 404, f"GET {path} is not served", str(status))

        status, _, _ = self.request("GET", "/graphql?query=%7B__typename%7D")
        self.check(status in (400, 404, 405), "GraphQL over GET is refused", str(status))

        res = self.gql("{ __schema { types { name } } }")
        self.check(bool(res.get("errors")) and not res.get("data"),
                   "introspection is off")
        res = self.gql("{ config { googleMapsApiKey } }")
        self.check(bool(res.get("errors")), "config query is refused")
        res = self.gql('mutation { deletePoint(id: 1) }')
        self.check(bool(res.get("errors")) and not res.get("data"),
                   "mutations are refused")

        if self.origin:
            status, headers, _ = self.request("OPTIONS", "/graphql", headers={
                "Origin": self.origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"})
            self.check(headers.get("access-control-allow-origin") == self.origin,
                       "CORS preflight allows the frontend origin", str(status))
        status, headers, _ = self.request("OPTIONS", "/graphql", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.check("access-control-allow-origin" not in headers,
                   "CORS preflight refuses a foreign origin")

        res = self.gql(POINTS, {"bbox": bbox, "limit": 50})
        points = (res.get("data") or {}).get("points") or []
        self.check(bool(points) and not res.get("errors"), "points in bbox",
                   f"{len(points)} rows")
        bad = [p["id"] for p in points
               if p["dinoRqiScore"] is not None and not 1 <= p["dinoRqiScore"] <= 5]
        self.check(not bad, "point RQI values are on the 1-5 scale", str(bad[:5]))
        dated = sum(1 for p in points if p.get("captureDate"))
        self.check(dated > 0, "points carry captureDate (migration 0004)",
                   f"{dated}/{len(points)}")

        if points:
            res = self.gql(POINT_DETAIL, {"id": points[0]["id"]})
            point = (res.get("data") or {}).get("point") or {}
            self.check(point.get("imageUrl") is None and bool(point.get("streetViewUrl")),
                       "point detail: no stored image URL, Street View link present")

        res = self.gql(SEGMENTS, {"bbox": bbox, "zoom": zoom})
        segments = (res.get("data") or {}).get("roadSegments") or []
        self.check(bool(segments) and not res.get("errors"),
                   "roadSegments in bbox (migration 0005 + publish)",
                   f"{len(segments)} segments" + (f"; {res['errors'][0]['message']}"
                                                  if res.get("errors") else ""))
        rated = [s for s in segments if s["rqi"] is not None]
        bad = [s["id"] for s in rated if not 1 <= s["rqi"] <= 5]
        self.check(bool(rated) and not bad, "segment RQI values are on the 1-5 scale",
                   f"{len(rated)} rated")
        direction = scale_direction(rated)
        self.check(direction != "lower_is_better",
                   "scale direction: 5 = best (bad roads have the higher pBad)",
                   direction)

        res = self.gql(GRID, {"zoom": zoom, "bbox": bbox})
        self.check(not res.get("errors") and (res.get("data") or {}).get("roadQualityGrid")
                   is not None, "roadQualityGrid")

        if rated:
            # Follow one rated segment: the route must be (almost) fully covered.
            longest = max(rated, key=lambda s: s["lengthM"])
            res = self.gql(ROUTE_QUALITY, {"path": longest["path"]})
            rq = (res.get("data") or {}).get("routeQuality") or {}
            total, covered = rq.get("totalLengthM") or 0, rq.get("coveredLengthM") or 0
            self.check(total > 0 and covered >= 0.5 * total and not res.get("errors"),
                       "routeQuality along a rated segment",
                       f"covered {covered:.0f} of {total:.0f} m")

        res = self.gql(ROUTE_QUALITY, {"path": [[47.5, 19.0]] * 20001})
        self.check(bool(res.get("errors")) and not res.get("data"),
                   "routeQuality refuses an oversized path")

        print(f"\n{len(self.failures)} check(s) failed" if self.failures
              else "\nall checks passed")
        return 1 if self.failures else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base_url", help="API base URL, e.g. https://smooth-route-api.vercel.app")
    ap.add_argument("--origin", help="frontend origin expected in CORS (e.g. https://simaut.hu)")
    ap.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX,
                    metavar=("MIN_LNG", "MIN_LAT", "MAX_LNG", "MAX_LAT"))
    ap.add_argument("--zoom", type=int, default=DEFAULT_ZOOM)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()
    sys.exit(Smoke(args.base_url, args.origin, args.timeout).run(args.bbox, args.zoom))


if __name__ == "__main__":
    main()
