"""Street View capture-date helpers (pure, no DB / network).

The Street View Metadata API returns the panorama's capture date as a
month-precision string ("2019-06"; rarely just "2019"). We store it as a DATE
pinned to the first day of the month and expose it back as "YYYY-MM", so no
false day-level precision leaks out.

`backfill_decision` holds the one non-obvious rule for existing points: a
location-based metadata lookup returns the panorama that is live *today*,
which may be newer than the image we downloaded months ago. Only a pano-id
lookup (or a location lookup whose pano predates our download) proves the date
belongs to the stored image.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

# Images older than this are flagged as possibly outdated (UI warning + map dim).
STALE_AFTER_YEARS = 4

_DATE_RE = re.compile(r"^\s*(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?\s*$")


def parse_capture_date(value: Optional[str]) -> Optional[dt.date]:
    """Parse a Metadata API `date` ("YYYY-MM", "YYYY" or "YYYY-MM-DD").

    Returns the first day of that month (January for a bare year), or None for
    missing / malformed / out-of-range input. Never raises.
    """
    if not value or not isinstance(value, str):
        return None
    m = _DATE_RE.match(value)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else 1
    if not (1990 <= year <= 2100) or not (1 <= month <= 12):
        return None
    return dt.date(year, month, 1)


def format_capture_date(value: Optional[dt.date]) -> Optional[str]:
    """DATE → "YYYY-MM" (month precision, as the API reports it)."""
    if value is None:
        return None
    return f"{value.year:04d}-{value.month:02d}"


def capture_age_months(value: Optional[dt.date], today: Optional[dt.date] = None) -> Optional[int]:
    """Whole months between the capture month and `today`'s month (≥ 0)."""
    if value is None:
        return None
    today = today or dt.date.today()
    return max(0, (today.year - value.year) * 12 + (today.month - value.month))


def is_stale_capture(
    value: Optional[dt.date],
    today: Optional[dt.date] = None,
    years: int = STALE_AFTER_YEARS,
) -> bool:
    """True when the capture is more than `years` old. Unknown → False."""
    months = capture_age_months(value, today)
    return months is not None and months > years * 12


def _month_start(value: dt.date | dt.datetime) -> dt.date:
    return dt.date(value.year, value.month, 1)


# Outcomes of backfill_decision.
ACCEPT = "accept"
NEWER_PANO = "newer_pano"  # live pano postdates our image → its date is not ours
NO_DATE = "no_date"  # no pano / no date in the response


def backfill_decision(
    meta: Optional[dict],
    *,
    by_pano_id: bool,
    image_fetched_at: Optional[dt.datetime],
) -> tuple[str, Optional[dt.date]]:
    """Decide whether a metadata response may date an already-stored image.

    - Looked up by the stored pano_id → the date is exactly that panorama's.
    - Looked up by location → only trusted when the live panorama was captured
      strictly before the month we fetched our image (Google publishes with a
      lag of months, so a same-month or later pano cannot be what we stored).
    """
    capture = parse_capture_date((meta or {}).get("date"))
    if capture is None:
        return NO_DATE, None
    if by_pano_id:
        return ACCEPT, capture
    # Without a fetch time there is nothing to prove the pano is ours.
    if image_fetched_at is None or capture >= _month_start(image_fetched_at):
        return NEWER_PANO, None
    return ACCEPT, capture
