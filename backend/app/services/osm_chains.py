"""Join consecutive OSM ways of the same road into longer lines (pure).

OSM cuts a road into a new way wherever a tag changes (lane count, speed
limit, bridge, bus lane…), so in a city the typical way is only ~70 m long.
Cutting each way separately into "~150 m" pieces therefore mostly yields
fragments with two or three frames. Before splitting we stitch ways back into
the road they belong to:

Two way ENDS are joined when they meet at the same node and are a unique
continuation of each other:

- both ways carry the same ``name`` (or ref) and the same ``highway`` class,
  and exactly two ends with that name+class meet at the node (a third one is
  a fork — e.g. where a dual carriageway splits — and stops the chain), or
- both ways are unnamed, share the ``highway`` class, and nothing else ends
  at the node (a plain continuation, not a junction).

Both cases also require a deflection below 60 degrees at the joint.

Node identity is the vertex coordinate: Overpass returns the same node with
bit-identical lat/lon in every way that uses it.

The result is deterministic for a given set of ways: the chain's id is the
smallest member way id, and it is oriented along that way's drawing
direction. Closed ways (roundabouts) are never joined.
"""
from __future__ import annotations

from collections import defaultdict
import math
from typing import Mapping, Optional

from app.services.osm_overpass import Way

_START, _END = 0, 1
End = tuple[int, int]  # (way id, _START | _END)


def _end_coord(way: Way, which: int):
    return way.coords[0] if which == _START else way.coords[-1]


def _outward_bearing(way: Way, which: int) -> Optional[float]:
    """Bearing from the joint into the way, using its adjacent segment."""
    joint = _end_coord(way, which)
    adjacent = way.coords[1] if which == _START else way.coords[-2]
    if joint == adjacent:
        return None  # no direction can be established from a zero-length segment
    lat1, lon1 = map(math.radians, joint)
    lat2, lon2 = map(math.radians, adjacent)
    delta_lon = lon2 - lon1
    return math.degrees(math.atan2(
        math.sin(delta_lon) * math.cos(lat2),
        math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon),
    ))


def _continues(a: Way, a_end: int, b: Way, b_end: int) -> bool:
    bearing_a, bearing_b = _outward_bearing(a, a_end), _outward_bearing(b, b_end)
    if bearing_a is None or bearing_b is None:
        return False
    # One outward bearing must be reversed to describe travel through the joint.
    deflection = abs((bearing_b - bearing_a) % 360.0 - 180.0)
    return deflection < 60.0


def _links(ways: Mapping[int, Way]) -> dict[End, End]:
    """For every way end, the single way end it continues into (if any)."""
    at_node: dict[tuple[float, float], list[End]] = defaultdict(list)
    for way in ways.values():
        if len(way.coords) < 2 or way.coords[0] == way.coords[-1]:
            continue  # closed way (roundabout): stays on its own
        at_node[way.coords[0]].append((way.id, _START))
        at_node[way.coords[-1]].append((way.id, _END))

    links: dict[End, End] = {}
    for ends in at_node.values():
        if len(ends) < 2:
            continue
        groups: dict[tuple[Optional[str], str], list[End]] = defaultdict(list)
        for end in ends:
            way = ways[end[0]]
            groups[(way.name, way.highway)].append(end)
        for (name, _highway), group in groups.items():
            if len(group) != 2 or group[0][0] == group[1][0]:
                continue
            if name is None and len(ends) != 2:
                continue  # unnamed roads only continue where nothing else ends
            a, b = group
            if not _continues(ways[a[0]], a[1], ways[b[0]], b[1]):
                continue
            links[a] = b
            links[b] = a
    return links


def merge_ways(ways: Mapping[int, Way]) -> dict[int, Way]:
    """Stitch ways into chains. Returns ``{chain id: Way}`` where the chain
    id is the smallest member way id and ``coords`` is the joined line.
    Every input way ends up in exactly one chain.
    """
    links = _links(ways)
    done: set[int] = set()                              # ways already in a chain
    chains: list[list[tuple[int, bool]]] = []           # [(way id, reversed?), ...]

    for way_id in sorted(ways):
        if way_id in done:
            continue
        # Walk "backwards" from this way's start to find where the chain
        # begins (or come full circle on a ring of ways).
        first, entered_by = way_id, _START
        seen = {way_id}
        while True:
            prev = links.get((first, entered_by))
            if prev is None:
                break
            if prev[0] in seen:
                # Links pair ends one-to-one, so a repeat means we are back at
                # way_id: a ring. Start it at way_id (its smallest member).
                first, entered_by = way_id, _START
                break
            first, entered_by = prev[0], (_START if prev[1] == _END else _END)
            seen.add(first)

        # Walk forwards from that beginning, recording each way and whether
        # it is traversed against its drawing direction.
        chain: list[tuple[int, bool]] = []
        current, enter = first, entered_by
        while current not in done:
            done.add(current)
            chain.append((current, enter == _END))
            leave = _END if enter == _START else _START
            nxt = links.get((current, leave))
            if nxt is None:
                break
            current, enter = nxt
        chains.append(chain)

    merged: dict[int, Way] = {}
    for chain in chains:
        anchor = min(way_id for way_id, _ in chain)
        # Orient the chain along the anchor way's own direction.
        if next(rev for way_id, rev in chain if way_id == anchor):
            chain = [(way_id, not rev) for way_id, rev in reversed(chain)]
        coords: list[tuple[float, float]] = []
        for way_id, reverse in chain:
            pts = ways[way_id].coords[::-1] if reverse else ways[way_id].coords
            coords.extend(pts if not coords else pts[1:])   # shared node once
        base = ways[anchor]
        # A chain shares name and class; its speed limit is the anchor way's.
        merged[anchor] = Way(id=anchor, coords=tuple(coords), name=base.name, highway=base.highway,
                             maxspeed=base.maxspeed)
    return merged
