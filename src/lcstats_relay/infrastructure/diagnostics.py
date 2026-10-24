"""Configure standard-library logging for diagnostics retained across restarts."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lcstats_relay.application.diagnostics import LOGGER_NAME, emit
from lcstats_relay.infrastructure.config import default_data_dir


def default_log_dir() -> Path:
    """Use a fixed per-user location independent of the editable archive root."""
    return (
        default_data_dir().parent / "logs"
        if os.environ.get("LOCALAPPDATA")
        else default_data_dir() / "logs"
    )


@contextmanager
def logging_session(*, directory: Path | None = None) -> Iterator[None]:
    """Append operational events with standard rotation and console fallback."""
    path = (directory if directory is not None else default_log_dir()) / "relay.log"
    handler: logging.Handler
    fallback = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, mode="a", maxBytes=1_048_576, backupCount=4, encoding="utf-8"
        )
    except OSError:
        handler = logging.StreamHandler()
        fallback = True
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger = logging.getLogger(LOGGER_NAME)
    previous_level, previous_propagation = logger.level, logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    try:
        if fallback:
            emit(event="log_file_unavailable", category="storage", failed=True)
        emit(event="application_started")
        yield
    finally:
        emit(event="application_stopped")
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagation
        with suppress(OSError):
            handler.close()
