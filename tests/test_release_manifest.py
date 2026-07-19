"""Tests for release artifact manifests and checksums."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.release_manifest import ReleaseArtifact, ReleasePlan, main, write_release_files

_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_WORKFLOW_URL = "https://github.com/aoirint/lcstats_relay/actions/runs/123"


def _write_metadata(tmp_path: Path, *, version: str = "1.2.3") -> tuple[Path, Path, Path]:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        f'[project]\nname = "lcstats-relay"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    python_version_path = tmp_path / ".python-version"
    python_version_path.write_text("3.14\n", encoding="utf-8")
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text('[[package]]\nname = "flet"\nversion = "0.85.3"\n', encoding="utf-8")
    return pyproject_path, python_version_path, lock_path


def _write_artifacts(tmp_path: Path) -> list[ReleaseArtifact]:
    windows_path = tmp_path / "app-windows.zip"
    linux_path = tmp_path / "app-linux.tar.gz"
    windows_path.write_bytes(b"windows")
    linux_path.write_bytes(b"linux")
    return [
        ReleaseArtifact(target="windows", path=windows_path),
        ReleaseArtifact(target="linux", path=linux_path),
    ]


def _build_plan(tmp_path: Path, *, version: str = "1.2.3") -> ReleasePlan:
    pyproject_path, python_version_path, lock_path = _write_metadata(tmp_path, version=version)
    manifest_path = tmp_path / "release-manifest.json"
    checksums_path = tmp_path / "SHA256SUMS"
    return ReleasePlan(
        pyproject_path=pyproject_path,
        python_version_path=python_version_path,
        lock_path=lock_path,
        artifacts=_write_artifacts(tmp_path),
        build_number=42,
        source_commit=_COMMIT,
        workflow_url=_WORKFLOW_URL,
        uv_version="0.11.21",
        manifest_path=manifest_path,
        checksums_path=checksums_path,
    )


def _write_release(
    tmp_path: Path,
    *,
    plan: ReleasePlan | None = None,
    version: str = "1.2.3",
) -> tuple[Path, Path]:
    selected_plan = plan if plan is not None else _build_plan(tmp_path, version=version)
    write_release_files(plan=selected_plan)
    return selected_plan.manifest_path, selected_plan.checksums_path


def _invalid_identity_plan(tmp_path: Path, *, case: str) -> ReleasePlan:
    plan = _build_plan(tmp_path)
    match case:
        case "build_number":
            return replace(plan, build_number=0)
        case "source_commit":
            return replace(plan, source_commit="ABC")
        case "workflow_scheme" | "workflow_host" | "workflow_path":
            invalid_urls = {
                "workflow_scheme": "http://github.com/example/run",
                "workflow_host": "https://example.com/run",
                "workflow_path": "https://github.com",
            }
            return replace(plan, workflow_url=invalid_urls[case])
        case "uv_version":
            return replace(plan, uv_version="")
        case "artifacts":
            return replace(plan, artifacts=[])
        case _:
            raise AssertionError(case)


def test_write_release_files_records_sorted_provenance(tmp_path: Path) -> None:
    """Bind every published target to source, tools, sizes, and digests."""
    manifest_path, checksums_path = _write_release(tmp_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["project"] == {"name": "lcstats-relay", "version": "1.2.3"}
    assert manifest["build"] == {
        "flet_version": "0.85.3",
        "number": 42,
        "python_version": "3.14",
        "source_commit": _COMMIT,
        "uv_version": "0.11.21",
        "workflow_url": _WORKFLOW_URL,
    }
    assert [record["target"] for record in manifest["artifacts"]] == ["linux", "windows"]
    assert [record["size"] for record in manifest["artifacts"]] == [5, 7]
    assert checksums_path.read_text(encoding="utf-8").splitlines() == [
        f"{record['sha256']}  {record['file']}" for record in manifest["artifacts"]
    ]


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("build_number", "must be positive"),
        ("source_commit", "lowercase 40-character"),
        ("workflow_scheme", "HTTPS github.com"),
        ("workflow_host", "HTTPS github.com"),
        ("workflow_path", "HTTPS github.com"),
        ("uv_version", "must not be empty"),
        ("artifacts", "exactly one linux"),
    ],
)
def test_write_release_files_rejects_invalid_identity(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    """Reject incomplete, mutable, or non-release build identities."""
    with pytest.raises(ValueError, match=message):
        _write_release(tmp_path, plan=_invalid_identity_plan(tmp_path, case=case))


def test_write_release_files_rejects_edge_version(tmp_path: Path) -> None:
    """Keep the repository placeholder version out of GitHub Releases."""
    with pytest.raises(ValueError, match="cannot be released"):
        _write_release(tmp_path, version="0.0.0")


def test_write_release_files_rejects_empty_python_version(tmp_path: Path) -> None:
    """Require the selected Python runtime in the manifest."""
    python_version_path = tmp_path / "empty-python-version"
    python_version_path.write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not be empty"):
        _write_release(
            tmp_path,
            plan=replace(_build_plan(tmp_path), python_version_path=python_version_path),
        )


def test_write_release_files_rejects_duplicate_file_names(tmp_path: Path) -> None:
    """Keep release asset lookup unambiguous across target archives."""
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    first_path = first_directory / "desktop.zip"
    second_path = second_directory / "desktop.zip"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")

    with pytest.raises(ValueError, match="file names must be unique"):
        _write_release(
            tmp_path,
            plan=replace(
                _build_plan(tmp_path),
                artifacts=[
                    ReleaseArtifact(target="linux", path=first_path),
                    ReleaseArtifact(target="windows", path=second_path),
                ],
            ),
        )


def test_write_release_files_rejects_duplicate_targets(tmp_path: Path) -> None:
    """Require one archive for each supported desktop target."""
    plan = _build_plan(tmp_path)
    duplicate_targets = [replace(artifact, target="linux") for artifact in plan.artifacts]

    with pytest.raises(ValueError, match="exactly one linux"):
        _write_release(tmp_path, plan=replace(plan, artifacts=duplicate_targets))


def test_write_release_files_rejects_missing_artifact(tmp_path: Path) -> None:
    """Never publish a manifest for an absent target file."""
    plan = _build_plan(tmp_path)
    plan.artifacts[0].path.unlink()

    with pytest.raises(ValueError, match="existing file"):
        _write_release(tmp_path, plan=plan)


@pytest.mark.parametrize(
    ("pyproject", "lock", "message"),
    [
        ('[project]\nversion = "1.2.3"\n', None, "non-empty.*name"),
        (None, "version = 1\n", "package list"),
        (None, '[[package]]\nname = "httpx"\nversion = "1"\n', "exactly one flet"),
        (
            None,
            '[[package]]\nname = "flet"\nversion = "1"\n'
            '[[package]]\nname = "flet"\nversion = "2"\n',
            "exactly one flet",
        ),
        ('[project]\nname = 1\nversion = "1.2.3"\n', None, "non-empty.*name"),
        (
            None,
            '[[package]]\nname = "flet"\nversion = 1\n',
            "exactly one flet",
        ),
    ],
)
def test_write_release_files_rejects_invalid_project_metadata(
    tmp_path: Path,
    pyproject: str | None,
    lock: str | None,
    message: str,
) -> None:
    """Require canonical project and resolved Flet identity."""
    plan = _build_plan(tmp_path)
    if pyproject is not None:
        plan.pyproject_path.write_text(pyproject, encoding="utf-8")
    if lock is not None:
        plan.lock_path.write_text(lock, encoding="utf-8")

    exception_type = TypeError if message == "package list" else ValueError
    with pytest.raises(exception_type, match=message):
        _write_release(
            tmp_path,
            plan=plan,
        )


@pytest.mark.parametrize("value", ["linux", "=path", "linux="])
def test_main_rejects_invalid_artifact_spec(tmp_path: Path, value: str) -> None:
    """Require an explicit target-to-file mapping at the CLI boundary."""
    pyproject_path, python_version_path, lock_path = _write_metadata(tmp_path)

    with pytest.raises(ValueError, match="TARGET=PATH"):
        main(
            [
                "--pyproject",
                str(pyproject_path),
                "--python-version",
                str(python_version_path),
                "--lock",
                str(lock_path),
                "--artifact",
                value,
                "--build-number",
                "42",
                "--source-commit",
                _COMMIT,
                "--workflow-url",
                _WORKFLOW_URL,
                "--uv-version",
                "0.11.21",
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--checksums",
                str(tmp_path / "SHA256SUMS"),
            ]
        )


def test_main_writes_release_files(tmp_path: Path) -> None:
    """Generate both publication metadata files through the CLI."""
    pyproject_path, python_version_path, lock_path = _write_metadata(tmp_path)
    artifacts = _write_artifacts(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    checksums_path = tmp_path / "SHA256SUMS"

    assert (
        main(
            [
                "--pyproject",
                str(pyproject_path),
                "--python-version",
                str(python_version_path),
                "--lock",
                str(lock_path),
                "--artifact",
                f"windows={artifacts[0].path}",
                "--artifact",
                f"linux={artifacts[1].path}",
                "--build-number",
                "42",
                "--source-commit",
                _COMMIT,
                "--workflow-url",
                _WORKFLOW_URL,
                "--uv-version",
                "0.11.21",
                "--manifest",
                str(manifest_path),
                "--checksums",
                str(checksums_path),
            ]
        )
        == 0
    )
    assert manifest_path.is_file()
    assert checksums_path.is_file()
