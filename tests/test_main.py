"""Tests for the default command-line entry point."""

import pytest

from main import main


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    """Print the startup message."""
    main()

    captured = capsys.readouterr()
    assert captured.out == "Hello from lcstats-relay!\n"
