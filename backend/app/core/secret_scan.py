"""Find credentials in data about to leave the machine (publish to Neon).

Pure and dependency-free. Returns locations only, never the secret values.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

SECRET_PATTERNS = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "url_key_param": re.compile(r"[?&](?:key|api_key|apikey|token|signature)=[^&\s]{8,}", re.I),
    "clerk_secret": re.compile(r"sk_(?:test|live)_[0-9A-Za-z]{20,}"),
    "neon_password": re.compile(r"\bnpg_[A-Za-z0-9]{8,}"),
    "db_url_with_password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/@]+:[^@\s]+@"),
}


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, (int, float, bool)):
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def find_secrets(
    rows: Iterable[Mapping[str, Any]], id_key: str = "id"
) -> list[tuple[Any, str, str]]:
    """[(row id, column, pattern name), ...] for every value matching a pattern."""
    hits = []
    for row in rows:
        for column, value in row.items():
            text = _as_text(value)
            if not text:
                continue
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    hits.append((row.get(id_key), column, name))
    return hits
