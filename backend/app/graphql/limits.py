"""Cost and abuse limits for the GraphQL API.

The public read-only deploy is anonymous, so every limit here is per request:
nothing in this module knows who is calling. Per-IP rate limiting belongs to
the edge (Vercel WAF), hard money caps to the GCP quota page.

Three layers, all registered in schema.py via `schema_extensions()`:

1. Document limits: token count (`MaxTokensParser`), fragment expansion,
   query depth and aliases. They run at parse time, before other validators or
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
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional

from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    GraphQLError,
    GraphQLSchema,
    InlineFragmentNode,
    OperationDefinitionNode,
    SelectionSetNode,
    parse,
)
from graphql.execution.values import get_argument_values, get_variable_values
from graphql.utilities import get_operation_ast
from strawberry.extensions import (
    DisableIntrospection,
    MaskErrors,
    SchemaExtension,
)

# --- Document limits ---------------------------------------------------------
# The deepest frontend document is 3 levels (trainingPoints.items.field);
# introspection fields are not counted for depth. No frontend
# document uses aliases; the largest is ~150 tokens.
MAX_QUERY_DEPTH = 8
MAX_ALIASES = 10
MAX_TOKENS = 2000
# Bound the expanded selection tree before graphql-core's validators run.
MAX_DOCUMENT_WORK = 10_000

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

# --- routeQuality(path): segment match along a user path ----------------------
# == services/segment_read.MAX_PATH_POINTS (kept equal, not imported, so this
# module stays import-light).
MAX_PATH_POINTS = 20_000
# The matcher samples every 10 m in Python: ~1.1 ms CPU per km (benchmarked),
# so 800 km is ~1 s worst case. Longest drive inside HU is ~600 km.
MAX_PATH_KM = 800.0
MAX_ENCODED_POLYLINE_CHARS = 50_000

# --- How often a root field may appear in one operation (distinct aliases) ----
MAX_ROOT_FIELD_COUNT = {
    "getRoute": 1,  # paid Google call
    "routeAlternatives": 1,  # the same paid call (alternatives=true)
    "routeQuality": 1,  # heaviest PostGIS query
    "roadSegments": 2,
    "points": 2,
    "roadQualityGrid": 2,
    "segmentFrames": 2,  # ~10-35 ms each (frames + nearby segments matched)
}

# Paid Google fields: one per request IN TOTAL, not one of each (getRoute and
# routeAlternatives each cost one Directions call in public mode; local
# address-only requests may also use 2 Geocoding calls + 1 Directions retry).
PAID_ROOT_FIELDS = ("getRoute", "routeAlternatives")
MAX_PAID_ROOT_FIELDS = 1

# Per-item fields that run their own DB query for EACH object they appear on:
# allowed only below the listed root fields. Point.segmentId is one PostGIS
# query + a line index per point (~5 ms locally, a Neon round trip in prod);
# on `points(limit: 20000)` that is 20 000 queries from one anonymous request.
PER_ITEM_FIELD_ROOTS = {
    "segmentId": frozenset({"point"}),
}

# Root fields the anonymous public schema never serves, whatever their
# permission class says. `config` returned the server-side Google key to
# anyone until the QA fix (460c5f9) made it admin-only; this keeps it shut on
# the public deploy whichever branch merges first.
PUBLIC_DENIED_ROOT_FIELDS = frozenset({"config"})

_COORD_RE = re.compile(r"\s*(-?[0-9]+(?:\.[0-9]+)?)\s*,\s*(-?[0-9]+(?:\.[0-9]+)?)\s*")
# These words can decorate coordinates, so they must never turn numeric input
# into an address. Other words (street/city names) retain the address path.
_COORD_WORDS = frozenset({
    "n", "s", "e", "w", "north", "south", "east", "west",
    "lat", "lng", "lon", "latitude", "longitude", "geo", "gps", "and", "x", "by",
    "nan", "inf", "infinity",
})
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
# Google location modifiers (including future names) must not become addresses.
_LOCATION_PREFIX_RE = re.compile(r"^[\w-]+(?:\s*=[^:]*)?\s*:", re.UNICODE)


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
    """Parse decimal ``lat,lng`` (optional whitespace around the comma).

    Non-canonical numeric inputs are rejected, including space/semicolon
    separators, explicit plus signs, Unicode signs and compass prefixes.
    Only real address text returns None; malformed coordinates cannot skip
    the service-area check by falling through to Google's address parser.
    """
    match = _COORD_RE.fullmatch(text)
    if not match:
        # Normalize only for detection, never to silently accept another format.
        candidate = unicodedata.normalize("NFKC", text).casefold()
        words = re.findall(r"[^\W\d_]+", candidate)
        numbers = list(re.finditer(r"\d+(?:\.\d+)?", candidate))
        numeric = numbers or {"nan", "inf", "infinity"}.intersection(words)
        # An arbitrary separator/trailing place label must not disguise a
        # leading decimal pair. Postal codes and ordinary street numbers keep
        # the address path, e.g. "1051 Budapest, Nádor utca 5".
        decimal_pair = (
            len(numbers) >= 2
            and "." in numbers[0].group()
            and all(
                word in _COORD_WORDS
                for word in re.findall(r"[^\W\d_]+", candidate[:numbers[0].start()])
            )
        )
        if (
            (numeric and all(word in _COORD_WORDS for word in words))
            or decimal_pair
            or _COORD_RE.match(candidate)
        ):
            raise InputLimitError("coordinates must use decimal lat,lng format")
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
    if _LOCATION_PREFIX_RE.match(unicodedata.normalize("NFKC", value)):
        raise InputLimitError(f"{name} location modifiers are not supported")
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
            raise InputLimitError("every path point must be [lat, lng]")
        return point[0], point[1]
    lat = getattr(point, "lat", getattr(point, "latitude", None))
    lng = getattr(point, "lng", getattr(point, "longitude", None))
    return lat, lng


def validate_route_path(path: Any) -> list[tuple[float, float]]:
    """routeQuality(path) input -> [(lat, lng), …].

    Accepts [[lat, lng], …], [{lat, lng}, …], input objects with .lat/.lng (or
    .latitude/.longitude), or a Google encoded polyline string. Caps the point
    count and the total length, so the matching work is bounded. No service-
    area check: a route outside Hungary just matches nothing (cheap), and
    getRoute accepts addresses abroad, so rejecting it would only show an error.
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
    if len(path) > MAX_PATH_POINTS:
        raise InputLimitError(f"path has too many points (max {MAX_PATH_POINTS})")

    coords: list[tuple[float, float]] = []
    for point in path:
        raw_lat, raw_lng = _as_lat_lng(point)
        lat, lng = _finite(raw_lat, "lat"), _finite(raw_lng, "lng")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise InputLimitError("path point out of range (expected [lat, lng])")
        coords.append((lat, lng))

    validate_path_edges(coords)
    total_km = sum(_haversine_km(a, b) for a, b in zip(coords, coords[1:]))
    if total_km > MAX_PATH_KM:
        raise InputLimitError(f"path is longer than {MAX_PATH_KM:.0f} km")
    return coords


def validate_path_edges(path: Sequence[tuple[float, float]]) -> None:
    """Linear longitude interpolation does not support crossing the dateline."""
    if any(abs(b[1] - a[1]) > 180 for a, b in zip(path, path[1:])):
        raise InputLimitError("path edges must not cross the antimeridian")


# --- Extensions -------------------------------------------------------------------


# Every extension is registered as a zero-argument CLASS, never an instance:
# strawberry-graphql >= 0.33x (what Vercel installs) then builds a fresh one per
# request; shared instances leak execution_context between concurrent requests
# (strawberry#4369) and are deprecated. 0.287 (local venv) calls
# cls(execution_context=None), hence the keyword.


class MaxTokensParser(SchemaExtension):
    """Parse with a MAX_TOKENS cap on both execution paths.

    Strawberry's MaxTokensLimiter only sets `parse_options`, which the async
    path — every HTTP request — ignores (strawberry-graphql 0.287), so a
    multi-megabyte query was parsed in full. Setting the document in on_parse
    is the same hook ParserCache uses; Strawberry then skips its own parse.
    """

    def __init__(self, *, execution_context=None) -> None:
        self.execution_context = execution_context

    def on_parse(self):
        ctx = self.execution_context
        if ctx.graphql_document is None and ctx.query:
            ctx.graphql_document = parse(ctx.query, max_tokens=MAX_TOKENS)
        if ctx.graphql_document is not None:
            check_document_limits(ctx.graphql_document)
        yield


@dataclass(frozen=True)
class _SelectionCost:
    work: int = 0
    depth: int = 0
    aliases: int = 0
    restricted_fields: frozenset[str] = frozenset()


def check_document_limits(document) -> dict[int, _SelectionCost]:
    """Summarize each selection set once, including each fragment once.

    Iterative postorder avoids recursion limits on long fragment chains.
    Memoized costs count repeated spreads without expanding them. Cycles and
    expansion work are rejected before depth/alias and graphql-core validation.
    """
    fragments = {d.name.value: d for d in document.definitions
                 if isinstance(d, FragmentDefinitionNode)}
    owners = [d for d in document.definitions
              if isinstance(d, (OperationDefinitionNode, FragmentDefinitionNode))]
    costs: dict[int, _SelectionCost] = {}
    visiting: set[int] = set()

    def child(selection):
        if isinstance(selection, (FieldNode, InlineFragmentNode)):
            return selection.selection_set
        if isinstance(selection, FragmentSpreadNode):
            fragment = fragments.get(selection.name.value)
            return fragment.selection_set if fragment else None
        return None

    for owner in owners:
        stack = [(owner.selection_set, False)]
        while stack:
            selections, done = stack.pop()
            key = id(selections)
            if key in costs:
                continue
            if not done:
                if key in visiting:
                    raise InputLimitError("fragment cycles are not allowed")
                visiting.add(key)
                stack.append((selections, True))
                stack.extend((c, False) for s in selections.selections
                             if (c := child(s)) is not None)
                continue
            work = aliases = depth = 0
            restricted: set[str] = set()
            for selection in selections.selections:
                subtree = child(selection)
                cost = costs[id(subtree)] if subtree is not None else _SelectionCost()
                work += 1 + cost.work
                aliases += cost.aliases
                restricted.update(cost.restricted_fields)
                field_depth = cost.depth
                if isinstance(selection, FieldNode):
                    aliases += int(selection.alias is not None)
                    if selection.name.value in PER_ITEM_FIELD_ROOTS:
                        restricted.add(selection.name.value)
                    field_depth = (1 + cost.depth if subtree is not None else 0)
                    if selection.name.value.startswith("__"):
                        field_depth = 0
                depth = max(depth, field_depth)
                if work > MAX_DOCUMENT_WORK:
                    raise InputLimitError("document exceeds fragment expansion budget")
            costs[key] = _SelectionCost(work, depth, aliases, frozenset(restricted))
            visiting.remove(key)

    # Include all operations, even when operationName selects just one. Fragment
    # definitions are already included in their operation's memoized cost.
    operations = [costs[id(d.selection_set)] for d in owners
                  if isinstance(d, OperationDefinitionNode)]
    if sum(c.work for c in operations) > MAX_DOCUMENT_WORK:
        raise InputLimitError("document exceeds fragment expansion budget")
    if any(c.depth > MAX_QUERY_DEPTH for c in operations):
        raise InputLimitError(f"query exceeds maximum operation depth of {MAX_QUERY_DEPTH}")
    aliases = sum(c.aliases for c in operations)
    if aliases > MAX_ALIASES:
        raise InputLimitError(f"{aliases} aliases found. Allowed: {MAX_ALIASES}")
    return costs


class NoIntrospection(DisableIntrospection):
    def __init__(self, *, execution_context=None) -> None:
        super().__init__()


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
    "routeAlternatives": _check_route,
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


def _check_per_item_fields(root: FieldNode, costs: dict[int, _SelectionCost]) -> None:
    allowed_roots = {
        field: roots for field, roots in PER_ITEM_FIELD_ROOTS.items()
        if root.name.value not in roots
    }
    if not allowed_roots:
        return
    cost = costs.get(id(root.selection_set), _SelectionCost())
    for name in cost.restricted_fields:
        if name in allowed_roots:
            only = ", ".join(sorted(allowed_roots[name]))
            raise InputLimitError(
                f"{name} is only available on {only}(id), not on {root.name.value}"
            )


def check_operation(
    schema: GraphQLSchema,
    document,
    operation_name: Optional[str] = None,
    variables: Optional[dict[str, Any]] = None,
    denied_fields: frozenset = frozenset(),
) -> None:
    """Raise InputLimitError when the selected operation breaks a limit
    (a GraphQLError with code FORBIDDEN for a field in `denied_fields`).

    Anything this function cannot interpret (unknown operation, variable
    coercion errors) is left for normal execution to report.
    """
    costs = check_document_limits(document)
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
        if name in denied_fields:
            raise GraphQLError(
                f"{name} is not available on the public API",
                extensions={"code": "FORBIDDEN"},
            )
        field_def = root_type.fields.get(name)
        if field_def is None:
            continue
        keys = response_keys.setdefault(name, set())
        keys.add(node.alias.value if node.alias else name)
        max_count = MAX_ROOT_FIELD_COUNT.get(name)
        if max_count is not None and len(keys) > max_count:
            raise InputLimitError(f"At most {max_count} {name} per request")
        paid = sum(len(response_keys.get(f, ())) for f in PAID_ROOT_FIELDS)
        if name in PAID_ROOT_FIELDS and paid > MAX_PAID_ROOT_FIELDS:
            raise InputLimitError(
                f"At most {MAX_PAID_ROOT_FIELDS} route request "
                f"({' or '.join(PAID_ROOT_FIELDS)}) per request")
        _check_per_item_fields(node, costs)
        check = ROOT_FIELD_CHECKS.get(name)
        if check is not None:
            check(get_argument_values(field_def, node, coerced))


class PublicQueryGuard(SchemaExtension):
    """Runs check_operation before execution; a violation skips execution."""

    denied_fields: frozenset = frozenset()

    def on_execute(self):
        ctx = self.execution_context
        if ctx.graphql_document is not None:
            check_operation(
                ctx.schema._schema,
                ctx.graphql_document,
                ctx.operation_name,
                ctx.variables,
                denied_fields=self.denied_fields,
            )
        yield


class PublicSchemaGuard(PublicQueryGuard):
    """PublicQueryGuard plus PUBLIC_DENIED_ROOT_FIELDS (public schema only)."""

    denied_fields = PUBLIC_DENIED_ROOT_FIELDS


# --- Error masking (public schema) ---------------------------------------------

def should_mask_error(error: GraphQLError) -> bool:
    """Mask unexpected exceptions (DB errors carry SQL text and hostnames);
    keep GraphQL errors (validation, permissions, InputLimitError)."""
    original = error.original_error
    return original is not None and not isinstance(original, GraphQLError)


class MaskUnexpectedErrors(MaskErrors):
    def __init__(self, *, execution_context=None) -> None:
        super().__init__(should_mask_error=should_mask_error)


def schema_extensions(public: bool) -> list:
    """Extension classes for strawberry.Schema(..., extensions=...).

    public=True (the anonymous read-only schema) also disables introspection
    and masks unexpected errors; the full local schema keeps both for dev.
    """
    guard = PublicSchemaGuard if public else PublicQueryGuard
    extensions: list = [MaxTokensParser, guard]
    if public:
        extensions += [NoIntrospection, MaskUnexpectedErrors]
    return extensions
