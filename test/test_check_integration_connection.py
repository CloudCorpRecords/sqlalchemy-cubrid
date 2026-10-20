"""Pin sync_probe() engine disposal on success and failure paths (issue #858)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SPEC = importlib.util.spec_from_file_location(
    "check_integration_connection",
    REPO_ROOT / "scripts/check_integration_connection.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
sync_probe = MODULE.sync_probe
_TIME_OUTS = MODULE._TIMEOUTS


class _FakeResult:
    def __init__(self, scalar: int) -> None:
        self.scalar = scalar

    def scalar_one(self) -> int:
        return self.scalar


class _FakeConnection:
    def __init__(self, scalar: int) -> None:
        self.scalar = scalar

    def execute(self, statement):  # noqa: ANN001, ANN202
        return _FakeResult(self.scalar)


class _ConnectionContext:
    def __init__(self, scalar: int) -> None:
        self.scalar = scalar

    def __enter__(self) -> _FakeConnection:
        return _FakeConnection(self.scalar)

    def __exit__(self, *exc_info) -> None:  # noqa: ANN002, ANN003
        return None


class _FakeEngine:
    def __init__(self, url, connect_args) -> None:  # noqa: ANN001
        self.url = url
        self.connect_args = connect_args
        self.disposed = False
        self.scalar = 1
        self.connect_raises: Exception | None = None

    def connect(self) -> _ConnectionContext:
        if self.connect_raises is not None:
            raise self.connect_raises
        return _ConnectionContext(self.scalar)

    def dispose(self) -> None:
        self.disposed = True


def _patch_engine(monkeypatch: pytest.MonkeyPatch) -> _FakeEngine:
    engine = _FakeEngine(None, None)
    created: dict[str, _FakeEngine] = {}

    def fake_create_engine(url, **kwargs):  # noqa: ANN001, ANN003, ANN202
        engine.url = url
        engine.connect_args = kwargs.get("connect_args")
        created["engine"] = engine
        return engine

    monkeypatch.setattr(MODULE, "create_engine", fake_create_engine)
    return engine


def test_disposes_engine_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _patch_engine(monkeypatch)
    sync_probe("cubrid://dba@localhost:33000/testdb")
    assert engine.disposed
    assert engine.connect_args == _TIME_OUTS
    assert engine.connect_args == {"connect_timeout": 5, "read_timeout": 5}


def test_disposes_engine_on_unexpected_scalar(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _patch_engine(monkeypatch)
    engine.scalar = 2
    with pytest.raises(RuntimeError, match="Unexpected database probe result"):
        sync_probe("cubrid://dba@localhost:33000/testdb")
    assert engine.disposed


def test_disposes_engine_when_connect_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _patch_engine(monkeypatch)
    engine.connect_raises = OSError("connection refused")
    with pytest.raises(OSError, match="connection refused"):
        sync_probe("cubrid://dba@localhost:33000/testdb")
    assert engine.disposed
