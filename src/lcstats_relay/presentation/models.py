"""Immutable monitor presentation values."""

from dataclasses import dataclass
from enum import StrEnum


class Tone(StrEnum):
    """Semantic color role interpreted by a UI adapter."""

    NEUTRAL = "neutral"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class StatusGlyph(StrEnum):
    """Semantic status symbol interpreted by a UI adapter."""

    CHECK = "check"
    ERROR = "error"
    IDLE = "idle"
    LINK_OFF = "link_off"
    SYNC = "sync"
    WARNING = "warning"


@dataclass(frozen=True, kw_only=True, slots=True)
class OutputViewState:
    """One output destination ready for deterministic rendering."""

    label: str
    status_label: str
    tone: Tone
    glyph: StatusGlyph
    glyph_tone: Tone
    detail: str | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class HealthViewState:
    """Global relay health ready for deterministic rendering."""

    label: str
    detail: str
    tone: Tone
    glyph: StatusGlyph
    glyph_tone: Tone


@dataclass(frozen=True, kw_only=True, slots=True)
class RelayViewState:
    """Complete framework-free state consumed by the monitor adapter."""

    status_label: str
    receive_count: str
    last_received: str
    error: str
    health: HealthViewState
    outputs: tuple[OutputViewState, ...]
