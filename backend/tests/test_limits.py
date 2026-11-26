"""Request limits for the public GraphQL API (app/graphql/limits.py).

DB-free: rejected requests never reach a resolver, accepted ones are checked
with check_operation() (no execution) or against a probe schema.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import strawberry
from graphql import parse

from app.graphql import limits
from app.graphql.permissions import IsAdmin
from app.graphql.limits import (
    InputLimitError,
    check_operation,
    max_bbox_area_for_zoom,
    schema_extensions,
    validate_bbox,
    validate_grid_args,
    validate_points_args,
    validate_route_endpoints,
    validate_route_path,
    validate_segments_args,
)

BUDAPEST_BBOX = [19.0, 47.4, 19.3, 47.6]  # zoom ~14 viewport is far smaller
BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_GQL = BACKEND_DIR.parent / "frontend/src/modules/graphql/generated/gql.ts"  # noqa: E501


@pytest.fixture(scope="module")
def read_schema():
    from app.graphql.schema import read_schema

    return read_schema


@pytest.fixture(scope="module")
def full_schema():
    from app.graphql.schema import schema

    return schema


def errors_of(schema, query, variables=None):
    result = schema.execute_sync(
        query, variable_values=variables, context_value={"identity": None}
    )
    assert result.data is None, "a rejected request must not execute"
    return [e.message for e in result.errors]


# --- Pure validators -------------------------------------------------------------


class TestBbox:
    def test_none_allowed_unless_required(self):
        assert validate_bbox(None) is None
        with pytest.raises(InputLimitError):
            validate_bbox(None, required=True)

    @pytest.mark.parametrize(
        "bbox", [[1, 2, 3], [1, 2, 3, 4, 5], [], [19.3, 47.4, 19.0, 47.6], "1,2,3,4"]
    )
    def test_malformed_rejected(self, bbox):
        with pytest.raises(InputLimitError):
            validate_bbox(bbox)

    def test_zoomed_out_viewport_may_exceed_world(self):
        assert validate_bbox([-500, -100, 500, 100]) == (-500, -100, 500, 100)
        assert limits.bbox_area_deg2([-500, -100, 500, 100]) == 360 * 180


class TestPoints:
    def test_frontend_request_ok(self):
        box, limit, offset = validate_points_args(BUDAPEST_BBOX, 20_000, 0)
        assert box == tuple(BUDAPEST_BBOX) and limit == 20_000 and offset == 0

    def test_defaults_ok(self):
        assert validate_points_args(None, None, None) == (None, 100, 0)

    @pytest.mark.parametrize(
        "bbox,limit,offset",
        [
            (BUDAPEST_BBOX, 20_001, 0),  # over the map cap
            (None, 1_001, 0),  # whole table without a bbox
            (BUDAPEST_BBOX, -1, 0),
            (BUDAPEST_BBOX, 10, -5),  # used to surface raw SQL in the error
            (BUDAPEST_BBOX, 10, 10_000_000),
            ([16.0, 45.7, 23.0, 48.6], 20_000, 0),  # all of Hungary: use the grid
            ([1, 2, 3], 20_000, 0),  # used to be ignored -> whole table
        ],
    )
    def test_abuse_rejected(self, bbox, limit, offset):
        with pytest.raises(InputLimitError):
            validate_points_args(bbox, limit, offset)


class TestViewport:
    @pytest.mark.parametrize("zoom", range(0, 14))
    def test_frontend_grid_viewports_ok(self, zoom):
        # What the router saga sends: window size around the centre, 4K screen.
        deg_per_px = 360 / (2**zoom * 256)
        dlng, dlat = 1920 * deg_per_px, 1080 * deg_per_px
        bbox = [19.0 - dlng, 47.5 - dlat, 19.0 + dlng, 47.5 + dlat]
        assert validate_grid_args(zoom, bbox)[0] == zoom

    def test_whole_world_only_when_zoomed_out(self):
        assert validate_grid_args(4, None) == (4, None)
        with pytest.raises(InputLimitError):
            validate_grid_args(22, None)  # one row per point, whole table

    def test_country_bbox_at_street_zoom_rejected(self):
        with pytest.raises(InputLimitError):
            validate_segments_args(18, [16.0, 45.7, 23.0, 48.6])

    @pytest.mark.parametrize("zoom", [-1, 23, 1e9, "14", None, True])
    def test_bad_zoom_rejected(self, zoom):
        with pytest.raises(InputLimitError):
            validate_grid_args(zoom, BUDAPEST_BBOX)

    def test_area_shrinks_with_zoom(self):
        assert max_bbox_area_for_zoom(10) == pytest.approx(
            4 * max_bbox_area_for_zoom(11)
        )


class TestRouteEndpoints:
    def test_coordinates_and_addresses_ok(self):
        assert validate_route_endpoints("47.4979,19.0402", " Debrecen ") == (
            "47.4979,19.0402",
            "Debrecen",
        )
        # Vienna is inside the margin.
        validate_route_endpoints("48.2082, 16.3738", "Győr")

    @pytest.mark.parametrize("address", [
        "1051 Budapest, Nádor utca 5.", "47 Main Street", "E 19th Street, Budapest",
        "Budapest, 47-es út", "Győr", "Debrecen",
    ])
    def test_real_addresses_keep_the_address_path(self, address):
        assert validate_route_endpoints(address, "Budapest")[0] == address
        assert limits.parse_lat_lng(address) is None

    @pytest.mark.parametrize("value", [
        "40.7 -74.0", "+34.05,-118.24", "40.7; -74.0", "40.7/−74.0",
        "40.7 −74.0", "N40.7 W74.0", "N40.7 E-74.0", "40.7°N 74.0°W",
        "lat: 40.7, lng: -74.0", "[40.7, -74.0]", "40.7 | -74.0",
        "40.7x-74.0", "40.7 and -74.0", "4.07e1,-7.4e1", "４０.７,−７４.０",
        "47.5 19.04", "+47.5,+19.04", "N47.5 E19.04", "47.5;19.04",
        "47.5,,,19.04", "47.5,19.04,20", "47,5;19,04", "47.5", "47.5,",
        "NaN,19.04", "47.5,Infinity", "NaN,NaN", "47.5\u00a019.04",
        "47.5\t19.04", "47.5\n19.04", "47.5，19.04", "47.5,+19.04",
        "40.7xyz-74.0", "40.7,-74.0 USA", "N40.7 W74.0 USA", "40,74 USA",
        "⁴⁰.⁷,⁻⁷⁴.⁰", "47.5<separator>19.04",
    ])
    @pytest.mark.parametrize("endpoint", ["origin", "destination"])
    def test_numeric_bypasses_and_noncanonical_pairs_rejected(self, value, endpoint):
        args = {"origin": "Budapest", "destination": "Győr", endpoint: value}
        with pytest.raises(InputLimitError) as caught:
            validate_route_endpoints(**args)
        assert caught.value.extensions == {"code": "BAD_USER_INPUT"}

    def test_canonical_whitespace_and_service_area_boundaries(self):
        assert validate_route_endpoints(" 47.5 , 19.04 ", "Győr")[0] == "47.5 , 19.04"
        validate_route_endpoints("45.4,15.5", "49.0,23.5")
        for value in ("45.399,19", "49.001,19", "47.5,15.499", "47.5,23.501"):
            with pytest.raises(InputLimitError, match="outside the service area"):
                validate_route_endpoints(value, "Budapest")

    @pytest.mark.parametrize(
        "origin",
        ["", "   ", None, "x" * 201, "Buda\x00pest", "40.7128,-74.0060", "95,19"],
    )
    def test_bad_input_rejected(self, origin):
        with pytest.raises(InputLimitError):
            validate_route_endpoints(origin, "Budapest")


class TestRoutePath:
    LINE = [[47.4979, 19.0402], [47.53, 21.63]]  # Budapest -> Debrecen, ~195 km

    def test_shapes_accepted(self):
        expected = [(47.4979, 19.0402), (47.53, 21.63)]
        assert validate_route_path(self.LINE) == expected
        assert validate_route_path(
            [{"lat": 47.4979, "lng": 19.0402}, {"latitude": 47.53, "longitude": 21.63}]
        ) == expected

        @strawberry.input
        class LatLng:
            lat: float
            lng: float

        assert validate_route_path([LatLng(lat=a, lng=b) for a, b in self.LINE]) == expected

    def test_encoded_polyline(self):
        from googlemaps.convert import encode_polyline

        coords = validate_route_path(encode_polyline([(47.4979, 19.0402), (47.53, 21.63)]))
        assert coords[0] == pytest.approx((47.4979, 19.0402), abs=1e-5)

    def test_too_many_points(self):
        path = [[47.5, 19.0 + i * 1e-6] for i in range(limits.MAX_PATH_POINTS + 1)]
        with pytest.raises(InputLimitError):
            validate_route_path(path)

    def test_too_long(self):
        # ~1 800 km of zig-zag across Hungary.
        zigzag = [[46.0, 16.0], [48.5, 23.0]] * 3
        with pytest.raises(InputLimitError, match="longer than"):
            validate_route_path(zigzag)

    def test_short_and_foreign_paths_are_cheap_and_allowed(self):
        assert validate_route_path([]) == []
        assert validate_route_path([[47.5, 19.0]]) == [(47.5, 19.0)]
        assert len(validate_route_path([[48.21, 16.37], [50.08, 14.43]])) == 2  # Wien-Praha

    @pytest.mark.parametrize(
        "path",
        [None, [[47.5, 19.0], [47.5]], [[47.5, 19.0], [95.0, 19.0]],
         [[47.5, 19.0], ["a", "b"]], "!!!", 42],
    )
    def test_bad_paths(self, path):
        with pytest.raises(InputLimitError):
            validate_route_path(path)


# --- Guard on the real schemas (rejections never execute) ------------------------


class TestPublicSchemaGuard:
    @pytest.mark.parametrize("value", ["40.7 -74.0", "+34.05,-118.24", "N40.7 W74.0", "47.5 19.04"])
    def test_numeric_bypasses_blocked_before_execution(self, read_schema, full_schema, value):
        alt = 'query($o: String!) { routeAlternatives(origin: $o, destination: "Győr") { fastestIndex } }'
        route = 'query($o: String!) { getRoute(origin: $o, destination: "Győr") { points { lat } } }'
        # getRoute is full-schema only since T-79; the guard runs on both schemas.
        assert errors_of(read_schema, alt, {"o": value})
        assert errors_of(full_schema, route, {"o": value})

    def test_getroute_alias_amplification_blocked(self, full_schema):
        query = "{ a: getRoute(origin: \"Budapest\", destination: \"Győr\") { points { lat } }" \
                " b: getRoute(origin: \"Budapest\", destination: \"Pécs\") { points { lat } } }"
        assert errors_of(full_schema, query) == ["At most 1 getRoute per request"]

    def test_fragment_spread_counts_too(self, read_schema):
        query = """
          { ...R  b: routeAlternatives(origin: "a", destination: "b") { fastestIndex } }
          fragment R on Query { a: routeAlternatives(origin: "c", destination: "d") { fastestIndex } }
        """
        assert "At most 1 routeAlternatives per request" in errors_of(read_schema, query)

    def test_points_limit_via_variables(self, read_schema):
        query = "query($l: Int) { points(limit: $l) { id } }"
        msgs = errors_of(read_schema, query, {"l": 1_000_000})
        assert msgs == ["limit must be between 0 and 1000 without a bbox"]

    def test_points_default_args_checked(self, read_schema):
        # bbox of length 3 used to be ignored silently.
        msgs = errors_of(read_schema, "{ points(bbox: [1, 2, 3]) { id } }")
        assert msgs == ["bbox must be [minLng, minLat, maxLng, maxLat]"]

    def test_grid_zoom_checked(self, read_schema):
        assert errors_of(read_schema, "{ roadQualityGrid(zoom: 22) }")

    def test_error_code(self, read_schema):
        result = read_schema.execute_sync("{ points(limit: -1) { id } }")
        assert result.errors[0].extensions == {"code": "BAD_USER_INPUT"}

    def test_aliases_tokens_depth(self, read_schema):
        many = " ".join(f"a{i}: me {{ role }}" for i in range(limits.MAX_ALIASES + 1))
        assert "aliases found" in errors_of(read_schema, "{ " + many + " }")[0]
        huge = "{ " + "me { role } " * 1000 + "}"
        assert "tokens" in errors_of(read_schema, huge)[0]

    def test_token_cap_on_async_path(self, read_schema):
        # HTTP requests use the async path, where MaxTokensLimiter is a no-op.
        import asyncio

        huge = "{ " + "me { role } " * 1000 + "}"
        result = asyncio.run(read_schema.execute(huge, context_value={"identity": None}))
        assert result.data is None and "tokens" in result.errors[0].message

    def test_google_key_field_closed_on_public_schema(self, read_schema, full_schema):
        result = read_schema.execute_sync("{ config }", context_value={"identity": None})
        assert result.data is None
        assert result.errors[0].message.startswith("Cannot query field")
        assert result.errors[0].nodes[0].name.value == "config"
        # The full (local) schema leaves it to the field's own permission.
        check_operation(full_schema._schema, parse("{ config }"))

    def test_introspection_off_on_public_schema(self, read_schema):
        assert errors_of(read_schema, "{ __schema { types { name } } }")
        result = read_schema.execute_sync("{ __typename }")  # Apollo adds this
        assert result.errors is None

    def test_introspection_on_for_local_schema(self, full_schema):
        from graphql import get_introspection_query

        result = full_schema.execute_sync(get_introspection_query())
        assert result.errors is None  # codegen keeps working locally


class TestFrontendDocumentsPass:
    """Every query the frontend ships must pass the guard with its real
    variables (the check runs without executing)."""

    VARIABLES = {
        "GetPoints": {"limit": 20_000, "bbox": BUDAPEST_BBOX},
        "GetSegmentFrames": {"limit": 2_000, "bbox": [19.04, 47.49, 19.05, 47.50]},
        "GetRoadSegments": {"zoom": 15, "bbox": [19.0, 47.45, 19.1, 47.52]},
        "GetRouteQuality": {"path": [[47.4979, 19.0402], [47.53, 21.63]]},
        "GetRoadQualityGrid": {"zoom": 8, "bbox": [14.0, 45.0, 24.0, 50.0]},
        "RouteAlternatives": {"origin": "47.4979,19.0402", "destination": "Debrecen"},
        "GetPointDetail": {"id": 1},
    }

    def documents(self):
        """Query documents from the gql(`...`) templates in frontend/src."""
        src = FRONTEND_GQL.parents[2]  # frontend/src
        if not src.is_dir():
            pytest.skip("frontend sources not present")
        docs = set()
        for path in src.rglob("*.ts*"):
            if "generated" in path.parts or ".test." in path.name:
                continue
            for body in re.findall(r"gql\(\s*`([^`]*)`", path.read_text()):
                if re.match(r"\s*query\b", body):
                    docs.add(body)
        return sorted(docs)

    def test_all_queries_pass(self, read_schema):
        docs = self.documents()
        names = {parse(d).definitions[0].name.value for d in docs}
        # The planner asks routeAlternatives (one Directions call) instead of getRoute.
        assert {"GetPoints", "GetRoadQualityGrid", "RouteAlternatives"} <= names
        for source in docs:
            document = parse(source)
            name = document.definitions[0].name.value
            check_operation(read_schema._schema, document, None, self.VARIABLES.get(name, {}))


# --- Error masking (public schema) -----------------------------------------------


@strawberry.type
class ProbeQuery:
    @strawberry.field(permission_classes=[IsAdmin])
    def needs_admin(self) -> str:
        return "ok"

    @strawberry.field
    def broken(self) -> str:
        raise RuntimeError("(psycopg2.OperationalError) host=ep-secret.neon.tech")

    @strawberry.field
    def bad_input(self) -> str:
        raise InputLimitError("limit too big")


class TestMasking:
    def test_public_masks_unexpected_errors_only(self):
        probe = strawberry.Schema(query=ProbeQuery, extensions=schema_extensions(public=True))
        result = probe.execute_sync("{ broken }")
        assert [e.message for e in result.errors] == ["Unexpected error."]
        result = probe.execute_sync("{ badInput }")
        assert [e.message for e in result.errors] == ["limit too big"]

    def test_local_keeps_details(self):
        probe = strawberry.Schema(query=ProbeQuery, extensions=schema_extensions(public=False))
        assert "psycopg2" in probe.execute_sync("{ broken }").errors[0].message

    def test_permission_errors_not_masked(self):
        probe = strawberry.Schema(query=ProbeQuery, extensions=schema_extensions(public=True))
        result = probe.execute_sync(
            "{ needsAdmin }", context_value={"identity": None}
        )
        assert result.errors[0].message == "Admin privileges required"


# --- App wiring in PUBLIC_READ_ONLY mode (fresh interpreter: settings are
# --- read at import time) -----------------------------------------------------------

_PROBE_APP = r"""
from fastapi.testclient import TestClient
from app.main import app

paths = {getattr(r, "path", "") for r in app.routes}
for p in ("/api/v1/points", "/api/v1/points/{point_id}", "/api/v1/process-route",
          "/api/v1/jobs/active", "/images/{filename}", "/api/v1/exports/{filename}",
          "/docs", "/openapi.json", "/redoc"):
    assert p not in paths, p
assert "/graphql" in paths and "/health" in paths

c = TestClient(app)
r = c.get("/health")
assert r.status_code == 200
assert r.headers["x-content-type-options"] == "nosniff"
assert r.headers["x-frame-options"] == "DENY"
assert c.get("/docs").status_code == 404
assert c.get("/api/v1/points").status_code == 404

# GraphiQL off, GET queries off, POST works without a DB for __typename.
assert c.get("/graphql", headers={"accept": "text/html"}).status_code in (404, 405)
assert c.get("/graphql", params={"query": "{ __typename }"}).status_code in (400, 404, 405)
r = c.post("/graphql", json={"query": "{ __typename }"})
assert r.status_code == 200 and r.json()["data"] == {"__typename": "Query"}, r.text

# Limits hold on the HTTP (async) path, before any resolver or DB access.
def gql_errors(query):
    body = c.post("/graphql", json={"query": query}).json()
    assert body["data"] is None, body
    return [e["message"] for e in body["errors"]]
two = '{ a: routeAlternatives(origin: "x", destination: "y") { fastestIndex } ' \
      'b: routeAlternatives(origin: "x", destination: "z") { fastestIndex } }'
assert gql_errors(two) == ["At most 1 routeAlternatives per request"]
assert "tokens" in gql_errors("{ " + "me { role } " * 1000 + "}")[0]
assert "introspection" in gql_errors("{ __schema { types { name } } }")[0]

# CORS: allowed origin, no credentials; foreign origin refused.
ok = c.options("/graphql", headers={"origin": "https://simaut.hu",
    "access-control-request-method": "POST", "access-control-request-headers": "content-type"})
assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "https://simaut.hu"
assert "access-control-allow-credentials" not in ok.headers
bad = c.options("/graphql", headers={"origin": "https://evil.example",
    "access-control-request-method": "POST"})
assert bad.status_code == 400
print("OK")
"""

_PROBE_LOCAL_CORS = r"""
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
def preflight(origin):
    return c.options("/graphql", headers={"origin": origin,
        "access-control-request-method": "POST"})
assert preflight("http://localhost:5199").status_code == 200
assert preflight("http://127.0.0.1:5173").status_code == 200
assert preflight("https://evil.example").status_code == 400
assert preflight("http://localhost.evil.example").status_code == 400
print("OK")
"""


def _run_app_probe(code: str, tmp_path, **env):
    full_env = {
        **os.environ,
        "DATA_DIR": str(tmp_path),  # local mode mkdirs previews/ here
        "RUN_MIGRATIONS_ON_STARTUP": "false",
        "ALLOWED_ORIGINS": "https://simaut.hu",
        "DATABASE_URL": "postgresql://nobody:x@127.0.0.1:9/none",  # never connected
        **env,
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stderr[-3000:]


def test_public_read_only_app_wiring(tmp_path):
    _run_app_probe(_PROBE_APP, tmp_path, PUBLIC_READ_ONLY="1", AUTH_MODE="clerk")


def test_local_cors_allows_localhost_only(tmp_path):
    _run_app_probe(_PROBE_LOCAL_CORS, tmp_path, PUBLIC_READ_ONLY="0", AUTH_MODE="disabled")
