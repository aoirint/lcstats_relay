"""Payload types shared by receivers, outputs, and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast
from uuid import uuid4

type JSONValue = bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None


def parse_json(*, raw_json: str) -> JSONValue:
    """Parse a JSON value without leaking an untyped result."""
    return cast("JSONValue", json.loads(raw_json))


@dataclass(frozen=True, kw_only=True, slots=True)
class RelayPayload:
    """One received payload, including an optional parsing failure."""

    raw_json: str
    payload: JSONValue
    received_at: datetime
    parse_error: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid4().hex, compare=False)
