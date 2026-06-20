"""Tests for the module entry point."""

import pytest

from lcstats_relay import __main__


def test_main_starts_flet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delegate module execution to the Flet application runner."""
    calls: list[bool] = []
    monkeypatch.setattr(__main__, "run", lambda: calls.append(True))

    __main__.main()

    assert calls == [True]
