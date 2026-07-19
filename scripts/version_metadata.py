"""Validate canonical project version metadata for Flet desktop builds."""

from __future__ import annotations

import argparse
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

_BUILD_VERSION_SEGMENTS = 3


@dataclass(frozen=True, kw_only=True, slots=True)
class VersionMetadata:
    """Version identities shared by Python, Flet, artifacts, and Git."""

    project_version: str
    build_version: str
    git_version: str
    release_mode: str


def read_version_metadata(pyproject_path: Path) -> VersionMetadata:
    """Read and validate one normalized PEP 440 project version."""
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project")
    version_text = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version_text, str) or not version_text:
        msg = "pyproject.toml must define a non-empty [project].version"
        raise ValueError(msg)
    try:
        version = Version(version_text)
    except InvalidVersion as exc:
        msg = f"project.version is not PEP 440 compliant: {version_text}"
        raise ValueError(msg) from exc
    if str(version) != version_text:
        msg = f"project.version must be normalized: {version_text} != {version}"
        raise ValueError(msg)
    if version.epoch != 0 or version.local is not None:
        msg = "project.version must not contain an epoch or local version segment"
        raise ValueError(msg)
    if len(version.release) > _BUILD_VERSION_SEGMENTS:
        msg = "project.version has too many release segments for a Flet build version"
        raise ValueError(msg)

    release = (*version.release, 0, 0)[:_BUILD_VERSION_SEGMENTS]
    build_version = ".".join(str(segment) for segment in release)
    if version_text == "0.0.0":
        release_mode = "edge"
    elif version.is_prerelease or version.is_devrelease:
        release_mode = "prerelease"
    else:
        release_mode = "latest"
    return VersionMetadata(
        project_version=version_text,
        build_version=build_version,
        git_version=f"v{version_text}",
        release_mode=release_mode,
    )


def _write_github_output(path: Path, metadata: VersionMetadata) -> None:
    values = {
        "project_version": metadata.project_version,
        "build_version": metadata.build_version,
        "git_version": metadata.git_version,
        "release_mode": metadata.release_mode,
    }
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Write validated metadata to the GitHub Actions output file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)
    metadata = read_version_metadata(args.pyproject)
    _write_github_output(args.github_output, metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
