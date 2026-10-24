"""Credential test double; never used by the production composition."""


class MemoryTokens:
    """An isolated token dictionary shared by test controllers."""

    def __init__(self) -> None:
        """Start with no credentials."""
        self.values: dict[str, str] = {}

    async def load(self, *, gas_url: str) -> str | None:
        """Read one test destination."""
        return self.values.get(gas_url)

    async def save(self, *, gas_url: str, token: str) -> None:
        """Save one test destination."""
        self.values[gas_url] = token

    async def delete(self, *, gas_url: str) -> None:
        """Forget one test destination."""
        self.values.pop(gas_url, None)
