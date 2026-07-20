"""Authentication policies for HTTP output requests."""

from __future__ import annotations

from typing import Protocol

import httpx


class RequestAuthenticator(Protocol):
    """Apply credentials to a prepared request."""

    def apply(self, *, request: httpx.Request) -> None:
        """Mutate a request with authentication data."""


class NoAuthentication:
    """Leave output requests unauthenticated."""

    def apply(self, *, request: httpx.Request) -> None:
        """Leave the supplied request unchanged."""


class QueryTokenAuthentication:
    """Add a secret token as a configurable URL query parameter."""

    def __init__(self, *, token: str, parameter: str = "token") -> None:
        """Retain the credential separately from the destination URL."""
        self._token = token
        self._parameter = parameter

    def apply(self, *, request: httpx.Request) -> None:
        """Add the token only to the outgoing request URL."""
        request.url = request.url.copy_set_param(self._parameter, self._token)
