"""Structured operational events; never pass boundary text to this logger."""

import logging

LOGGER = logging.getLogger("lcstats_relay.events")
EVENTS = frozenset(
    [
        "application_started",
        "application_stopped",
        "application_failed",
        "connection_started",
        "connection_stopped",
        "connection_failed",
        "receive_waiting",
        "receive_connected",
        "receive_failed",
        "reconnect_scheduled",
        "payload_received",
        "payload_parse_failed",
        "output_started",
        "output_succeeded",
        "output_failed",
        "output_cancelled",
        "queue_saved",
        "queue_save_failed",
        "queue_loaded",
        "queue_read_failed",
        "retry_started",
        "retry_removed",
        "retry_remove_failed",
        "retry_skipped",
        "settings_loaded",
        "settings_saved",
        "settings_failed",
    ]
)
CATEGORIES = frozenset(
    [
        "delivery",
        "archive",
        "json_parse",
        "timeout",
        "transport",
        "http",
        "authentication",
        "response_format",
        "application",
        "queue",
        "storage",
        "unexpected",
    ]
)


def emit(  # noqa: PLR0913 - bounded event schema keeps metadata explicit.
    *,
    event: str,
    correlation_id: str = "",
    output: str = "",
    category: str = "",
    failed: bool = False,
    status_code: int | None = None,
) -> None:
    """Emit only structured metadata; the persistent formatter enforces its schema."""
    LOGGER.log(
        logging.WARNING if failed else logging.INFO,
        event,
        extra={
            "correlation_id": correlation_id,
            "output": output,
            "category": category,
            "status_code": status_code,
        },
    )
