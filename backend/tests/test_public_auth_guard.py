"""Startup guard: PUBLIC_READ_ONLY must not run with AUTH_MODE=disabled (T-79)."""
import pytest

from app.core.config import Settings


def make(**overrides):
    return Settings(_env_file=None, **overrides)


def test_public_read_only_with_auth_disabled_is_refused():
    for mode in ("disabled", " Disabled "):
        with pytest.raises(RuntimeError, match="AUTH_MODE=disabled"):
            make(PUBLIC_READ_ONLY=True, AUTH_MODE=mode).check_public_auth()


def test_allowed_combinations_pass():
    make(PUBLIC_READ_ONLY=True, AUTH_MODE="clerk").check_public_auth()
    make(PUBLIC_READ_ONLY=False, AUTH_MODE="disabled").check_public_auth()
    make(PUBLIC_READ_ONLY=False, AUTH_MODE="clerk").check_public_auth()


def test_app_startup_calls_the_guard():
    import inspect

    import app.main as main

    assert "settings.check_public_auth()" in inspect.getsource(main)
