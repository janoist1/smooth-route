"""Collect Street View frames at planned road points (core loop, no DB code).

``network_sampling`` decides WHERE; this module does the per-point work
through the quota-guarded ``sv_client`` and a ``FrameStore``:

    metadata (free) → no panorama? skip
                    → panorama already stored / already seen? skip
                    → panorama not on this road? skip
                    → a stored frame within a few metres? skip
    image (billed)  → booked on the monthly + job budget first
                    → saved exactly like the training frames
                      (600×400, pitch −20, heading = road bearing)

Every decision is appended to a resume log (JSON lines), so an interrupted
job continues where it stopped and never asks Google twice about a point.

How a run ends:
- plan finished,
- budget reached (``QuotaExceeded`` — monthly cap, job cap or the megabyte
  ceiling): a clean, expected stop,
- trouble (``StreetViewFatal`` — HTTP 403/429, quota/billing/key status):
  the job stops at once and says so,
- the operator's Ctrl-C.
In every case the log is complete up to the last point handled.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Hashable, Mapping, Optional, Protocol, Sequence

from app.services.capture_date import parse_capture_date
from app.services.map_matching import DEFAULT_MAX_DISTANCE_M, Line, LineIndex
from app.services.network_sampling import Candidate, Cell, bearing_at_offset
from app.services.segment_geometry import cumulative_lengths
from app.services.sv_client import (
    DEFAULT_PITCH,
    StreetViewClient,
    StreetViewError,
    StreetViewFatal,
)
from app.services.sv_quota import JobBudget, QuotaExceeded

SAVED = "saved"
NO_PANO = "no_pano"
DUP_PANO = "dup_pano"
OFF_ROAD = "off_road"
NEAR_EXISTING = "near_existing"
META_ERROR = "meta_error"
IMAGE_ERROR = "image_error"
BAD_IMAGE = "bad_image"

# A real 600×400 road photo is tens of kilobytes; anything tiny is an error
# placeholder, not a frame.
MIN_IMAGE_BYTES = 5_000
NEAR_EXISTING_M = 5.0

STOP_DONE = "plan finished"
STOP_BUDGET = "budget reached"
STOP_TROUBLE = "stopped on a quota / billing / key signal"
STOP_INTERRUPT = "interrupted by the operator"


@dataclass(frozen=True)
class NewFrame:
    lat: float
    lon: float
    heading: float
    pitch: float
    pano_id: str
    capture_date: Optional[dt.date]


class FrameStore(Protocol):
    def has_pano(self, pano_id: str) -> bool: ...
    def near_existing(self, lat: float, lon: float, radius_m: float) -> bool: ...
    def save(self, frame: NewFrame, jpeg: bytes) -> int: ...


class ResumeLog:
    """Append-only JSON-lines record of every handled candidate."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.status: dict[str, str] = {}
        self.frame_ids: list[int] = []
        self.bytes_saved = 0
        if self.path.is_file():
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue  # a torn last line after a crash
                    self._apply(entry)

    def _apply(self, entry: dict) -> None:
        self.status[entry["k"]] = entry["s"]
        if entry["s"] == SAVED and entry.get("id") is not None:
            self.frame_ids.append(int(entry["id"]))
            self.bytes_saved += int(entry.get("b", 0))

    def __contains__(self, key: str) -> bool:
        return key in self.status

    def add(self, key: str, status: str, frame_id: Optional[int] = None, size: int = 0) -> None:
        entry = {"k": key, "s": status}
        if frame_id is not None:
            entry.update(id=frame_id, b=size)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        self._apply(entry)

    def counts(self) -> Counter:
        return Counter(self.status.values())


@dataclass
class RunResult:
    stop: str = STOP_DONE
    detail: str = ""
    counts: Counter = field(default_factory=Counter)   # this run only
    cells_done: int = 0


def is_jpeg(data: bytes) -> bool:
    return len(data) >= MIN_IMAGE_BYTES and data[:2] == b"\xff\xd8"


def process_candidate(
    candidate: Candidate,
    *,
    client: StreetViewClient,
    store: FrameStore,
    index: LineIndex,
    lines: Mapping[Hashable, Line],
    seen_panos: set,
    job: Optional[JobBudget],
    radius_m: float,
) -> tuple[str, Optional[int], int]:
    """Handle one planned point. Returns (status, frame id, bytes saved).
    ``QuotaExceeded`` / ``StreetViewFatal`` propagate: they end the run."""
    try:
        meta = client.metadata(candidate.lat, candidate.lon, radius=max(1, round(radius_m)))
    except StreetViewError:
        return META_ERROR, None, 0
    if not meta or not meta.get("pano_id") or meta.get("lat") is None or meta.get("lng") is None:
        return NO_PANO, None, 0

    pano_id = meta["pano_id"]
    if pano_id in seen_panos or store.has_pano(pano_id):
        return DUP_PANO, None, 0

    # The panorama must sit on the road we planned for — Google may answer
    # with one on a side street or the opposite carriageway. (Not marked as
    # seen: the road it does belong to may still want it.)
    position = (meta["lat"], meta["lng"])
    match = index.snap(position, candidate.heading, max_distance_m=DEFAULT_MAX_DISTANCE_M)
    if match is None or match.line_id != candidate.line_id:
        return OFF_ROAD, None, 0
    if store.near_existing(position[0], position[1], NEAR_EXISTING_M):
        return NEAR_EXISTING, None, 0
    seen_panos.add(pano_id)

    line = lines[candidate.line_id]
    heading = bearing_at_offset(line.coords, cumulative_lengths(line.coords), match.offset_m)
    try:
        jpeg = client.image(pano_id=pano_id, heading=round(heading, 2), pitch=DEFAULT_PITCH, job=job)
    except StreetViewError:
        return IMAGE_ERROR, None, 0
    if not is_jpeg(jpeg):
        return BAD_IMAGE, None, 0

    frame_id = store.save(
        NewFrame(position[0], position[1], round(heading, 2), DEFAULT_PITCH, pano_id,
                 parse_capture_date(meta.get("date"))),
        jpeg,
    )
    return SAVED, frame_id, len(jpeg)


def run_plan(
    plan: Sequence[tuple[Cell, Sequence[Candidate]]],
    *,
    client: StreetViewClient,
    store: FrameStore,
    lines: Mapping[Hashable, Line],
    resume: ResumeLog,
    job: Optional[JobBudget] = None,
    radius_m: float = 25.0,
    max_bytes: Optional[int] = None,
    on_progress: Optional[Callable[[RunResult, ResumeLog], None]] = None,
    progress_every: int = 1000,
) -> RunResult:
    """Work through the plan cell by cell until it is done or something says
    stop. Candidates already in the resume log are skipped silently."""
    result = RunResult()
    index = LineIndex(lines.values())
    seen_panos: set = set()
    saved_at_last_note = len(resume.frame_ids)
    try:
        for _cell, candidates in plan:
            for candidate in candidates:
                if candidate.key in resume:
                    continue
                if max_bytes is not None and resume.bytes_saved >= max_bytes:
                    raise QuotaExceeded(
                        f"megabyte ceiling reached ({resume.bytes_saved / 1e6:.0f} MB)")
                status, frame_id, size = process_candidate(
                    candidate, client=client, store=store, index=index, lines=lines,
                    seen_panos=seen_panos, job=job, radius_m=radius_m,
                )
                resume.add(candidate.key, status, frame_id, size)
                result.counts[status] += 1
                if (on_progress is not None
                        and len(resume.frame_ids) - saved_at_last_note >= progress_every):
                    saved_at_last_note = len(resume.frame_ids)
                    on_progress(result, resume)
            result.cells_done += 1
    except QuotaExceeded as stop:
        result.stop, result.detail = STOP_BUDGET, str(stop)
    except StreetViewFatal as stop:
        result.stop, result.detail = STOP_TROUBLE, str(stop)
    except KeyboardInterrupt:
        result.stop = STOP_INTERRUPT
    return result
