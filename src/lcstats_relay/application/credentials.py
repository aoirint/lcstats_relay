"""Desktop credential persistence boundary, separate from non-secret settings."""

from typing import Protocol


class CredentialStoreError(RuntimeError):
    """An OS credential operation failed; no backend details are exposed."""


class GasTokenStore(Protocol):
    """Store tokens separately for each accepted GAS destination."""

    async def load(self, *, gas_url: str) -> str | None:
        """Read a saved token, or None when absent."""

    async def save(self, *, gas_url: str, token: str) -> None:
        """Persist one destination's token in the OS store."""

    async def delete(self, *, gas_url: str) -> None:
        """Remove one destination's token, including an already absent entry."""
