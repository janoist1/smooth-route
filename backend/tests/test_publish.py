"""publish.py helpers: no DB needed (Alembic scripts are read from disk)."""
import importlib.util
from pathlib import Path

import pytest

PUBLISH_PATH = Path(__file__).resolve().parents[1] / "scripts" / "publish.py"


def _load():
    spec = importlib.util.spec_from_file_location("publish_under_test", PUBLISH_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def publish():
    return _load()


def test_replace_never_truncates(publish):
    # TRUNCATE takes ACCESS EXCLUSIVE until commit: the live site would hang.
    stmts = publish.replace_statements()
    assert stmts == ["DELETE FROM street_view_images", "DELETE FROM road_segments"]
    assert not any("TRUNCATE" in s.upper() for s in stmts)


def test_alembic_url_escapes_percent(publish):
    from app.core.migrations import alembic_config

    url = "postgresql://u:p%40ss@host/db?sslmode=require"
    cfg = alembic_config()
    cfg.set_main_option("sqlalchemy.url", publish.alembic_url(url))
    assert cfg.get_main_option("sqlalchemy.url") == url


def test_pending_revisions_from_round1(publish):
    from app.core.migrations import alembic_config

    cfg = alembic_config()
    head = publish.pending_revisions(cfg, None)
    assert head[0] == "0001"
    # Round 1 on Neon stopped at 0003 (pano_id); the release applies the rest.
    pending = publish.pending_revisions(cfg, "0003")
    assert pending[:3] == ["0004", "0005", "0006"]
    assert pending == head[3:]
    assert publish.pending_revisions(cfg, head[-1]) == []


def test_pending_revisions_unknown_target(publish):
    from app.core.migrations import alembic_config

    with pytest.raises(SystemExit, match="unknown revision"):
        publish.pending_revisions(alembic_config(), "9999")


# --- smoke_public_api.py (stdlib; pure helpers only) -------------------------


def _load_smoke():
    path = PUBLISH_PATH.parent / "smoke_public_api.py"
    spec = importlib.util.spec_from_file_location("smoke_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_smoke_scale_direction():
    smoke = _load_smoke()
    good = [{"rqi": 5, "pBad": 0.05}, {"rqi": 4, "pBad": 0.1}, {"rqi": 1, "pBad": 0.9}]
    flipped = [{**s, "rqi": 6 - s["rqi"]} for s in good]
    assert smoke.scale_direction(good) == "higher_is_better"
    assert smoke.scale_direction(flipped) == "lower_is_better"
    assert smoke.scale_direction([{"rqi": 3, "pBad": 0.4}]).startswith("unknown")


def test_smoke_key_pattern():
    smoke = _load_smoke()
    assert smoke.KEY_PATTERN.search('{"u": "https://x/y?key=' + "A" * 30 + '"}')
    assert smoke.KEY_PATTERN.search("AIza" + "b" * 35)
    assert not smoke.KEY_PATTERN.search('{"streetViewUrl": "https://www.google.com/maps/@?api=1"}')


def test_smoke_unreachable_is_a_failure():
    smoke = _load_smoke().Smoke("http://127.0.0.1:9", None, timeout=1)
    status, headers, text = smoke.request("GET", "/health")
    assert (status, headers, text) == (0, {}, "")
    assert smoke.failures


# --- app engine ---------------------------------------------------------------


def test_app_engine_pings_pooled_connections():
    # Neon closes connections when an idle compute suspends; a stale pooled
    # connection must be replaced, not handed to the next request.
    from app.core.database import engine

    assert engine.pool._pre_ping is True
