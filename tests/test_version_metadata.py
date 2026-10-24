"""Release identity tests for canonical SemVer and native build versions."""

from pathlib import Path

import pytest

from scripts.version_metadata import main, read_version_metadata


@pytest.mark.parametrize(
    ("version", "build_version", "release_mode"),
    [
        ("0.0.0", "0.0.0", "edge"),
        ("0.1.0-alpha.1", "0.1.0", "prerelease"),
        ("0.1.0-alpha.12", "0.1.0", "prerelease"),
        ("0.1.0", "0.1.0", "latest"),
        ("1.2.3-rc.1", "1.2.3", "prerelease"),
    ],
)
def test_release_identity(
    *, tmp_path: Path, version: str, build_version: str, release_mode: str
) -> None:
    """Keep SemVer in tags/archives while deriving Flutter's numeric version."""
    path = tmp_path / "VERSION"
    path.write_text(f"{version}\n", encoding="ascii", newline="\n")
    metadata = read_version_metadata(version_path=path)
    assert metadata.project_version == version
    assert metadata.git_version == f"v{version}"
    assert metadata.build_version == build_version
    assert metadata.release_mode == release_mode


@pytest.mark.parametrize(
    "document",
    [
        "",
        "v0.1.0\n",
        "0.1\n",
        "0.1.0a1\n",
        "01.1.0\n",
        "0.1.0-alpha.01\n",
        "0.1.0+build.1\n",
        " 0.1.0\n",
        "0.1.0 \n",
        "0.1.0\n\n",
        "0.1.0\r\n",
        "0.1.0\nother\n",
    ],
)
def test_reject_noncanonical_release(*, tmp_path: Path, document: str) -> None:
    """Reject ambiguous identities before they become immutable tags."""
    path = tmp_path / "VERSION"
    path.write_bytes(document.encode("ascii"))
    with pytest.raises(ValueError, match="canonical SemVer"):
        read_version_metadata(version_path=path)


def test_missing_version_file(*, tmp_path: Path) -> None:
    """A missing release request must fail rather than choose a fallback."""
    with pytest.raises(FileNotFoundError):
        read_version_metadata(version_path=tmp_path / "VERSION")


def test_main_writes_github_outputs(*, tmp_path: Path) -> None:
    """Expose the same validated alpha identity to every CI consumer."""
    path = tmp_path / "VERSION"
    path.write_bytes(b"0.1.0-alpha.1")
    output = tmp_path / "github-output.txt"
    assert main(argv=["--version-file", str(path), "--github-output", str(output)]) == 0
    assert output.read_text().splitlines() == [
        "project_version=0.1.0-alpha.1",
        "build_version=0.1.0",
        "git_version=v0.1.0-alpha.1",
        "release_mode=prerelease",
    ]
