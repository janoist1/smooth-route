"""Street View request budget: one persistent counter per calendar month.

Street View Static images are billed per request against a MONTHLY quota that
must never be exceeded. Every image request in this code base goes through
``StreetViewQuota.reserve`` (via ``sv_client.StreetViewClient``), which

- refuses the request BEFORE it is sent when the month's cap or the job's own
  cap would be exceeded (``QuotaExceeded``), and
- records it on disk first, so a crash can only over-count, never under-count.

The counter is a small JSON file in the shared data directory
(``data/quota/street_view.json``), updated under an exclusive file lock and
replaced atomically — every process and git worktree on the machine shares
one number. A file rather than a DB table on purpose: the scripts that fetch
images must be stoppable by the guard even when no database is around, and it
needs no migration.

Months follow Google's billing clock (US Pacific time), not local time, so
the counter cannot roll over hours before Google's does.

Metadata requests are free; they are counted for visibility only.

Config (env or the repo-root ``.env``):
    GOOGLE_SV_MONTHLY_CAP   images per month, default 5000 (hard stop)
    GOOGLE_SV_JOB_CAP       default per-job cap, 1500
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

DEFAULT_MONTHLY_CAP = 5000
DEFAULT_JOB_CAP = 1500

KIND_IMAGE = "static_images"
KIND_METADATA = "metadata"


class QuotaExceeded(RuntimeError):
    """The request would exceed the monthly or the per-job image cap."""


def _pacific_now() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:  # no tz database: fixed UTC-8 (never rolls over early)
        return dt.datetime.now(dt.timezone(dt.timedelta(hours=-8)))


def month_key(moment: dt.datetime) -> str:
    return f"{moment.year:04d}-{moment.month:02d}"


def cap_from_env(name: str, default: int) -> int:
    """A non-negative integer cap from the environment; junk → the default
    (never "unlimited")."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


@dataclass
class JobBudget:
    """Per-job image allowance, enforced together with the monthly cap."""

    cap: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)


class StreetViewQuota:
    def __init__(
        self,
        path: Path | str,
        monthly_cap: Optional[int] = None,
        now: Callable[[], dt.datetime] = _pacific_now,
    ):
        self.path = Path(path)
        self.monthly_cap = (
            cap_from_env("GOOGLE_SV_MONTHLY_CAP", DEFAULT_MONTHLY_CAP)
            if monthly_cap is None else int(monthly_cap)
        )
        self._now = now

    # -- storage ------------------------------------------------------------
    def _locked(self, update: Optional[Callable[[dict], None]] = None) -> dict:
        """Read the counter file under an exclusive lock; with ``update``,
        mutate and write it back atomically before releasing the lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(".lock")
        with open(lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = {"version": 1, "months": {}}
                if self.path.is_file():
                    try:
                        loaded = json.loads(self.path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        # Never guess a count: a broken file blocks requests
                        # until someone looks at it.
                        raise QuotaExceeded(
                            f"quota file {self.path} is unreadable ({exc}); "
                            "fix or remove it deliberately before fetching images"
                        ) from exc
                    if isinstance(loaded, dict) and isinstance(loaded.get("months"), dict):
                        data = loaded
                if update is not None:
                    update(data)
                    tmp = self.path.with_suffix(f".tmp{os.getpid()}")
                    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
                    os.replace(tmp, self.path)
                return data
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _month(self, data: dict, key: str) -> dict:
        return data["months"].setdefault(key, {KIND_IMAGE: 0, KIND_METADATA: 0})

    # -- reads --------------------------------------------------------------
    def used(self, kind: str = KIND_IMAGE) -> int:
        key = month_key(self._now())
        return int(self._locked()["months"].get(key, {}).get(kind, 0))

    def remaining(self) -> int:
        return max(0, self.monthly_cap - self.used())

    # -- writes -------------------------------------------------------------
    def reserve(self, n: int = 1, job: Optional[JobBudget] = None) -> int:
        """Book ``n`` image requests for this month (and this job) or raise
        ``QuotaExceeded`` without booking anything. Returns the month's new
        total. Call it BEFORE sending the request."""
        if n <= 0:
            raise ValueError("n must be positive")
        if job is not None and job.used + n > job.cap:
            raise QuotaExceeded(
                f"per-job image cap reached ({job.used}/{job.cap}); "
                "raise --job-cap deliberately to continue"
            )
        key = month_key(self._now())
        total = 0

        def book(data: dict) -> None:
            nonlocal total
            month = self._month(data, key)
            if month[KIND_IMAGE] + n > self.monthly_cap:
                raise QuotaExceeded(
                    f"monthly Street View image cap reached for {key} "
                    f"({month[KIND_IMAGE]}/{self.monthly_cap}); "
                    "set GOOGLE_SV_MONTHLY_CAP deliberately to continue"
                )
            month[KIND_IMAGE] += n
            data["updated_at"] = self._now().isoformat(timespec="seconds")
            total = month[KIND_IMAGE]

        self._locked(book)
        if job is not None:
            job.used += n
        return total

    def note_metadata(self, n: int = 1) -> None:
        """Count free metadata requests (visibility only, no cap)."""
        key = month_key(self._now())

        def book(data: dict) -> None:
            self._month(data, key)[KIND_METADATA] += n

        self._locked(book)

    def set_used(self, images: int) -> None:
        """Set this month's image count (e.g. to the Google Cloud console's
        number when images were fetched before this counter existed)."""
        if images < 0:
            raise ValueError("images must be >= 0")
        key = month_key(self._now())

        def book(data: dict) -> None:
            self._month(data, key)[KIND_IMAGE] = int(images)

        self._locked(book)

    def summary(self) -> str:
        key = month_key(self._now())
        month = self._locked()["months"].get(key, {})
        return (f"Street View {key}: {int(month.get(KIND_IMAGE, 0))}/{self.monthly_cap} images, "
                f"{int(month.get(KIND_METADATA, 0))} metadata requests")


def default_quota() -> StreetViewQuota:
    """The shared counter in the canonical data directory."""
    from app.core.paths import data_path

    return StreetViewQuota(data_path("quota", "street_view.json"))
