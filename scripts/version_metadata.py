"""Read the canonical SemVer release identity from the root VERSION file."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_NUMBER = r"(?:0|[1-9][0-9]*)"
_IDENTIFIER = rf"(?:{_NUMBER}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(
    rf"(?P<release>{_NUMBER}\.{_NUMBER}\.{_NUMBER})"
    rf"(?P<prerelease>-{_IDENTIFIER}(?:\.{_IDENTIFIER})*)?"
)


@dataclass(frozen=True, kw_only=True, slots=True)
class VersionMetadata:
    """Release identities shared by Flet, artifacts, and Git."""

    project_version: str
    build_version: str
    git_version: str
    release_mode: str


def read_version_metadata(*, version_path: Path) -> VersionMetadata:
    """Accept one bare stable or prerelease SemVer and an optional final LF."""
    version_text = version_path.read_bytes().decode("ascii").removesuffix("\n")
    match = _SEMVER.fullmatch(version_text)
    if match is None:
        msg = "VERSION must contain one canonical SemVer without build metadata"
        raise ValueError(msg)
    if version_text == "0.0.0":
        release_mode = "edge"
    elif match.group("prerelease"):
        release_mode = "prerelease"
    else:
        release_mode = "latest"
    return VersionMetadata(
        project_version=version_text,
        build_version=match.group("release"),
        git_version=f"v{version_text}",
        release_mode=release_mode,
    )


def _write_github_output(*, path: Path, metadata: VersionMetadata) -> None:
    values = {
        "project_version": metadata.project_version,
        "build_version": metadata.build_version,
        "git_version": metadata.git_version,
        "release_mode": metadata.release_mode,
    }
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main(*, argv: Sequence[str] | None = None) -> int:
    """Write validated metadata to the GitHub Actions output file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-file", type=Path, default=Path("VERSION"))
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)
    metadata = read_version_metadata(version_path=args.version_file)
    _write_github_output(path=args.github_output, metadata=metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
