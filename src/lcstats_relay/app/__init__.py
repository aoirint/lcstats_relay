"""Application assembly for the Flet desktop process."""

from lcstats_relay.app.composition import create_connection_manager
from lcstats_relay.app.main import main, run

__all__ = ["create_connection_manager", "main", "run"]
