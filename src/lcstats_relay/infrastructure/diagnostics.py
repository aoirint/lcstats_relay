"""Bounded private operational logs independent of third-party logging."""

from __future__ import annotations

import json
import logging
import os
from contextlib import suppress
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import UUID, uuid4

from lcstats_relay.application.diagnostics import CATEGORIES, EVENTS, LOGGER, emit
from lcstats_relay.infrastructure.config import default_config_path, default_data_dir

MAX_LOG_BYTES = 1_048_576
LOG_BACKUPS = 4
_MIN_HTTP_STATUS = 100
_MAX_HTTP_STATUS = 599


def default_log_dir() -> Path:
    """Keep logs stable even when the configured archive root changes."""
    return (
        default_data_dir().parent / "logs"
        if os.environ.get("LOCALAPPDATA")
        else default_data_dir() / "logs"
    )


class EventFormatter(logging.Formatter):
    """Serialize an allowlist, ignoring exceptions, arguments and arbitrary extras."""

    def __init__(self) -> None:
        """Give every process logging session a random identity."""
        super().__init__()
        self._session = uuid4().hex

    def format(self, record: logging.LogRecord) -> str:  # noqa: PLR0917 -- keyword-only-exception: logging Formatter ABI
        """Drop all fields except bounded operational metadata."""
        result: dict[str, str | int] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": "WARNING" if record.levelno >= logging.WARNING else "INFO",
            "session_id": self._session,
            "event": record.msg
            if isinstance(record.msg, str) and record.msg in EVENTS
            else "application_failed",
        }
        output = getattr(record, "output", "")
        if output in ("archive", "gas"):
            result["output"] = output
        category = getattr(record, "category", "")
        if category in CATEGORIES:
            result["category"] = category
        status_code = getattr(record, "status_code", None)
        if isinstance(status_code, int) and _MIN_HTTP_STATUS <= status_code <= _MAX_HTTP_STATUS:
            result["status_code"] = status_code
        with suppress(ValueError):
            result["correlation_id"] = UUID(hex=str(getattr(record, "correlation_id", ""))).hex
        return json.dumps(result, ensure_ascii=True)


class DiagnosticLog:
    """Own the file handler and expose failures without logging sensitive exceptions."""

    def __init__(self, *, directory: Path) -> None:
        """Configure a stable output location without opening it yet."""
        self.path = directory.resolve() / "relay.jsonl"
        self.failed = False
        self._handler: RotatingFileHandler | None = None

    def start(self) -> None:
        """Open a rotating sink, or continue with a visible degraded status."""
        if self._handler is not None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handler = _SafeRotatingHandler(owner=self)
        except OSError:
            self.failed = True
            return
        handler.setFormatter(EventFormatter())
        LOGGER.setLevel(logging.INFO)
        LOGGER.propagate = False
        LOGGER.addHandler(handler)
        self._handler = handler
        emit(event="application_started")

    def close(self) -> None:
        """Flush and release the sink on normal or failed application exit."""
        if self._handler is not None:
            emit(event="application_stopped")
            LOGGER.removeHandler(self._handler)
            try:
                self._handler.close()
            except OSError:
                self.failed = True
            self._handler = None

    def describe(self, *, data_dir: Path) -> str:
        """Show actual paths locally; paths deliberately never enter shared logs."""
        status = "書き込み失敗(ログが欠落しています)" if self.failed else "有効"
        return (
            f"診断ログ: {self.path} [{status}]\n"
            f"設定: {default_config_path().resolve()}\n"
            f"アーカイブ: {(data_dir / 'archive').resolve()}\n"
            f"再送キュー: {(data_dir / 'queue').resolve()}\n"
            "共有する前にログを確認してください。設定・アーカイブ・キューは含めないでください。"
        )


class _SafeRotatingHandler(RotatingFileHandler):
    def __init__(self, *, owner: DiagnosticLog) -> None:
        self._owner = owner
        super().__init__(
            owner.path, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )

    def handleError(  # keyword-only-exception: logging.Handler ABI  # noqa: N802, PLR0917
        self, record: logging.LogRecord
    ) -> None:
        # logging's default error handler prints the record and traceback to stderr.
        del record
        self._owner.failed = True
