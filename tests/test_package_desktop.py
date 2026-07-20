"""Tests for desktop build archive packaging."""

import tarfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.package_desktop import main, package_desktop


@pytest.mark.parametrize(
    ("archive_format", "suffix"),
    [("zip", ".zip"), ("gztar", ".tar.gz")],
)
def test_package_desktop_archives_complete_build(
    *,
    tmp_path: Path,
    archive_format: str,
    suffix: str,
) -> None:
    """Keep nested generated files in each target-specific archive format."""
    build_directory = tmp_path / "build"
    nested_directory = build_directory / "data"
    nested_directory.mkdir(parents=True)
    (build_directory / "launcher").write_text("executable", encoding="utf-8")
    (nested_directory / "asset.txt").write_text("asset", encoding="utf-8")

    archive_path = package_desktop(
        build_directory=build_directory,
        output_directory=tmp_path / "dist",
        artifact_name="desktop-linux",
        archive_format=archive_format,
    )

    assert archive_path == tmp_path / "dist" / f"desktop-linux{suffix}"
    if archive_format == "zip":
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(archive_path, "r:gz") as archive:
            names = [name.removeprefix("./") for name in archive.getnames()]
    assert "launcher" in names
    assert "data/asset.txt" in names


@pytest.mark.parametrize(
    ("build_state", "artifact_name", "archive_format", "message"),
    [
        ("missing", "desktop", "zip", "does not exist"),
        ("empty", "desktop", "zip", "contains no files"),
        ("populated", "", "zip", "one non-empty path component"),
        ("populated", "nested/desktop", "zip", "one non-empty path component"),
        ("populated", "desktop", "rar", "unsupported archive format"),
    ],
)
def test_package_desktop_rejects_invalid_input(
    *,
    tmp_path: Path,
    build_state: str,
    artifact_name: str,
    archive_format: str,
    message: str,
) -> None:
    """Reject ambiguous or empty build inputs before creating an artifact."""
    build_directory = tmp_path / "build"
    if build_state != "missing":
        build_directory.mkdir()
    if build_state == "populated":
        (build_directory / "app").write_text("app", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        package_desktop(
            build_directory=build_directory,
            output_directory=tmp_path / "dist",
            artifact_name=artifact_name,
            archive_format=archive_format,
        )


def test_package_desktop_rejects_unexpected_archive_path(*, tmp_path: Path) -> None:
    """Fail closed if the archive implementation returns another output path."""
    build_directory = tmp_path / "build"
    build_directory.mkdir()
    (build_directory / "app").write_text("app", encoding="utf-8")

    with (
        patch("scripts.package_desktop.shutil.make_archive", return_value="unexpected.zip"),
        pytest.raises(RuntimeError, match="did not match"),
    ):
        package_desktop(
            build_directory=build_directory,
            output_directory=tmp_path / "dist",
            artifact_name="desktop",
            archive_format="zip",
        )


def test_main_packages_archive(*, tmp_path: Path) -> None:
    """Create the requested archive from command-line arguments."""
    build_directory = tmp_path / "build"
    build_directory.mkdir()
    (build_directory / "app.exe").write_text("app", encoding="utf-8")

    assert (
        main(
            argv=[
                "--build-directory",
                str(build_directory),
                "--output-directory",
                str(tmp_path / "dist"),
                "--artifact-name",
                "desktop-windows",
                "--format",
                "zip",
            ]
        )
        == 0
    )
    assert (tmp_path / "dist" / "desktop-windows.zip").is_file()
