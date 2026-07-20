"""Tests for final desktop release archive inspection."""

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.verify_desktop_archive import main, verify_desktop_archive


def _write_zip(
    *, path: Path, members: dict[str, bytes], symlink: tuple[str, str] | None = None
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("./", b"")
        archive.writestr("data/", b"")
        for name, value in members.items():
            info = zipfile.ZipInfo(name)
            archive.writestr(info, value)
        if symlink is not None:
            name, target = symlink
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, target)


def _add_tar_file(*, archive: tarfile.TarFile, name: str, value: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(value)
    info.mode = mode
    archive.addfile(info, io.BytesIO(value))


def _write_tar(
    *,
    path: Path,
    members: dict[str, tuple[bytes, int]],
    link: tuple[str, str] | None = None,
    special_name: str | None = None,
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for directory in (".", "data"):
            info = tarfile.TarInfo(directory)
            info.type = tarfile.DIRTYPE
            archive.addfile(info)
        for name, (value, mode) in members.items():
            _add_tar_file(archive=archive, name=name, value=value, mode=mode)
        if link is not None:
            name, target = link
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            archive.addfile(info)
        if special_name is not None:
            info = tarfile.TarInfo(special_name)
            info.type = tarfile.FIFOTYPE
            archive.addfile(info)


def _required_windows_members() -> dict[str, bytes]:
    return {
        "LICENSE": b"license",
        "THIRD_PARTY_NOTICES.md": b"notices",
        "lcstats-relay.exe": b"launcher",
        "data/flutter_assets/app.so": b"payload",
        "python312.dll": b"packaged runtime",
    }


def _required_linux_members(*, launcher_mode: int = 0o755) -> dict[str, tuple[bytes, int]]:
    return {
        "LICENSE": (b"license", 0o644),
        "THIRD_PARTY_NOTICES.md": (b"notices", 0o644),
        "lcstats-relay": (b"launcher", launcher_mode),
        "data/flutter_assets/app.so": (b"payload", 0o644),
        "python3.12/__future__.pyc": (b"packaged runtime module", 0o644),
    }


def test_verify_desktop_archive_accepts_windows_bundle(*, tmp_path: Path) -> None:
    """Accept a ZIP with the launcher, notices, and application payload."""
    archive_path = tmp_path / "desktop.zip"
    members = _required_windows_members()
    members["site-packages/colorama/tests/test_ansi.py"] = b"dependency-owned tests"
    _write_zip(path=archive_path, members=members)

    assert (
        verify_desktop_archive(
            archive_path=archive_path,
            target="windows",
            launcher_name="lcstats-relay.exe",
        )
        == "3.12"
    )


def test_verify_desktop_archive_accepts_linux_bundle_and_safe_link(*, tmp_path: Path) -> None:
    """Accept an executable Linux launcher and a relative in-bundle symlink."""
    archive_path = tmp_path / "desktop.tar.gz"
    members = _required_linux_members()
    members["site-packages/fastapi/.agents/rules.md"] = (b"dependency metadata", 0o644)
    _write_tar(
        path=archive_path,
        members=members,
        link=("lib/libexample.so", "libexample.so.1"),
    )

    assert (
        verify_desktop_archive(
            archive_path=archive_path,
            target="linux",
            launcher_name="lcstats-relay",
        )
        == "3.12"
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("../secret", "unsafe archive path"),
        ("/secret", "unsafe archive path"),
        ("tests/test_app.py", "forbidden release content"),
        ("config/.env.production", "forbidden release content"),
        ("app/__pycache__/module.pyc", "forbidden release content"),
    ],
)
def test_verify_desktop_archive_rejects_unsafe_zip_content(
    *,
    tmp_path: Path,
    name: str,
    message: str,
) -> None:
    """Reject traversal and development-only content without extraction."""
    archive_path = tmp_path / "desktop.zip"
    members = _required_windows_members()
    members[name] = b"unsafe"
    _write_zip(path=archive_path, members=members)

    with pytest.raises(ValueError, match=message):
        verify_desktop_archive(
            archive_path=archive_path,
            target="windows",
            launcher_name="lcstats-relay.exe",
        )


def test_verify_desktop_archive_rejects_unsafe_zip_link(*, tmp_path: Path) -> None:
    """Reject a ZIP symlink that points outside the extracted archive."""
    archive_path = tmp_path / "desktop.zip"
    _write_zip(
        path=archive_path,
        members=_required_windows_members(),
        symlink=("data/current", "../outside"),
    )

    with pytest.raises(ValueError, match="unsafe archive path"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="windows",
            launcher_name="lcstats-relay.exe",
        )


def test_verify_desktop_archive_does_not_count_symlink_as_payload(*, tmp_path: Path) -> None:
    """Require real application payload beyond a safe but dangling link."""
    archive_path = tmp_path / "desktop.zip"
    members = _required_windows_members()
    members.pop("data/flutter_assets/app.so")
    _write_zip(
        path=archive_path,
        members=members,
        symlink=("data/current", "payload.bin"),
    )

    with pytest.raises(ValueError, match="no application payload"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="windows",
            launcher_name="lcstats-relay.exe",
        )


def test_verify_desktop_archive_rejects_ambiguous_python_runtime(*, tmp_path: Path) -> None:
    """Reject a bundle whose packaged Python runtime identity is ambiguous."""
    archive_path = tmp_path / "desktop.zip"
    members = _required_windows_members()
    members["python313.dll"] = b"another runtime"
    _write_zip(path=archive_path, members=members)

    with pytest.raises(ValueError, match="exactly one identifiable"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="windows",
            launcher_name="lcstats-relay.exe",
        )


@pytest.mark.parametrize(
    ("removed", "message"),
    [
        ("LICENSE", "missing required regular files"),
        ("lcstats-relay.exe", "missing required regular files"),
        ("data/flutter_assets/app.so", "no application payload"),
        ("python312.dll", "exactly one identifiable"),
    ],
)
def test_verify_desktop_archive_rejects_incomplete_bundle(
    *,
    tmp_path: Path,
    removed: str,
    message: str,
) -> None:
    """Require identity, notices, and payload beyond the launcher."""
    archive_path = tmp_path / "desktop.zip"
    members = _required_windows_members()
    members.pop(removed)
    _write_zip(path=archive_path, members=members)

    with pytest.raises(ValueError, match=message):
        verify_desktop_archive(
            archive_path=archive_path,
            target="windows",
            launcher_name="lcstats-relay.exe",
        )


@pytest.mark.filterwarnings("ignore:Duplicate name:UserWarning")
def test_verify_desktop_archive_rejects_duplicate_path(*, tmp_path: Path) -> None:
    """Reject ambiguous duplicate archive entries."""
    archive_path = tmp_path / "desktop.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, value in _required_windows_members().items():
            archive.writestr(name, value)
        archive.writestr("LICENSE", b"duplicate")

    with pytest.raises(ValueError, match="duplicate path"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="windows",
            launcher_name="lcstats-relay.exe",
        )


def test_verify_desktop_archive_rejects_non_executable_linux_launcher(*, tmp_path: Path) -> None:
    """Require executable mode bits to survive Linux tar packaging."""
    archive_path = tmp_path / "desktop.tar.gz"
    _write_tar(path=archive_path, members=_required_linux_members(launcher_mode=0o644))

    with pytest.raises(ValueError, match="not executable"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="linux",
            launcher_name="lcstats-relay",
        )


def test_verify_desktop_archive_rejects_unsafe_tar_link(*, tmp_path: Path) -> None:
    """Reject a tar link that escapes the archive root."""
    archive_path = tmp_path / "desktop.tar.gz"
    _write_tar(
        path=archive_path,
        members=_required_linux_members(),
        link=("lib/current", "../../outside"),
    )

    with pytest.raises(ValueError, match="unsafe archive path"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="linux",
            launcher_name="lcstats-relay",
        )


def test_verify_desktop_archive_rejects_backslash_tar_path(*, tmp_path: Path) -> None:
    """Reject host-specific separators in a raw tar member name."""
    archive_path = tmp_path / "desktop.tar.gz"
    members = _required_linux_members()
    members["folder\\secret"] = (b"unsafe", 0o644)
    _write_tar(path=archive_path, members=members)

    with pytest.raises(ValueError, match="unsafe archive path"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="linux",
            launcher_name="lcstats-relay",
        )


def test_verify_desktop_archive_rejects_special_tar_file(*, tmp_path: Path) -> None:
    """Reject device-like or other unsupported tar members."""
    archive_path = tmp_path / "desktop.tar.gz"
    _write_tar(
        path=archive_path,
        members=_required_linux_members(),
        special_name="runtime.pipe",
    )

    with pytest.raises(ValueError, match="unsupported special file"):
        verify_desktop_archive(
            archive_path=archive_path,
            target="linux",
            launcher_name="lcstats-relay",
        )


@pytest.mark.parametrize(
    ("target", "archive_name", "launcher", "message"),
    [
        ("windows", "missing.zip", "lcstats-relay.exe", "does not exist"),
        ("windows", "desktop.tar.gz", "lcstats-relay.exe", "does not match"),
        ("linux", "desktop.zip", "lcstats-relay", "does not match"),
        ("unknown", "desktop.zip", "lcstats-relay", "does not match"),
        ("windows", "desktop.zip", "../launcher", "unsafe archive path"),
        ("windows", "desktop.zip", "bin/launcher", "one safe root"),
    ],
)
def test_verify_desktop_archive_rejects_invalid_identity(
    *,
    tmp_path: Path,
    target: str,
    archive_name: str,
    launcher: str,
    message: str,
) -> None:
    """Require a matching target, format, and root launcher identity."""
    archive_path = tmp_path / archive_name
    if not archive_name.startswith("missing"):
        archive_path.write_bytes(b"not inspected for this rejected identity")

    with pytest.raises(ValueError, match=message):
        verify_desktop_archive(
            archive_path=archive_path,
            target=target,
            launcher_name=launcher,
        )


def test_main_verifies_windows_archive(*, tmp_path: Path) -> None:
    """Expose final archive verification through the Composite Action CLI."""
    archive_path = tmp_path / "desktop.zip"
    _write_zip(path=archive_path, members=_required_windows_members())

    assert (
        main(
            argv=[
                "--archive",
                str(archive_path),
                "--target",
                "windows",
                "--launcher",
                "lcstats-relay.exe",
            ]
        )
        == 0
    )
