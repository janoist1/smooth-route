"""Label queue: pick the unlabelled frames whose human label helps the model most.

Pure logic: no DB, torch or filesystem access, so it is unit-tested in
isolation (backend/tests/test_label_queue.py). label_queue_store.py loads the
inputs from Postgres and writes the labels.

Why these strategies (docs/MODEL_EXPERIMENTS.md, 6th era): a bigger model does
not help; more human labels from more places do. Neighbouring Street View
frames (~10 m apart) are near-duplicates, so labelling the next frame on an
already-labelled street teaches the model almost nothing.

- ``uncertain``: frames whose continuous model score sits close to an ordinal
  cut-point (P(bad) near 0.5 when there is no score), taken round-robin over
  the three boundaries. That is where one label moves a decision boundary.
- ``diverse``: spatial coverage. Frames are thinned to at least
  ``THIN_RADIUS_M`` apart and drawn one per 1 km grid cell per round, emptiest
  cell first. The cells are the same grid as the honest spatial CV groups
  (ml/spatial_cv.py), so every pick from a new cell is also a new CV group.
  Ties prefer Budapest (the model is weakest there), then areas with the fewest
  labels.
- ``mixed`` (default): diverse and uncertain picks interleaved.

Orientation: scores and cut-points here are in the model's fixed severity
orientation (1 = best); the GraphQL layer converts to the canonical scale
(shared/rqi_scale.json).

Every strategy drops frames closer than ``LABEL_RADIUS_M`` to a labelled frame
and never returns two frames from the same panorama or closer than
``DUP_RADIUS_M`` to each other (or to the ids the client already holds).
"""
from __future__ import annotations

import hashlib
import heapq
import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Sequence

# Same projection and grid as ml/spatial_cv.py (grid_cells), so a "cell" here
# is one spatial-CV group there.
M_PER_DEG = 111_320.0
LAT_REF = 47.0
CELL_M = 1000.0

LABEL_RADIUS_M = 50.0   # closer than this to a labelled frame -> excluded
DUP_RADIUS_M = 50.0     # closer than this to another queued frame -> near-duplicate
THIN_RADIUS_M = 150.0   # diverse picks are at least this far apart
UNCERTAINTY_BAND = 0.5  # score distance to a cut-point that still counts as uncertain
UNCERTAINTY_BANDS = 10  # uncertain picks: ties within 1/10 are broken by area

SPRINT_THIN_M = 75.0       # sprint: at most one frame per ~75 m
SPRINT_PATTERN = "DDDB"    # sprint mix: 3 diverse, 1 model-best (repeating)
SPRINT_TARGET = 1000       # labels the learning curve asks for

DEFAULT_CUT_POINTS: tuple[float, ...] = (1.5, 2.5, 3.5)
MAX_LIMIT = 200

# Collection areas, same centroids as ml/build_coords.py (AREAS).
AREAS: dict[str, tuple[float, float]] = {
    "budapest": (47.4981, 19.0713),
    "torokbalint": (47.4330, 18.9002),
    "szekesfehervar": (47.1505, 18.4101),
    "tapolca": (46.8681, 17.3897),
}
AREA_RADIUS_KM = 15.0
OTHER_AREA = "other"
PRIORITY_AREA = "budapest"


class Strategy(str, Enum):
    UNCERTAIN = "uncertain"
    DIVERSE = "diverse"
    MIXED = "mixed"
    # Already-labelled frames, served again blind (pick_recheck): the owner's
    # early labels were made while learning the task.
    RECHECK = "recheck"
    # Labelling sprint (learning curve: ~1000 labels on new streets): diverse
    # with <= 1 frame per SPRINT_THIN_M, plus every 4th frame from the ones the
    # model rates best, so the top level (Kiváló) is covered too.
    SPRINT = "sprint"


@dataclass(frozen=True)
class Frame:
    """An unlabelled candidate frame (image file exists, no manual_rqi)."""
    id: int
    lat: float
    lon: float
    pano_id: Optional[str] = None
    score: Optional[float] = None   # continuous model RQI estimate (1.0-4.0)
    p_bad: Optional[float] = None   # calibrated P(bad = Közepes or worse)


@dataclass(frozen=True)
class QueueItem:
    frame: Frame
    reason: str                     # "uncertain" | "diverse"
    area: str
    uncertainty: Optional[float]    # 0..1, None when the frame has no model score
    cell_labels: int                # labels (+ earlier picks) in its 1 km cell
    boundary: Optional[str] = None  # nearest decision boundary, e.g. "1|2"


@dataclass(frozen=True)
class QueueResult:
    items: list[QueueItem]
    eligible: int                   # candidates left after the exclusions
    scored: int                     # of those, how many carry a model score


# --- geometry ---------------------------------------------------------------

_COS_REF = math.cos(math.radians(LAT_REF))


def to_xy(lat: float, lon: float) -> tuple[float, float]:
    """Local equirectangular metres (error < 1% across Hungary)."""
    return lon * M_PER_DEG * _COS_REF, lat * M_PER_DEG


def grid_cell(lat: float, lon: float, cell_m: float = CELL_M) -> tuple[int, int]:
    """(ky, kx) of the cell_m grid cell, identical to ml/spatial_cv.grid_cells."""
    return (math.floor(lat * M_PER_DEG / cell_m),
            math.floor(lon * M_PER_DEG * _COS_REF / cell_m))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def area_of(lat: float, lon: float) -> str:
    """Nearest collection area within AREA_RADIUS_KM, else "other"."""
    best, best_d = OTHER_AREA, AREA_RADIUS_KM
    for name, (alat, alon) in AREAS.items():
        d = haversine_km(lat, lon, alat, alon)
        if d <= best_d:
            best, best_d = name, d
    return best


class PointIndex:
    """Hash-grid of points for "is anything within r metres?" queries."""

    def __init__(self, bucket_m: float):
        self.bucket = float(bucket_m)
        self._cells: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def add(self, lat: float, lon: float) -> None:
        x, y = to_xy(lat, lon)
        key = (math.floor(x / self.bucket), math.floor(y / self.bucket))
        self._cells.setdefault(key, []).append((x, y))

    def near(self, lat: float, lon: float, radius_m: float) -> bool:
        if radius_m <= 0:
            return False
        x, y = to_xy(lat, lon)
        reach = math.ceil(radius_m / self.bucket)
        bx, by = math.floor(x / self.bucket), math.floor(y / self.bucket)
        r2 = radius_m * radius_m
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for px, py in self._cells.get((bx + dx, by + dy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < r2:
                        return True
        return False


# --- scoring ----------------------------------------------------------------

def boundary(score: Optional[float], p_bad: Optional[float],
             cut_points: Sequence[float] = DEFAULT_CUT_POINTS) -> Optional[int]:
    """Index of the decision boundary the frame sits closest to: 0 = 1|2,
    1 = 2|3 (good/bad), 2 = 3|4. A frame with only P(bad) belongs to the
    good/bad boundary."""
    if score is not None and cut_points:
        return min(range(len(cut_points)), key=lambda k: abs(score - cut_points[k]))
    if p_bad is not None:
        return 1
    return None


def boundary_label(k: Optional[int]) -> Optional[str]:
    return None if k is None else f"{k + 1}|{k + 2}"


def uncertainty(score: Optional[float], p_bad: Optional[float],
                cut_points: Sequence[float] = DEFAULT_CUT_POINTS) -> Optional[float]:
    """0..1, 1 = right on a decision boundary; None without any model output.

    From the distance of the continuous score to the nearest ordinal cut-point
    (UNCERTAINTY_BAND away counts as 0). P(bad) is only the fallback: it is a
    monotone (isotonic, step-shaped) function of the same score, so it adds no
    information and its plateaus would create large ties.
    """
    if score is not None and cut_points:
        margin = min(abs(score - c) for c in cut_points)
        return max(0.0, 1.0 - margin / UNCERTAINTY_BAND)
    if p_bad is not None:
        return max(0.0, 1.0 - abs(p_bad - 0.5) / 0.5)
    return None


def stable_rank(key: object, seed: int = 0) -> float:
    """Deterministic pseudo-random number in [0, 1) per key (stable order
    across requests and processes, so prefetching sees a consistent queue)."""
    digest = hashlib.blake2b(f"{seed}:{key}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2 ** 64


# --- selection --------------------------------------------------------------

def eligible_frames(candidates: Iterable[Frame],
                    labelled: Iterable[tuple[float, float]],
                    exclude_ids: Iterable[int] = (),
                    label_radius_m: float = LABEL_RADIUS_M) -> list[Frame]:
    """Drop excluded ids, frames near a labelled frame and repeat panoramas.

    Of several frames from one panorama (different headings) the one with a
    model score, then the lowest id, is kept.
    """
    excluded = set(exclude_ids)
    labelled_idx = PointIndex(max(label_radius_m, 1.0))
    for lat, lon in labelled:
        labelled_idx.add(lat, lon)

    kept: list[Frame] = []
    seen_pano: set[str] = set()
    ordered = sorted(candidates, key=lambda f: (f.score is None and f.p_bad is None, f.id))
    for f in ordered:
        if f.id in excluded:
            continue
        if f.pano_id:
            if f.pano_id in seen_pano:
                continue
        if labelled_idx.near(f.lat, f.lon, label_radius_m):
            continue
        if f.pano_id:
            seen_pano.add(f.pano_id)
        kept.append(f)
    return kept


def pick_uncertain(frames: Sequence[Frame], limit: int,
                   cut_points: Sequence[float] = DEFAULT_CUT_POINTS,
                   dup_radius_m: float = DUP_RADIUS_M,
                   occupied: Iterable[tuple[float, float]] = (),
                   seed: int = 0) -> list[QueueItem]:
    """Closest to a cut-point first, round-robin over the boundaries (1|2,
    2|3, 3|4) so one boundary cannot crowd out the others (class 2, the
    weakest class, sits on two of them). Near-ties prefer Budapest. No two
    picks within dup_radius_m."""
    lanes: dict[int, list] = {}
    for f in frames:
        u = uncertainty(f.score, f.p_bad, cut_points)
        k = boundary(f.score, f.p_bad, cut_points)
        if u is None or k is None:
            continue
        # Within a 0.1-wide uncertainty band, Budapest (where the model is
        # weakest) goes first; then a seeded random order.
        band = min(math.floor(u * UNCERTAINTY_BANDS), UNCERTAINTY_BANDS - 1)
        in_priority = area_of(f.lat, f.lon) == PRIORITY_AREA
        lanes.setdefault(k, []).append(((-band, not in_priority, stable_rank(f.id, seed)), f, u))
    for lane in lanes.values():
        lane.sort(key=lambda t: t[0])
        lane.reverse()  # pop() from the end = most uncertain first

    taken = PointIndex(max(dup_radius_m, 1.0))
    for lat, lon in occupied:
        taken.add(lat, lon)
    out: list[QueueItem] = []
    order = sorted(lanes)
    while len(out) < limit and any(lanes[k] for k in order):
        for k in order:
            if len(out) >= limit:
                break
            lane = lanes[k]
            while lane:
                _, f, u = lane.pop()
                if taken.near(f.lat, f.lon, dup_radius_m):
                    continue
                taken.add(f.lat, f.lon)
                out.append(QueueItem(frame=f, reason=Strategy.UNCERTAIN.value,
                                     area=area_of(f.lat, f.lon), uncertainty=u,
                                     cell_labels=0, boundary=boundary_label(k)))
                break
    return out


def _area_ranks(labelled: Sequence[tuple[float, float]]) -> dict[str, int]:
    """Budapest first, then areas with the fewest labels (unlabelled "other"
    usually next), name as the final tie-break."""
    counts = {name: 0 for name in (*AREAS, OTHER_AREA)}
    for lat, lon in labelled:
        counts[area_of(lat, lon)] += 1
    order = sorted(counts, key=lambda a: (a != PRIORITY_AREA, counts[a], a))
    return {a: i for i, a in enumerate(order)}


def pick_diverse(frames: Sequence[Frame], labelled: Sequence[tuple[float, float]],
                 limit: int,
                 cut_points: Sequence[float] = DEFAULT_CUT_POINTS,
                 thin_radius_m: float = THIN_RADIUS_M,
                 cell_m: float = CELL_M,
                 occupied: Iterable[tuple[float, float]] = (),
                 seed: int = 0) -> list[QueueItem]:
    """Spatial coverage: emptiest 1 km cell first, one pick per cell per round,
    every pick at least thin_radius_m from labelled frames and other picks.

    ``occupied`` (frames the client already holds) count as picks: they fill
    their cell and block their surroundings.
    """
    occupied = list(occupied)
    cell_count: dict[tuple[int, int], int] = {}
    for lat, lon in (*labelled, *occupied):
        key = grid_cell(lat, lon, cell_m)
        cell_count[key] = cell_count.get(key, 0) + 1

    by_cell: dict[tuple[int, int], list[Frame]] = {}
    for f in frames:
        by_cell.setdefault(grid_cell(f.lat, f.lon, cell_m), []).append(f)
    for members in by_cell.values():
        # Random (seeded) order inside a cell: an unbiased sample of the cell,
        # not just its ambiguous frames (that is the uncertain strategy's job).
        members.sort(key=lambda f: stable_rank(f.id, seed), reverse=True)

    ranks = _area_ranks(labelled)
    cell_area: dict[tuple[int, int], str] = {}
    heap = []
    for key, members in by_cell.items():
        f0 = members[0]
        cell_area[key] = area_of(f0.lat, f0.lon)
        heap.append((cell_count.get(key, 0), ranks[cell_area[key]],
                     stable_rank(key, seed), key))
    heapq.heapify(heap)

    taken = PointIndex(max(thin_radius_m, 1.0))
    for lat, lon in (*labelled, *occupied):
        taken.add(lat, lon)

    out: list[QueueItem] = []
    while heap and len(out) < limit:
        count, rank, tie, key = heapq.heappop(heap)
        members = by_cell[key]
        pick = None
        while members:
            f = members.pop()
            if not taken.near(f.lat, f.lon, thin_radius_m):
                pick = f
                break
        if pick is None:
            continue  # cell exhausted (everything left is too close)
        taken.add(pick.lat, pick.lon)
        out.append(QueueItem(frame=pick, reason=Strategy.DIVERSE.value,
                             area=cell_area[key],
                             uncertainty=uncertainty(pick.score, pick.p_bad, cut_points),
                             cell_labels=count,
                             boundary=boundary_label(boundary(pick.score, pick.p_bad,
                                                              cut_points))))
        if members:
            heapq.heappush(heap, (count + 1, rank, tie, key))
    return out


def interleave(first: Sequence[QueueItem], second: Sequence[QueueItem], limit: int,
               dup_radius_m: float = DUP_RADIUS_M,
               occupied: Iterable[tuple[float, float]] = ()) -> list[QueueItem]:
    """Alternate first/second, skipping repeats and near-duplicates; when one
    list runs out the other continues."""
    taken = PointIndex(max(dup_radius_m, 1.0))
    for lat, lon in occupied:
        taken.add(lat, lon)
    ids: set[int] = set()
    out: list[QueueItem] = []
    a, b = list(first), list(second)
    ia = ib = 0
    turn = 0
    while len(out) < limit and (ia < len(a) or ib < len(b)):
        use_a = (turn % 2 == 0 and ia < len(a)) or ib >= len(b)
        if use_a:
            item, ia = a[ia], ia + 1
        else:
            item, ib = b[ib], ib + 1
        f = item.frame
        if f.id in ids or taken.near(f.lat, f.lon, dup_radius_m):
            continue
        ids.add(f.id)
        taken.add(f.lat, f.lon)
        out.append(item)
        turn += 1
    return out


def pick_model_best(frames: Sequence[Frame], limit: int,
                    dup_radius_m: float = THIN_RADIUS_M,
                    occupied: Iterable[tuple[float, float]] = (),
                    seed: int = 0) -> list[QueueItem]:
    """Frames the model rates best (lowest severity score) first, Budapest
    first within 0.1-level bands, spread out; covers the top level."""
    scored = [f for f in frames if f.score is not None]
    scored.sort(key=lambda f: (round(f.score or 0.0, 1), area_of(f.lat, f.lon) != PRIORITY_AREA,
                               stable_rank(f.id, seed)))
    taken = PointIndex(max(dup_radius_m, 1.0))
    for lat, lon in occupied:
        taken.add(lat, lon)
    out: list[QueueItem] = []
    for f in scored:
        if len(out) >= limit:
            break
        if taken.near(f.lat, f.lon, dup_radius_m):
            continue
        taken.add(f.lat, f.lon)
        out.append(QueueItem(frame=f, reason="model_best", area=area_of(f.lat, f.lon),
                             uncertainty=None, cell_labels=0))
    return out


def merge_by_pattern(lists: dict[str, Sequence[QueueItem]], pattern: str, limit: int,
                     dup_radius_m: float = DUP_RADIUS_M,
                     occupied: Iterable[tuple[float, float]] = ()) -> list[QueueItem]:
    """Take from ``lists`` in the repeating ``pattern`` order (e.g. "DDDB"),
    skipping repeats and near-duplicates; a dry list yields to the others."""
    taken = PointIndex(max(dup_radius_m, 1.0))
    for lat, lon in occupied:
        taken.add(lat, lon)
    pos = {k: 0 for k in lists}
    ids: set[int] = set()
    out: list[QueueItem] = []
    step = 0
    while len(out) < limit and any(pos[k] < len(v) for k, v in lists.items()):
        key = pattern[step % len(pattern)]
        step += 1
        if pos[key] >= len(lists[key]):
            key = next(k for k in pattern if pos[k] < len(lists[k]))
        item = lists[key][pos[key]]
        pos[key] += 1
        f = item.frame
        if f.id in ids or taken.near(f.lat, f.lon, dup_radius_m):
            continue
        ids.add(f.id)
        taken.add(f.lat, f.lon)
        out.append(item)
    return out


PAIR_MAX_GAP = 0.25        # model scores this close -> an informative pair
PAIR_MIN_APART_M = 500.0   # two different streets, not two views of one spot
PAIR_LOOKAHEAD = 25


def pick_pairs(frames: Sequence[Frame], limit: int,
               judged: Iterable[tuple[int, int]] = (),
               exclude_ids: Iterable[int] = (),
               max_gap: float = PAIR_MAX_GAP,
               min_apart_m: float = PAIR_MIN_APART_M,
               seed: int = 0) -> list[tuple[Frame, Frame, float]]:
    """Pairs (a, b, |score gap|) for "which is worse?": the model scores both
    within ``max_gap`` (it cannot tell them apart, so the human answer
    teaches most), at least ``min_apart_m`` apart, each frame once per batch,
    never a pair judged before. Starting points are spread over the whole
    score range in a seeded random order."""
    done = {frozenset(p) for p in judged}
    excluded = set(exclude_ids)
    scored = sorted((f for f in frames if f.score is not None and f.id not in excluded),
                    key=lambda f: (f.score, f.id))
    order = sorted(range(len(scored)), key=lambda i: stable_rank(scored[i].id, seed))
    used: set[int] = set()
    out: list[tuple[Frame, Frame, float]] = []
    for i in order:
        if len(out) >= limit:
            break
        a = scored[i]
        if a.id in used:
            continue
        for j in range(i + 1, min(i + 1 + PAIR_LOOKAHEAD, len(scored))):
            b = scored[j]
            gap = (b.score or 0.0) - (a.score or 0.0)  # both scored (filtered above)
            if gap > max_gap:
                break
            if b.id in used or frozenset((a.id, b.id)) in done:
                continue
            ax, ay = to_xy(a.lat, a.lon)
            bx, by = to_xy(b.lat, b.lon)
            if math.hypot(ax - bx, ay - by) < min_apart_m:
                continue
            # Random side, so position is never a cue.
            pair = (a, b) if stable_rank((a.id, b.id), seed) < 0.5 else (b, a)
            out.append((pair[0], pair[1], gap))
            used.update((a.id, b.id))
            break
    return out


def pick_recheck(frames: Sequence[Frame], level_of: dict[int, int],
                 suspicious_ids: Sequence[int], limit: int,
                 levels: Sequence[int], exclude_ids: Iterable[int] = (),
                 seed: int = 0) -> list[QueueItem]:
    """Labelled frames to rate again, blind.

    First the ``suspicious_ids`` in their given (priority) order: frames whose
    human label disagrees with both the model and the VLM. Then a random
    sample stratified by the old label, the consistency control. Round-robin
    selection keeps the per-level counts; a separate seeded shuffle hides
    the old label's position. ``frames`` must already exclude frames
    re-checked before; ``level_of`` maps frame id -> old level (never sent to
    the client).
    """
    excluded = set(exclude_ids)
    by_id = {f.id: f for f in frames if f.id not in excluded}
    out: list[QueueItem] = []
    for fid in suspicious_ids:
        if len(out) >= limit:
            return out
        f = by_id.pop(fid, None)
        if f is not None:
            out.append(QueueItem(frame=f, reason="recheck_suspicious",
                                 area=area_of(f.lat, f.lon), uncertainty=None,
                                 cell_labels=0))
    strata: dict[int, list[Frame]] = {lv: [] for lv in levels}
    for f in by_id.values():
        lv = level_of.get(f.id)
        if lv in strata:
            strata[lv].append(f)
    for members in strata.values():
        members.sort(key=lambda f: stable_rank(f.id, seed), reverse=True)
    sample_start = len(out)
    while len(out) < limit and any(strata.values()):
        for lv in levels:
            if len(out) >= limit:
                break
            if strata[lv]:
                f = strata[lv].pop()
                out.append(QueueItem(frame=f, reason="recheck_sample",
                                     area=area_of(f.lat, f.lon), uncertainty=None,
                                     cell_labels=0))
    out[sample_start:] = sorted(
        out[sample_start:],
        key=lambda item: (stable_rank(("recheck_order", item.frame.id), seed), item.frame.id),
    )
    return out


def consistency_stats(histories: Iterable[list], scale, reason: Optional[str] = None) -> dict:
    """Owner's self-consistency from relabel_history lists: the ORIGINAL label
    (first entry's old) against the latest re-check (last entry's new), both on
    the canonical scale of ``scale`` (an app.core.rqi_scale.RqiScale, passed in
    so ml/label_consistency.py can load this module without the backend app).
    Per old level: n, exact share, within-one share.

    ``reason`` keeps only frames whose first re-check had that queue reason:
    the noise ceiling must come from "recheck_sample" (random control), not
    from "recheck_suspicious" frames, which were picked because they look wrong.
    """
    per: dict[int, list[int]] = {}
    for hist in histories:
        if not hist:
            continue
        first, last = hist[0], hist[-1]
        if reason is not None and first.get("reason") != reason:
            continue
        try:
            old = scale.convert(float(first["old"]), first.get("direction", scale.direction))
            new = scale.convert(float(last["new"]), last.get("direction", scale.direction))
        except (KeyError, TypeError, ValueError):
            continue
        bucket = per.setdefault(int(scale.nearest(old)), [0, 0, 0])
        bucket[0] += 1
        bucket[1] += abs(new - old) < 1e-9
        bucket[2] += abs(new - old) <= 1 + 1e-9

    def share(n, k):
        return round(k / n, 3) if n else None

    n, same, near = (sum(b[i] for b in per.values()) for i in range(3))
    return {
        "n": n, "same": share(n, same), "within_one": share(n, near),
        "per_level": {lv: {"n": b[0], "same": share(*b[:2]), "within_one": share(b[0], b[2])}
                      for lv, b in sorted(per.items())},
    }


def build_queue(candidates: Iterable[Frame],
                labelled: Iterable[tuple[float, float]],
                strategy: Strategy | str = Strategy.MIXED,
                limit: int = 20,
                *,
                cut_points: Sequence[float] = DEFAULT_CUT_POINTS,
                exclude_ids: Iterable[int] = (),
                label_radius_m: float = LABEL_RADIUS_M,
                dup_radius_m: float = DUP_RADIUS_M,
                thin_radius_m: float = THIN_RADIUS_M,
                cell_m: float = CELL_M,
                seed: int = 0) -> QueueResult:
    """The next ``limit`` frames to label.

    ``exclude_ids`` are frames the client already holds (queued, skipped or
    just rated): they are never returned, and their surroundings count as
    taken, so a follow-up request does not serve their near-duplicates.
    """
    strategy = Strategy(strategy)
    if strategy is Strategy.RECHECK:
        raise ValueError("recheck serves labelled frames: use pick_recheck")
    limit = max(0, min(int(limit), MAX_LIMIT))
    candidates = list(candidates)
    labelled = list(labelled)
    excluded = set(exclude_ids)
    occupied = [(f.lat, f.lon) for f in candidates if f.id in excluded]

    frames = eligible_frames(candidates, labelled, excluded, label_radius_m)
    scored = sum(1 for f in frames if f.score is not None or f.p_bad is not None)
    if limit == 0 or not frames:
        return QueueResult(items=[], eligible=len(frames), scored=scored)

    def uncertain(n: int) -> list[QueueItem]:
        return pick_uncertain(frames, n, cut_points, dup_radius_m, occupied, seed)

    def diverse(n: int) -> list[QueueItem]:
        return pick_diverse(frames, labelled, n, cut_points, thin_radius_m, cell_m,
                            occupied, seed)

    if strategy is Strategy.SPRINT:
        diverse_75 = pick_diverse(frames, labelled, limit, cut_points, SPRINT_THIN_M, cell_m,
                                  occupied, seed)
        best = pick_model_best(frames, limit, SPRINT_THIN_M, occupied, seed)
        items = merge_by_pattern({"D": diverse_75, "B": best}, SPRINT_PATTERN, limit,
                                 dup_radius_m, occupied)
    elif strategy is Strategy.UNCERTAIN:
        items = uncertain(limit)
    elif strategy is Strategy.DIVERSE:
        items = diverse(limit)
    else:
        # Over-fetch both halves: the merge drops cross-list near-duplicates.
        items = interleave(diverse(limit), uncertain(limit), limit, dup_radius_m,
                           occupied)
    return QueueResult(items=items, eligible=len(frames), scored=scored)
