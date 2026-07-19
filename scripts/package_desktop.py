"""Package one verified Flet desktop build for CI or release publication."""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path

_ARCHIVE_SUFFIXES = {
    "gztar": ".tar.gz",
    "zip": ".zip",
}


def package_desktop(
    *,
    build_directory: Path,
    output_directory: Path,
    artifact_name: str,
    archive_format: str,
) -> Path:
    """Create one archive containing the complete generated desktop bundle."""
    if archive_format not in _ARCHIVE_SUFFIXES:
        msg = f"unsupported archive format: {archive_format}"
        raise ValueError(msg)
    if not artifact_name or Path(artifact_name).name != artifact_name:
        msg = "artifact name must be one non-empty path component"
        raise ValueError(msg)
    if not build_directory.is_dir():
        msg = f"build directory does not exist: {build_directory}"
        raise ValueError(msg)
    if not any(path.is_file() for path in build_directory.rglob("*")):
        msg = f"build directory contains no files: {build_directory}"
        raise ValueError(msg)

    output_directory.mkdir(parents=True, exist_ok=True)
    archive_base = output_directory / artifact_name
    expected_path = archive_base.with_name(
        f"{archive_base.name}{_ARCHIVE_SUFFIXES[archive_format]}"
    )
    expected_path.unlink(missing_ok=True)

    archive_path = Path(
        shutil.make_archive(
            str(archive_base),
            archive_format,
            root_dir=build_directory,
        )
    )
    if archive_path != expected_path:
        msg = f"archive path did not match the requested artifact: {archive_path}"
        raise RuntimeError(msg)
    return archive_path


def main(argv: Sequence[str] | None = None) -> int:
    """Package a desktop build from command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--format", choices=sorted(_ARCHIVE_SUFFIXES), required=True)
    args = parser.parse_args(argv)

    package_desktop(
        build_directory=args.build_directory,
        output_directory=args.output_directory,
        artifact_name=args.artifact_name,
        archive_format=args.format,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
