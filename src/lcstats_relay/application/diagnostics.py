"""Emit operational metadata through Python's standard logging API."""

import logging

LOGGER_NAME = "lcstats_relay.events"
_logger = logging.getLogger(LOGGER_NAME)


def emit(  # noqa: PLR0913 - events carry only these explicit operational fields.
    *,
    event: str,
    correlation_id: str = "",
    output: str = "",
    category: str = "",
    failed: bool = False,
    status_code: int | None = None,
) -> None:
    """Log fixed event names and metadata; never pass payloads or boundary text."""
    values = {
        "id": correlation_id,
        "output": output,
        "category": category,
        "http": status_code,
    }
    details = " ".join(f"{key}={value}" for key, value in values.items() if value not in ("", None))
    _logger.log(logging.WARNING if failed else logging.INFO, "event=%s %s", event, details)
