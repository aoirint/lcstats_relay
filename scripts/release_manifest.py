"""Generate checksums and provenance metadata for release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from operator import attrgetter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.verify_desktop_archive import verify_desktop_archive
from scripts.version_metadata import read_version_metadata

_REQUIRED_TARGETS = frozenset({"linux", "windows"})
_SCHEMA_VERSION = 2
_SOURCE_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, kw_only=True, slots=True)
class ReleaseArtifact:
    """One target archive accepted for release publication."""

    target: str
    path: Path


@dataclass(frozen=True, kw_only=True, slots=True)
class ReleasePlan:
    """Canonical inputs and output paths for one release manifest."""

    pyproject_path: Path
    python_version_path: Path
    lock_path: Path
    artifacts: Sequence[ReleaseArtifact]
    build_number: int
    source_commit: str
    workflow_url: str
    uv_version: str
    manifest_path: Path
    checksums_path: Path


def _parse_artifact(*, value: str) -> ReleaseArtifact:
    target, separator, path_text = value.partition("=")
    if not separator or not target or not path_text:
        msg = "artifact must use TARGET=PATH with non-empty values"
        raise ValueError(msg)
    return ReleaseArtifact(target=target, path=Path(path_text))


def _read_project_name(*, pyproject_path: Path) -> str:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    if not isinstance(name, str) or not name:
        msg = "pyproject.toml must define a non-empty [project].name"
        raise ValueError(msg)
    return name


def _read_resolved_package_version(*, lock_path: Path, package_name: str) -> str:
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = data.get("package")
    if not isinstance(packages, list):
        msg = "uv.lock must contain a package list"
        raise TypeError(msg)
    versions = [
        package.get("version")
        for package in packages
        if isinstance(package, dict) and package.get("name") == package_name
    ]
    if len(versions) != 1 or not isinstance(versions[0], str) or not versions[0]:
        msg = f"uv.lock must resolve exactly one {package_name} package version"
        raise ValueError(msg)
    return versions[0]


def _sha256(*, path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        while chunk := artifact.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_build_identity(
    *,
    build_number: int,
    source_commit: str,
    workflow_url: str,
    uv_version: str,
) -> None:
    if build_number <= 0:
        msg = "build number must be positive"
        raise ValueError(msg)
    if _SOURCE_COMMIT_PATTERN.fullmatch(source_commit) is None:
        msg = "source commit must be a lowercase 40-character Git SHA"
        raise ValueError(msg)
    parsed_url = urlparse(workflow_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "github.com" or not parsed_url.path:
        msg = "workflow URL must identify an HTTPS github.com path"
        raise ValueError(msg)
    if not uv_version:
        msg = "uv version must not be empty"
        raise ValueError(msg)


def write_release_files(*, plan: ReleasePlan) -> None:
    """Validate release identity and write one manifest plus checksum list."""
    metadata = read_version_metadata(pyproject_path=plan.pyproject_path)
    if metadata.release_mode == "edge":
        msg = "project version 0.0.0 cannot be released"
        raise ValueError(msg)
    _validate_build_identity(
        build_number=plan.build_number,
        source_commit=plan.source_commit,
        workflow_url=plan.workflow_url,
        uv_version=plan.uv_version,
    )

    builder_python_version = plan.python_version_path.read_text(encoding="utf-8").strip()
    if not builder_python_version:
        msg = "Python version file must not be empty"
        raise ValueError(msg)

    if (
        len(plan.artifacts) != len(_REQUIRED_TARGETS)
        or {artifact.target for artifact in plan.artifacts} != _REQUIRED_TARGETS
    ):
        msg = "release must contain exactly one linux and one windows artifact"
        raise ValueError(msg)
    artifact_names = [artifact.path.name for artifact in plan.artifacts]
    if len(set(artifact_names)) != len(artifact_names):
        msg = "release artifact file names must be unique"
        raise ValueError(msg)
    if any(not artifact.path.is_file() for artifact in plan.artifacts):
        msg = "every release artifact path must be an existing file"
        raise ValueError(msg)

    artifact_records = []
    for artifact in sorted(plan.artifacts, key=attrgetter("target")):
        launcher_name = "lcstats-relay.exe" if artifact.target == "windows" else "lcstats-relay"
        runtime_version = verify_desktop_archive(
            archive_path=artifact.path,
            target=artifact.target,
            launcher_name=launcher_name,
        )
        artifact_records.append(
            {
                "file": artifact.path.name,
                "python_runtime_version": runtime_version,
                "sha256": _sha256(path=artifact.path),
                "size": artifact.path.stat().st_size,
                "target": artifact.target,
            }
        )
    manifest: dict[str, Any] = {
        "artifacts": artifact_records,
        "build": {
            "flet_version": _read_resolved_package_version(
                lock_path=plan.lock_path, package_name="flet"
            ),
            "number": plan.build_number,
            "builder_python_version": builder_python_version,
            "source_commit": plan.source_commit,
            "uv_version": plan.uv_version,
            "workflow_url": plan.workflow_url,
        },
        "project": {
            "name": _read_project_name(pyproject_path=plan.pyproject_path),
            "version": metadata.project_version,
        },
        "schema_version": _SCHEMA_VERSION,
    }

    plan.manifest_path.write_text(
        f"{json.dumps(manifest, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
        newline="\n",
    )
    plan.checksums_path.write_text(
        "".join(f"{record['sha256']}  {record['file']}\n" for record in artifact_records),
        encoding="utf-8",
        newline="\n",
    )


def main(*, argv: Sequence[str] | None = None) -> int:
    """Generate release metadata from command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--python-version", type=Path, default=Path(".python-version"))
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--build-number", type=int, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--workflow-url", required=True)
    parser.add_argument("--uv-version", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    args = parser.parse_args(argv)

    write_release_files(
        plan=ReleasePlan(
            pyproject_path=args.pyproject,
            python_version_path=args.python_version,
            lock_path=args.lock,
            artifacts=[_parse_artifact(value=value) for value in args.artifact],
            build_number=args.build_number,
            source_commit=args.source_commit,
            workflow_url=args.workflow_url,
            uv_version=args.uv_version,
            manifest_path=args.manifest,
            checksums_path=args.checksums,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
