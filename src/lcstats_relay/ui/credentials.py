"""Official Flet SecureStorage adapter for desktop credentials."""

import asyncio
import hashlib

import flet as ft
from flet_secure_storage import SecureStorage

from lcstats_relay.application.credentials import CredentialStoreError

_TIMEOUT_SECONDS = 10


class FletTokenStore:
    """Keep URLs out of credential names and never fall back to browser storage."""

    def __init__(self, *, storage: SecureStorage, native: bool) -> None:
        """Retain the service constructed inside the active Flet page context."""
        self._storage = storage
        self._native = native

    def _key(self, *, gas_url: str) -> str:
        if not self._native:
            raise CredentialStoreError
        digest = hashlib.sha256(gas_url.encode("utf-8")).hexdigest()
        return f"lcstats-relay.gas.{digest}"

    async def load(self, *, gas_url: str) -> str | None:
        """Read only this application's entry for this destination."""
        key = self._key(gas_url=gas_url)
        try:
            return await asyncio.wait_for(self._storage.get(key=key), timeout=_TIMEOUT_SECONDS)
        except RuntimeError, TimeoutError:
            # Flet 1.0.4 reports client invocation errors as RuntimeError.
            raise CredentialStoreError from None

    async def save(self, *, gas_url: str, token: str) -> None:
        """Write through the official native service, without plaintext fallback."""
        key = self._key(gas_url=gas_url)
        try:
            await asyncio.wait_for(
                self._storage.set(key=key, value=token), timeout=_TIMEOUT_SECONDS
            )
        except RuntimeError, TimeoutError:
            raise CredentialStoreError from None

    async def delete(self, *, gas_url: str) -> None:
        """Delete exactly one app/destination entry, never the whole OS vault."""
        key = self._key(gas_url=gas_url)
        try:
            await asyncio.wait_for(self._storage.remove(key=key), timeout=_TIMEOUT_SECONDS)
        except RuntimeError, TimeoutError:
            raise CredentialStoreError from None


def credential_store_name(*, platform: ft.PagePlatform | None) -> str:
    """Use the native platform's familiar credential-store name."""
    names: dict[ft.PagePlatform | None, str] = {
        ft.PagePlatform.WINDOWS: "Windows 資格情報マネージャー",
        ft.PagePlatform.MACOS: "macOS キーチェーン",
        ft.PagePlatform.LINUX: "システムのキーリング",
    }
    return names.get(platform, "OSの認証情報ストア")
