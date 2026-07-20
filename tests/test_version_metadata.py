"""Tests for pyproject-based Flet build version metadata."""

from pathlib import Path

import pytest

from scripts.version_metadata import main, read_version_metadata


@pytest.mark.parametrize(
    ("version", "build_version", "release_mode"),
    [
        ("0.0.0", "0.0.0", "edge"),
        ("1.2", "1.2.0", "latest"),
        ("1.2.3", "1.2.3", "latest"),
        ("1.2.3a1", "1.2.3", "prerelease"),
        ("1.2.3.dev1", "1.2.3", "prerelease"),
    ],
)
def test_read_version_metadata(
    *,
    tmp_path: Path,
    version: str,
    build_version: str,
    release_mode: str,
) -> None:
    """Preserve PEP 440 identity while deriving Flet's x.y.z build value."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")

    metadata = read_version_metadata(pyproject_path=pyproject)

    assert metadata.project_version == version
    assert metadata.build_version == build_version
    assert metadata.git_version == f"v{version}"
    assert metadata.release_mode == release_mode


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("[build-system]\nrequires = []\n", "must define"),
        ('[project]\nversion = "not a version"\n', "PEP 440"),
        ('[project]\nversion = "1.0RC1"\n', "must be normalized"),
        ('[project]\nversion = "1.0.0.0"\n', "too many release segments"),
        ('[project]\nversion = "1!1.0.0"\n', "epoch or local"),
        ('[project]\nversion = "1.0.0+local"\n', "epoch or local"),
    ],
)
def test_read_version_metadata_rejects_unsupported_versions(
    *,
    tmp_path: Path,
    document: str,
    message: str,
) -> None:
    """Reject identities that cannot remain consistent across build surfaces."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(document, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_version_metadata(pyproject_path=pyproject)


def test_main_writes_github_outputs(*, tmp_path: Path) -> None:
    """Expose stable output names for the local Composite Action."""
    pyproject = tmp_path / "pyproject.toml"
    output = tmp_path / "github-output.txt"
    pyproject.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")

    assert main(argv=["--pyproject", str(pyproject), "--github-output", str(output)]) == 0
    assert output.read_text(encoding="utf-8").splitlines() == [
        "project_version=1.2.3",
        "build_version=1.2.3",
        "git_version=v1.2.3",
        "release_mode=latest",
    ]
