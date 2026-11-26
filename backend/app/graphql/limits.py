"""Cost and abuse limits for the GraphQL API.

The public read-only deploy is anonymous, so every limit here is per request:
nothing in this module knows who is calling. Per-IP rate limiting belongs to
the edge (Vercel WAF), hard money caps to the GCP quota page.

Three layers, all registered in schema.py via `schema_extensions()`:

1. Document limits: token count (`MaxTokensParser`), query depth and alias
   count (Strawberry built-ins). They run at parse/validation time, before
   any resolver.
2. `PublicQueryGuard`: checks the arguments of the anonymous, data-heavy root
   fields (points, roadQualityGrid, getRoute, roadSegments, routeQuality) and
   how often each appears in one operation, BEFORE execution. A rejected
   request costs no DB row and no Google call.
3. Public schema only: introspection off, unexpected exceptions masked (no SQL
   text, hostnames or file paths in responses; the original is still logged).

The validators are plain functions so resolvers can call them too (see
`validate_segments_args`, `validate_route_path`). They raise `InputLimitError`
(a GraphQLError with code BAD_USER_INPUT), which MaskErrors lets through.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Optional

from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    GraphQLError,
    GraphQLSchema,
    InlineFragmentNode,
    SelectionSetNode,
    parse,
)
from graphql.execution.values import get_argument_values, get_variable_values
from graphql.utilities import get_operation_ast
from strawberry.extensions import (
    DisableIntrospection,
    MaskErrors,
    MaxAliasesLimiter,
    QueryDepthLimiter,
    SchemaExtension,
)

# --- Document limits ---------------------------------------------------------
# The deepest frontend document is 3 levels (trainingPoints.items.field);
# introspection fields are not counted by QueryDepthLimiter. No frontend
# document uses aliases; the largest is ~150 tokens.
MAX_QUERY_DEPTH = 8
MAX_ALIASES = 10
MAX_TOKENS = 2000

# --- points(bbox, limit, offset) ---------------------------------------------
MAX_POINTS_LIMIT = 20_000  # == frontend MAP_POINT_LIMIT (modules/map/sagas.ts)
MAX_UNBOUNDED_POINTS_LIMIT = 1_000  # without a bbox only small pages
MAX_OFFSET = 100_000
# Points load at zoom >= 14; that viewport on an 8K screen is ~0.25 deg².
MAX_POINTS_BBOX_AREA_DEG2 = 1.0

# --- zoom + bbox viewports (roadQualityGrid, roadSegments) --------------------
MIN_ZOOM, MAX_ZOOM = 0, 22
# A bbox may be at most this many pixels at the given zoom (8K screen, x2
# slack). Stops "zoom=18 detail over the whole country" requests. At the grid's
# 8 px cells this is ~1M cells max.
MAX_VIEWPORT_PX = (7680, 4320)
VIEWPORT_SLACK = 2.0
_WORLD = (-180.0, -90.0, 180.0, 90.0)

# --- getRoute(origin, destination): one paid Google Directions call ------------
MAX_ROUTE_ENDPOINT_CHARS = 200
# Coordinate inputs must fall in the service area: Hungary plus a margin that
# keeps Vienna, Bratislava, Zagreb and Oradea reachable. Free-text addresses
# cannot be checked without a (paid) geocode, so they only get the length cap.
SERVICE_AREA = (15.5, 45.4, 23.5, 49.0)  # minLng, minLat, maxLng, maxLat

# --- routeQuality(path): PostGIS buffer/match along a user path ---------------
MAX_PATH_POINTS = 5_000  # a Google overview polyline across HU is < 2 000
MAX_PATH_KM = 1_000.0  # longest drive inside HU is ~600 km
MAX_ENCODED_POLYLINE_CHARS = 50_000

# --- How often a root field may appear in one operation (distinct aliases) ----
MAX_ROOT_FIELD_COUNT = {
    "getRoute": 1,  # paid Google call
    "routeQuality": 1,  # heaviest PostGIS query
    "roadSegments": 2,
    "points": 2,
    "roadQualityGrid": 2,
}

_COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class InputLimitError(GraphQLError):
    """A request argument is outside the allowed bounds (shown to the client)."""

    def __init__(self, message: str):
        super().__init__(message, extensions={"code": "BAD_USER_INPUT"})


# --- Validators (pure; reusable from resolvers) --------------------------------


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise InputLimitError(f"{name} must be a number") from None
    if not math.isfinite(number):
        raise InputLimitError(f"{name} must be finite")
    return number


def validate_bbox(
    bbox: Optional[Sequence[float]], *, required: bool = False
) -> Optional[tuple[float, float, float, float]]:
    """`[minLng, minLat, maxLng, maxLat]` or None. Values may exceed ±180/±90
    (a zoomed-out viewport does); `bbox_area_deg2` clamps to the world."""
    if bbox is None:
        if required:
            raise InputLimitError("bbox is required")
        return None
    if isinstance(bbox, (str, bytes)) or len(bbox) != 4:
        # The resolvers silently ignore a bbox that is not 4 long, which turned
        # `points(bbox: [1, 2, 3])` into a whole-table read.
        raise InputLimitError("bbox must be [minLng, minLat, maxLng, maxLat]")
    min_lng, min_lat, max_lng, max_lat = (_finite(v, "bbox") for v in bbox)
    if min_lng > max_lng or min_lat > max_lat:
        raise InputLimitError("bbox must be [minLng, minLat, maxLng, maxLat]")
    return (min_lng, min_lat, max_lng, max_lat)


def bbox_area_deg2(bbox: Optional[Sequence[float]]) -> float:
    """Area in square degrees after clamping to the world (None = world)."""
    min_lng, min_lat, max_lng, max_lat = bbox if bbox is not None else _WORLD
    width = max(0.0, min(max_lng, 180.0) - max(min_lng, -180.0))
    height = max(0.0, min(max_lat, 90.0) - max(min_lat, -90.0))
    return width * height


def max_bbox_area_for_zoom(zoom: int) -> float:
    """Largest bbox (deg²) a MAX_VIEWPORT_PX screen shows at `zoom`, with slack."""
    deg_per_px = 360.0 / (256 * 2**zoom)
    width_px, height_px = MAX_VIEWPORT_PX
    return width_px * height_px * deg_per_px**2 * VIEWPORT_SLACK


def validate_zoom(zoom: Any) -> int:
    if isinstance(zoom, bool) or not isinstance(zoom, (int, float)):
        raise InputLimitError("zoom must be an integer")
    if not math.isfinite(zoom) or not MIN_ZOOM <= zoom <= MAX_ZOOM:
        raise InputLimitError(f"zoom must be between {MIN_ZOOM} and {MAX_ZOOM}")
    return int(zoom)


def validate_viewport(
    zoom: Any, bbox: Optional[Sequence[float]], *, require_bbox: bool = False
) -> tuple[int, Optional[tuple[float, float, float, float]]]:
    """zoom in range and a bbox no larger than a big screen at that zoom.
    Without a bbox the whole world is the viewport (allowed up to zoom ~5)."""
    zoom = validate_zoom(zoom)
    box = validate_bbox(bbox, required=require_bbox)
    if bbox_area_deg2(box) > max_bbox_area_for_zoom(zoom):
        raise InputLimitError(
            "bbox is too large for this zoom level; zoom in or send the visible bbox"
        )
    return zoom, box


def validate_points_args(
    bbox: Optional[Sequence[float]], limit: Any, offset: Any
) -> tuple[Optional[tuple[float, float, float, float]], int, int]:
    """points(bbox, limit, offset): bounded page, bounded area."""
    box = validate_bbox(bbox)
    max_limit = MAX_POINTS_LIMIT if box is not None else MAX_UNBOUNDED_POINTS_LIMIT
    limit = 100 if limit is None else limit
    offset = 0 if offset is None else offset
    if not isinstance(limit, int) or not 0 <= limit <= max_limit:
        hint = "" if box is not None else " without a bbox"
        raise InputLimitError(f"limit must be between 0 and {max_limit}{hint}")
    if not isinstance(offset, int) or not 0 <= offset <= MAX_OFFSET:
        raise InputLimitError(f"offset must be between 0 and {MAX_OFFSET}")
    if box is not None and bbox_area_deg2(box) > MAX_POINTS_BBOX_AREA_DEG2:
        raise InputLimitError(
            "bbox is too large for points; use roadQualityGrid when zoomed out"
        )
    return box, limit, offset


def validate_grid_args(zoom: Any, bbox: Optional[Sequence[float]]):
    """roadQualityGrid(zoom, bbox)."""
    return validate_viewport(zoom, bbox)


def validate_segments_args(zoom: Any, bbox: Optional[Sequence[float]]):
    """roadSegments(bbox, zoom). Call first thing in the resolver:
    `zoom, bbox = validate_segments_args(zoom, bbox)`."""
    return validate_viewport(zoom, bbox)


def _in_service_area(lat: float, lng: float) -> bool:
    min_lng, min_lat, max_lng, max_lat = SERVICE_AREA
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng


def parse_lat_lng(text: str) -> Optional[tuple[float, float]]:
    """"lat,lng" -> (lat, lng); None when the text is not a coordinate pair."""
    match = _COORD_RE.match(text)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def validate_route_endpoint(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputLimitError(f"{name} is required")
    value = value.strip()
    if len(value) > MAX_ROUTE_ENDPOINT_CHARS:
        raise InputLimitError(
            f"{name} must be at most {MAX_ROUTE_ENDPOINT_CHARS} characters"
        )
    if _CONTROL_RE.search(value):
        raise InputLimitError(f"{name} contains control characters")
    coords = parse_lat_lng(value)
    if coords is not None:
        lat, lng = coords
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise InputLimitError(f"{name} is not a valid lat,lng")
        if not _in_service_area(lat, lng):
            raise InputLimitError(f"{name} is outside the service area")
    return value


def validate_route_endpoints(origin: Any, destination: Any) -> tuple[str, str]:
    """getRoute(origin, destination): each a "lat,lng" or a short address."""
    return (
        validate_route_endpoint(origin, "origin"),
        validate_route_endpoint(destination, "destination"),
    )


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, h)))


def _as_lat_lng(point: Any) -> tuple[Any, Any]:
    if isinstance(point, Mapping):
        return (
            point.get("lat", point.get("latitude")),
            point.get("lng", point.get("longitude")),
        )
    if isinstance(point, Sequence) and not isinstance(point, (str, bytes)):
        if len(point) != 2:
            raise InputLimitError("each path point must be [lat, lng]")
        return point[0], point[1]
    lat = getattr(point, "lat", getattr(point, "latitude", None))
    lng = getattr(point, "lng", getattr(point, "longitude", None))
    return lat, lng


def validate_route_path(path: Any) -> list[tuple[float, float]]:
    """routeQuality(path) input -> [(lat, lng), …] inside the service area.

    Accepts [[lat, lng], …], [{lat, lng}, …], input objects with .lat/.lng (or
    .latitude/.longitude), or a Google encoded polyline string. Caps the point
    count and the total length, so the PostGIS buffer/match work is bounded.
    """
    if path is None:
        raise InputLimitError("path is required")
    if isinstance(path, str):
        if len(path) > MAX_ENCODED_POLYLINE_CHARS:
            raise InputLimitError("encoded path is too long")
        from googlemaps.convert import decode_polyline

        try:
            path = decode_polyline(path)
        except Exception:  # noqa: BLE001 - any decode failure is bad input
            raise InputLimitError("path is not a valid encoded polyline") from None
    if not isinstance(path, Sequence):
        raise InputLimitError("path must be a list of [lat, lng] points")
    if not 2 <= len(path) <= MAX_PATH_POINTS:
        raise InputLimitError(f"path must have 2 to {MAX_PATH_POINTS} points")

    coords: list[tuple[float, float]] = []
    for point in path:
        raw_lat, raw_lng = _as_lat_lng(point)
        lat, lng = _finite(raw_lat, "lat"), _finite(raw_lng, "lng")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise InputLimitError("path contains an invalid lat,lng")
        if not _in_service_area(lat, lng):
            raise InputLimitError("path leaves the service area")
        coords.append((lat, lng))

    total_km = sum(_haversine_km(a, b) for a, b in zip(coords, coords[1:]))
    if total_km > MAX_PATH_KM:
        raise InputLimitError(f"path is longer than {MAX_PATH_KM:.0f} km")
    return coords


# --- Extensions -------------------------------------------------------------------


class MaxTokensParser(SchemaExtension):
    """Parse with a token cap on both execution paths.

    Strawberry's MaxTokensLimiter only sets `parse_options`, which the async
    path — every HTTP request — ignores (strawberry-graphql 0.287), so a
    multi-megabyte query was parsed in full. Setting the document in on_parse
    is the same hook ParserCache uses; Strawberry then skips its own parse.
    """

    def __init__(self, max_token_count: int) -> None:
        self.max_token_count = max_token_count

    def on_parse(self):
        ctx = self.execution_context
        if ctx.graphql_document is None and ctx.query:
            ctx.graphql_document = parse(ctx.query, max_tokens=self.max_token_count)
        yield


# --- Pre-execution guard -------------------------------------------------------

def _check_points(args: dict) -> None:
    validate_points_args(args.get("bbox"), args.get("limit"), args.get("offset"))


def _check_grid(args: dict) -> None:
    validate_grid_args(args.get("zoom"), args.get("bbox"))


def _check_route(args: dict) -> None:
    validate_route_endpoints(args.get("origin"), args.get("destination"))


def _check_segments(args: dict) -> None:
    # Expected signature roadSegments(bbox, zoom); skip if it differs.
    if "zoom" in args:
        validate_segments_args(args.get("zoom"), args.get("bbox"))


def _check_route_quality(args: dict) -> None:
    # Expected signature routeQuality(path); other shapes are left to the
    # resolver, which should call validate_route_path itself.
    if "path" in args:
        validate_route_path(args.get("path"))


# GraphQL (camelCase) root field name -> argument check.
ROOT_FIELD_CHECKS: dict[str, Callable[[dict], None]] = {
    "points": _check_points,
    "roadQualityGrid": _check_grid,
    "getRoute": _check_route,
    "roadSegments": _check_segments,
    "routeQuality": _check_route_quality,
}


def _root_field_nodes(
    selection_set: SelectionSetNode,
    fragments: dict[str, FragmentDefinitionNode],
    seen_fragments: set[str],
):
    """Root-level FieldNodes, looking through fragment spreads/inline fragments."""
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            yield selection
        elif isinstance(selection, InlineFragmentNode):
            yield from _root_field_nodes(
                selection.selection_set, fragments, seen_fragments
            )
        elif isinstance(selection, FragmentSpreadNode):
            name = selection.name.value
            if name in seen_fragments or name not in fragments:
                continue
            seen_fragments.add(name)
            yield from _root_field_nodes(
                fragments[name].selection_set, fragments, seen_fragments
            )


def check_operation(
    schema: GraphQLSchema,
    document,
    operation_name: Optional[str] = None,
    variables: Optional[dict[str, Any]] = None,
) -> None:
    """Raise InputLimitError when the selected operation breaks a limit.

    Anything this function cannot interpret (unknown operation, variable
    coercion errors) is left for normal execution to report.
    """
    operation = get_operation_ast(document, operation_name)
    if operation is None:
        return
    root_type = schema.get_root_type(operation.operation)
    if root_type is None:
        return
    coerced = get_variable_values(
        schema, operation.variable_definitions or (), variables or {}
    )
    if isinstance(coerced, list):  # variable errors: execution reports them
        return
    fragments = {
        d.name.value: d
        for d in document.definitions
        if isinstance(d, FragmentDefinitionNode)
    }

    response_keys: dict[str, set[str]] = {}
    for node in _root_field_nodes(operation.selection_set, fragments, set()):
        name = node.name.value
        field_def = root_type.fields.get(name)
        if field_def is None:
            continue
        keys = response_keys.setdefault(name, set())
        keys.add(node.alias.value if node.alias else name)
        max_count = MAX_ROOT_FIELD_COUNT.get(name)
        if max_count is not None and len(keys) > max_count:
            raise InputLimitError(f"At most {max_count} {name} per request")
        check = ROOT_FIELD_CHECKS.get(name)
        if check is not None:
            check(get_argument_values(field_def, node, coerced))


class PublicQueryGuard(SchemaExtension):
    """Runs check_operation before execution; a violation skips execution."""

    def on_execute(self):
        ctx = self.execution_context
        if ctx.graphql_document is not None:
            check_operation(
                ctx.schema._schema,
                ctx.graphql_document,
                ctx.operation_name,
                ctx.variables,
            )
        yield


# --- Error masking (public schema) ---------------------------------------------

def should_mask_error(error: GraphQLError) -> bool:
    """Mask unexpected exceptions (DB errors carry SQL text and hostnames);
    keep GraphQL errors (validation, permissions, InputLimitError)."""
    original = error.original_error
    return original is not None and not isinstance(original, GraphQLError)


def schema_extensions(public: bool) -> list:
    """Extensions for strawberry.Schema(..., extensions=...).

    public=True (the anonymous read-only schema) also disables introspection
    and masks unexpected errors; the full local schema keeps both for dev.
    """
    extensions: list = [
        QueryDepthLimiter(max_depth=MAX_QUERY_DEPTH),
        MaxAliasesLimiter(max_alias_count=MAX_ALIASES),
        MaxTokensParser(max_token_count=MAX_TOKENS),
        PublicQueryGuard,
    ]
    if public:
        extensions += [
            DisableIntrospection(),
            MaskErrors(should_mask_error=should_mask_error),
        ]
    return extensions
