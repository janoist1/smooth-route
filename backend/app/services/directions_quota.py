"""Combined daily budget for routing and geocoding requests, per provider.

Reserve before sending, including attempts that fail. Like sv_quota, use an
exclusive file lock and atomic JSON replacement, so processes sharing a file
cannot overbook and a crash can only over-count. Days use Google's Pacific
billing clock. Corrupt/unwritable storage fails closed.

PUBLIC_READ_ONLY defaults to /tmp/smooth-route/quota/{provider counter}.json:
Vercel storage is ephemeral and instance-local, so this is a best-effort cap,
not a deployment-wide limit. Google Cloud API quotas are the hard money cap.
ROUTING_QUOTA_PATH overrides storage; GOOGLE_DIRECTIONS_QUOTA_PATH is the
legacy alias. Google retains its existing google_directions.json counter.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from pathlib import Path
from typing import Callable, Optional

from app.core.config import settings
from app.services.sv_quota import _pacific_now


class RoutingQuotaExceeded(RuntimeError):
    """The daily budget is exhausted or cannot safely be read/written."""


class RoutingQuota:
    def __init__(
        self,
        path: Path | str,
        daily_cap: int,
        now: Callable[[], dt.datetime] = _pacific_now,
    ):
        if daily_cap < 0:
            raise ValueError("daily_cap must be non-negative")
        self.path = Path(path)
        self.daily_cap = daily_cap
        self._now = now

    def _locked(self, update: Optional[Callable[[dict], None]] = None) -> dict:
        """Share sv_quota's lock-file + atomic replacement storage approach."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix(".lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    data = {"version": 1, "days": {}}
                    if self.path.exists():
                        data = json.loads(self.path.read_text(encoding="utf-8"))
                        if (
                            not isinstance(data, dict)
                            or data.get("version") != 1
                            or not isinstance(data.get("days"), dict)
                            or any(type(n) is not int or n < 0 for n in data["days"].values())
                        ):
                            raise ValueError("invalid daily counter")
                    if update is not None:
                        update(data)
                        tmp = self.path.with_suffix(f".tmp{os.getpid()}")
                        tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
                        os.replace(tmp, self.path)
                    return data
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except (OSError, ValueError) as exc:
            raise RoutingQuotaExceeded(
                "Routing/geocoding daily counter is unavailable; try again later"
            ) from exc

    def used(self) -> int:
        return self._locked()["days"].get(self._now().date().isoformat(), 0)

    def reserve(self) -> int:
        """Persist one attempt before the API call, or refuse it without booking."""
        total = 0

        def book(data: dict) -> None:
            nonlocal total
            # Compute the day under the lock, including when waiting at midnight.
            day = self._now().date().isoformat()
            used = data["days"].get(day, 0)
            if used >= self.daily_cap:
                raise RoutingQuotaExceeded(
                    f"Routing/geocoding daily cap reached ({used}/{self.daily_cap}); "
                    "try again after midnight Pacific time"
                )
            total = data["days"][day] = used + 1

        self._locked(book)
        return total


def default_quota(provider: str = "google") -> RoutingQuota:
    """Resolve storage lazily; public deployments never write to the bundle."""
    override = settings.ROUTING_QUOTA_PATH or settings.GOOGLE_DIRECTIONS_QUOTA_PATH
    if override:
        path = Path(override).expanduser()
    else:
        root = Path("/tmp/smooth-route") if settings.PUBLIC_READ_ONLY else Path(settings.resolve_data_dir())
        filename = "google_directions.json" if provider == "google" else "osm_routing.json"
        path = root / "quota" / filename
    cap = settings.ROUTING_DAILY_CAP
    return RoutingQuota(path, cap if cap is not None else settings.GOOGLE_DIRECTIONS_DAILY_CAP)


# Preserve imports and Google counter files used by existing deployments.
DirectionsQuota = RoutingQuota
DirectionsQuotaExceeded = RoutingQuotaExceeded
