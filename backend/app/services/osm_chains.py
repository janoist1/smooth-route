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

Node identity is the vertex coordinate: Overpass returns the same node with
bit-identical lat/lon in every way that uses it.

The result is deterministic for a given set of ways: the chain's id is the
smallest member way id, and it is oriented along that way's drawing
direction. Closed ways (roundabouts) are never joined.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Optional

from app.services.osm_overpass import Way

_START, _END = 0, 1
End = tuple[int, int]  # (way id, _START | _END)


def _end_coord(way: Way, which: int):
    return way.coords[0] if which == _START else way.coords[-1]


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
            links[a] = b
            links[b] = a
    return links


def merge_ways(ways: Mapping[int, Way]) -> dict[int, Way]:
    """Stitch ways into chains. Returns ``{chain id: Way}`` where the chain
    id is the smallest member way id and ``coords`` is the joined line.
    Every input way ends up in exactly one chain.
    """
    links = _links(ways)
    member_of: dict[int, list[tuple[int, bool]]] = {}   # way id → its chain (shared list)
    chains: list[list[tuple[int, bool]]] = []

    for way_id in sorted(ways):
        if way_id in member_of:
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
        visited: set[int] = set()
        while current not in visited:
            visited.add(current)
            chain.append((current, enter == _END))
            member_of[current] = chain
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
        merged[anchor] = Way(id=anchor, coords=tuple(coords), name=base.name, highway=base.highway)
    return merged


def chain_members(ways: Mapping[int, Way]) -> dict[int, int]:
    """``{way id: chain id}`` for the same input (diagnostics / tests)."""
    links = _links(ways)
    parent = {way_id: way_id for way_id in ways}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, _), (b, _) in links.items():
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {way_id: find(way_id) for way_id in ways}
