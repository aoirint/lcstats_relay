"""Inspect a packaged desktop archive before CI accepts or publishes it."""

from __future__ import annotations

import argparse
import stat
import tarfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

_FORBIDDEN_PARTS = frozenset(
    {
        ".agents",
        ".git",
        ".github",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "tests",
    }
)
_REQUIRED_FILES = frozenset({PurePosixPath("LICENSE"), PurePosixPath("THIRD_PARTY_NOTICES.md")})


def _validate_path(name: str, *, label: str) -> PurePosixPath | None:
    normalized = name.removeprefix("./")
    if normalized in {"", "."}:
        return None
    path = PurePosixPath(normalized)
    if path.is_absolute() or "\\" in normalized or ".." in path.parts:
        msg = f"{label} uses an unsafe archive path: {name}"
        raise ValueError(msg)
    for part in path.parts:
        lowered = part.lower()
        if lowered in _FORBIDDEN_PARTS or lowered.startswith(".env") or lowered.endswith(".pyc"):
            msg = f"{label} contains forbidden release content: {name}"
            raise ValueError(msg)
    return path


def _record_path(*, path: PurePosixPath, paths: set[PurePosixPath]) -> None:
    if path in paths:
        msg = f"archive contains a duplicate path: {path}"
        raise ValueError(msg)
    paths.add(path)


def _verify_required_files(
    *,
    paths: set[PurePosixPath],
    regular_files: set[PurePosixPath],
    launcher: PurePosixPath,
) -> None:
    missing = (_REQUIRED_FILES | {launcher}) - regular_files
    if missing:
        names = ", ".join(sorted(path.as_posix() for path in missing))
        msg = f"archive is missing required regular files: {names}"
        raise ValueError(msg)
    if len(paths) == len(_REQUIRED_FILES) + 1:
        msg = "archive contains no application payload beyond required files"
        raise ValueError(msg)


def _verify_zip(*, archive_path: Path, launcher: PurePosixPath) -> None:
    paths: set[PurePosixPath] = set()
    regular_files: set[PurePosixPath] = set()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            path = _validate_path(member.filename, label="ZIP")
            if path is None or member.is_dir():
                continue
            _record_path(path=path, paths=paths)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                target = archive.read(member).decode("utf-8")
                _validate_path(target, label=f"ZIP link {path}")
            else:
                regular_files.add(path)
    _verify_required_files(paths=paths, regular_files=regular_files, launcher=launcher)


def _verify_tar(*, archive_path: Path, launcher: PurePosixPath) -> None:
    paths: set[PurePosixPath] = set()
    regular_files: set[PurePosixPath] = set()
    launcher_mode: int | None = None
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            path = _validate_path(member.name, label="tar")
            if path is None or member.isdir():
                continue
            _record_path(path=path, paths=paths)
            if member.issym() or member.islnk():
                _validate_path(member.linkname, label=f"tar link {path}")
            elif member.isfile():
                regular_files.add(path)
                if path == launcher:
                    launcher_mode = member.mode
            else:
                msg = f"tar contains unsupported special file: {path}"
                raise ValueError(msg)
    _verify_required_files(paths=paths, regular_files=regular_files, launcher=launcher)
    if launcher_mode is None or launcher_mode & 0o111 == 0:
        msg = f"Linux launcher is not executable: {launcher}"
        raise ValueError(msg)


def verify_desktop_archive(*, archive_path: Path, target: str, launcher_name: str) -> None:
    """Verify identity, safety, notices, and launcher behavior in one archive."""
    if not archive_path.is_file():
        msg = f"desktop archive does not exist: {archive_path}"
        raise ValueError(msg)
    launcher = _validate_path(launcher_name, label="launcher")
    if launcher is None or launcher.parent != PurePosixPath("."):
        msg = "launcher name must be one safe root path component"
        raise ValueError(msg)

    if target == "windows" and archive_path.name.endswith(".zip"):
        _verify_zip(archive_path=archive_path, launcher=launcher)
    elif target == "linux" and archive_path.name.endswith(".tar.gz"):
        _verify_tar(archive_path=archive_path, launcher=launcher)
    else:
        msg = f"archive format does not match desktop target: {target}"
        raise ValueError(msg)


def main(argv: Sequence[str] | None = None) -> int:
    """Verify a desktop archive from command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target", choices=["linux", "windows"], required=True)
    parser.add_argument("--launcher", required=True)
    args = parser.parse_args(argv)
    verify_desktop_archive(
        archive_path=args.archive,
        target=args.target,
        launcher_name=args.launcher,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
