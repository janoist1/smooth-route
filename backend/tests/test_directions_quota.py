"""Daily Google budget: persistence, Pacific rollover and concurrent reservations."""
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services.directions_quota import DirectionsQuota, DirectionsQuotaExceeded, default_quota


def test_daily_cap_persists_and_blocks_after_limit(tmp_path):
    path = tmp_path / "quota" / "directions.json"
    quota = DirectionsQuota(path, daily_cap=2)
    assert quota.used() == 0
    assert quota.reserve() == 1
    assert DirectionsQuota(path, daily_cap=2).reserve() == 2
    with pytest.raises(DirectionsQuotaExceeded, match="daily cap reached"):
        quota.reserve()
    assert quota.used() == 2
    assert not list(path.parent.glob("*.tmp*"))


def test_daily_cap_rolls_over_at_pacific_midnight(tmp_path):
    pacific = dt.timezone(dt.timedelta(hours=-8))
    moment = dt.datetime(2026, 11, 26, 23, 59, tzinfo=pacific)
    quota = DirectionsQuota(tmp_path / "directions.json", 1, now=lambda: moment)
    quota.reserve()
    with pytest.raises(DirectionsQuotaExceeded):
        quota.reserve()
    moment += dt.timedelta(minutes=1)
    assert quota.used() == 0
    assert quota.reserve() == 1
    assert json.loads(quota.path.read_text())["days"] == {"2026-11-26": 1, "2026-11-27": 1}


def test_zero_cap_blocks_every_call(tmp_path):
    quota = DirectionsQuota(tmp_path / "directions.json", 0)
    with pytest.raises(DirectionsQuotaExceeded, match="0/0"):
        quota.reserve()
    assert quota.used() == 0


def test_concurrent_reservations_share_one_limit(tmp_path):
    path = tmp_path / "directions.json"

    def reserve(_):
        try:
            DirectionsQuota(path, 5).reserve()
            return 1
        except DirectionsQuotaExceeded:
            return 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(40))) == 5
    assert DirectionsQuota(path, 5).used() == 5


@pytest.mark.parametrize("content", [
    "{broken", "[]", '{}', '{"version":1,"days":[]}',
    '{"version":1,"days":{"2026-11-26":-1}}',
    '{"version":1,"days":{"2026-11-26":"0"}}',
])
def test_invalid_counter_fails_closed(tmp_path, content):
    path = tmp_path / "directions.json"
    path.write_text(content)
    with pytest.raises(DirectionsQuotaExceeded, match="counter is unavailable"):
        DirectionsQuota(path, 300).reserve()
    assert path.read_text() == content


def test_unwritable_counter_fails_closed(tmp_path):
    parent = tmp_path / "file-not-directory"
    parent.write_text("occupied")
    with pytest.raises(DirectionsQuotaExceeded, match="counter is unavailable"):
        DirectionsQuota(parent / "directions.json", 300).reserve()


def test_default_cap_and_env_override(monkeypatch):
    monkeypatch.delenv("GOOGLE_DIRECTIONS_DAILY_CAP", raising=False)
    assert Settings(_env_file=None).GOOGLE_DIRECTIONS_DAILY_CAP == 300
    monkeypatch.setenv("GOOGLE_DIRECTIONS_DAILY_CAP", "17")
    assert Settings(_env_file=None).GOOGLE_DIRECTIONS_DAILY_CAP == 17
    monkeypatch.setenv("GOOGLE_DIRECTIONS_DAILY_CAP", "-1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_counter_paths_follow_mode_and_override(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "GOOGLE_DIRECTIONS_QUOTA_PATH", None)
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", False)
    assert default_quota().path == tmp_path / "quota" / "google_directions.json"
    monkeypatch.setattr(settings, "PUBLIC_READ_ONLY", True)
    assert str(default_quota().path) == "/tmp/smooth-route/quota/google_directions.json"
    override = tmp_path / "override.json"
    monkeypatch.setenv("GOOGLE_DIRECTIONS_QUOTA_PATH", str(override))
    configured = Settings(_env_file=None)
    monkeypatch.setattr(settings, "GOOGLE_DIRECTIONS_QUOTA_PATH", configured.GOOGLE_DIRECTIONS_QUOTA_PATH)
    assert default_quota().path == override
