"""Tests for the module entry point."""

import tomllib
from pathlib import Path

import pytest

from lcstats_relay import __main__


def test_main_starts_flet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delegate module execution to the Flet application runner."""
    calls: list[bool] = []
    monkeypatch.setattr(__main__, "run", lambda: calls.append(True))

    __main__.main()

    assert calls == [True]


def test_console_script_points_to_module_entry_point() -> None:
    """Expose the same entry point through the installed console command."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["lcstats-relay"] == "lcstats_relay.__main__:main"
