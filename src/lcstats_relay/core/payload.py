"""Payload types shared by receivers, outputs, and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]


def parse_json(raw_json: str) -> JSONValue:
    """Parse a JSON value without leaking an untyped result."""
    return cast("JSONValue", json.loads(raw_json))


@dataclass(frozen=True, kw_only=True, slots=True)
class RelayPayload:
    """One received payload, including an optional parsing failure."""

    raw_json: str
    payload: JSONValue
    received_at: datetime
    parse_error: str | None = None
