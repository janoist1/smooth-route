"""Naive-UTC timestamps without the deprecated ``datetime.utcnow()``.

The DB columns are timezone-naive ``DateTime`` holding UTC, so this keeps the
exact semantics of ``datetime.utcnow()`` (naive, UTC) — only the deprecation
warning (Python 3.12+) goes away.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
