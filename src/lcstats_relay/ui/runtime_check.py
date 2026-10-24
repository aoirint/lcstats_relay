"""Opt-in native CI rendering, runtime identity, and credential restart checks."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import ssl
import struct
import sys
from collections.abc import Awaitable, Callable
from importlib.metadata import version
from pathlib import Path
from typing import cast

import flet as ft

from lcstats_relay.application.credentials import GasTokenStore


async def verify_native_startup(
    *, page: ft.Page, control: ft.Control, report_path: Path, token_store: GasTokenStore
) -> None:
    """Prove that the packaged page renders, then exit the isolated CI launch."""
    screenshot = ft.Screenshot(content=control)
    page.controls = [screenshot]
    page.update()
    # Flet 1.0.4 leaves these inspected zero-argument async methods unannotated.
    ready = cast("Callable[[], Awaitable[None]]", page.window.wait_until_ready_to_show)
    close = cast("Callable[[], Awaitable[None]]", page.window.destroy)
    try:
        await ready()
        if phase := os.environ.get("LCSTATS_RELAY_PROBE_PHASE"):
            await _probe_credentials(
                store=token_store, phase=phase, value=os.environ["LCSTATS_RELAY_PROBE_VALUE"]
            )
        png = await screenshot.capture(delay=200)
        if not png.startswith(b"\x89PNG\r\n\x1a\n"):
            msg = "Native startup did not return a PNG render"
            raise ValueError(msg)
        await asyncio.to_thread(
            _write_startup_report, report_path=report_path, png=png, page_title=page.title
        )
    finally:
        await close()


async def _probe_credentials(*, store: GasTokenStore, phase: str, value: str) -> None:
    """Probe an unreachable destination key; never touch production credentials."""
    # This reserved domain cannot pass GAS validation or name a production entry.
    destination = "https://example.invalid/lcstats-relay-native-probe"
    if phase == "write":
        await store.delete(gas_url=destination)
        await store.save(gas_url=destination, token=value)
    elif phase == "read-delete":
        if await store.load(gas_url=destination) != value:
            msg = "Credential did not survive process restart"
            raise ValueError(msg)
        await store.delete(gas_url=destination)
    elif phase == "absent":
        if await store.load(gas_url=destination) is not None:
            msg = "Deleted credential was restored"
            raise ValueError(msg)
    else:
        msg = "Unknown credential probe phase"
        raise ValueError(msg)


def _write_startup_report(*, report_path: Path, png: bytes, page_title: str | None) -> None:
    width, height = struct.unpack(">II", png[16:24])
    report_path.with_suffix(".png").write_bytes(png)
    release_version = (Path(sys.executable).parent / "VERSION").read_text(encoding="ascii").strip()
    report = {
        "version": release_version,
        "python_version": sys.version.split()[0],
        "architecture_bits": struct.calcsize("P") * 8,
        "flet_version": version("flet"),
        "httpx_version": version("httpx"),
        "certifi_version": version("certifi"),
        "openssl_version": ssl.OPENSSL_VERSION,
        "page_title": page_title,
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "width": width,
        "height": height,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
