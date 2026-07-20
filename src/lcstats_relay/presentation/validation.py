"""Validate user-entered relay settings without depending on Flet."""

from pathlib import Path
from urllib.parse import parse_qsl, urlparse

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def validate_sse_url(*, value: str) -> str:
    """Validate and normalize the local stats endpoint URL."""
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in _LOCAL_HOSTS:
        msg = "LCStatsTracker URLにはlocalhostのHTTP URLを指定してください"
        raise ValueError(msg)
    if parsed.username is not None or parsed.password is not None:
        msg = "LCStatsTracker URLに認証情報を含めることはできません"
        raise ValueError(msg)
    return url


def validate_gas_url(*, value: str) -> str:
    """Validate and normalize a Google Apps Script Web App URL."""
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "script.google.com":
        msg = "GAS URLにはscript.google.comのHTTPS URLを指定してください"
        raise ValueError(msg)
    if not parsed.path.startswith("/macros/s/"):
        msg = "GAS Web Appの実行URLを指定してください"
        raise ValueError(msg)
    if any(key.lower() == "token" for key, _value in parse_qsl(parsed.query)):
        msg = "GAS tokenはURLではなくToken欄に指定してください"
        raise ValueError(msg)
    return url


def validate_data_dir(*, value: str) -> Path:
    """Validate and normalize the local archive root directory."""
    raw_path = value.strip()
    if not raw_path:
        msg = "ローカル保存先ディレクトリを指定してください"
        raise ValueError(msg)
    return Path(raw_path).expanduser()
