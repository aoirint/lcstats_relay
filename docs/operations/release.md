# Release desktop artifacts

## Scope and version identity

The verified build profiles are **windows-amd64** (portable ZIP) and
**linux-amd64** (tar.gz, preserving executable modes and links). The Linux
baseline is Ubuntu 22.04 with an X11 desktop and GNOME Keyring providing Secret
Service. Native builds use the corresponding oldest supported GA runner.
Published 0.1.0 releases remain Windows-only; these profiles apply to candidates
and subsequent releases.

Windows ARM64 remains unavailable: Flet 1.0.4 bundles an x64 Python runtime and
forces x64 Windows output, including on ARM hosts. See the
[upstream release](https://github.com/flet-dev/flet/releases/tag/v1.0.4).
Do not label an emulated x64 executable as an ARM64 archive.
The immutable-release setting protects a published tag and asset set. Before
requesting the first release, an administrator enables that repository setting
and confirms it in their authenticated CLI session:

```sh
gh api repos/OWNER/REPO/immutable-releases --jq .enabled
```

The [setting API](https://docs.github.com/en/rest/repos/repos#check-if-immutable-releases-are-enabled-for-a-repository)
requires administration read access. CI uses `contents: write` for publication
and requires the actual published release to be immutable with a valid release
attestation.

The root `VERSION` contains one bare SemVer, optionally followed by one LF.
`0.0.0` reserves unreleased development and never creates a GitHub Release.
Use `0.1.0-alpha.N` while validating distribution, then `0.1.0` after target
verification. Tags and archive names retain the full SemVer; Flutter receives
its numeric three-part version. `pyproject.toml` stays at the source-package
placeholder `0.0.0` and is not the desktop release authority.

`CHANGELOG.md` is the canonical history. A release request adds a dated heading
such as `## 0.1.0-alpha.1 - 2026-10-24`. Publication selects that section as the
release body. Keep `Unreleased` for subsequent work.

## Reviewed build inputs

[`packaging/windows-toolchain.json`](../../packaging/windows-toolchain.json)
pins artifact URLs and SHA-256 digests for Flutter 3.44.8, Flet's 1.0.4 template,
serious_python's compatible embedded CPython 3.14.8 and dart_bridge 1.10.0.
The [Linux profile](../../packaging/linux-amd64-toolchain.json) pins the official
Linux SDK, runtime, compiler and bridge artifacts for the same versions. Their
releases satisfy the seven-day cooldown. The official template receives
the reviewed Dart lock; runtime/bootstrap code is unchanged.

The source/CI builder uses Python 3.14.9 and uv 0.13.5. Runtime wheels are
exported from `uv.lock` and downloaded with hash enforcement using the repaired
builder pip. Flet's packaging interpreter installs only those local wheels,
under exact constraints, with indexes and pip version checks disabled. The
embedded runtime contains no pip/ensurepip and carries certifi 2026.10.19.
The [Python security release](https://www.python.org/downloads/release/python-3149/)
addresses bundled pip's trust store; builder and embedded identities are
recorded separately rather than claiming they share a patch version.

The Dart graph in `packaging/pubspec.lock` contains 135 reviewed hosted
packages. Enforce its hashes before build execution and reject hosted graph
changes after Flet registers its official SecureStorage extension. Updating
these pins requires a fresh provenance, compatibility and cooldown review.

For a local Windows development build, restore the locked environment and run
PowerShell 7.4 or newer from the repository root, with Visual Studio's Desktop
C++ workload and ATL installed. For the unreleased `VERSION` value `0.0.0`:

```powershell
./.github/actions/build-desktop/build-windows.ps1 `
  -Version 0.0.0 -BuildVersion 0.0.0 -BuildNumber 1
```

Use the actual root version and its numeric build version for other candidates.
The script uses a workspace build directory when `RUNNER_TEMP` is unset. Its
first run downloads the reviewed SDK and runtime artifacts. It does not request
publication.

## Verification and publication

1. PRs run source checks and the full test suite with read-only permissions.
   They do not build desktop binaries. Main builds the integrated source.
   For packaging or platform changes, run the `Desktop Build` workflow manually
   against the candidate branch before merging. It repeats source validation,
   produces a verified candidate and render evidence, and does not publish.
   Select `windows-amd64`, `linux-amd64` or `all`; each build records its native
   CPU architecture as well as its Python version.
2. Each native job builds, launches the actual bundled executable, captures its
   rendered first page and records actual Python/Flet/TLS versions.
3. Three separate launches save an inert credential for a reserved-domain key,
   read it after restart and delete it, then confirm its absence. Temporary
   settings and logs are isolated from production data. Linux uses Xvfb and a
   separate D-Bus session with a temporary, unlocked GNOME Keyring. No live GAS request
   is made.
4. Retain Python package licenses, Flutter notices and versioned Dart source
   references. Exclude unused Tk, debug/test artifacts and caches; reject media
   runtimes outside this profile.
5. Package and inspect the same verified directory. Main repeats the gate for
   its exact commit even when `VERSION` remains `0.0.0`.
6. For a release request, publication downloads that job's artifact, creates
   checksums and schema-4 provenance, selects the dated changelog entry and
   verifies or creates the tag at the exact source commit, and prepares a mutable
   draft with `--verify-tag`. Verify source/tag identity before publishing, then
   require actual immutability and verify the release attestation. Do not rebuild
   the artifact.

New archives use `lcstats-relay-v{VERSION}-{OS}-{ARCH}.{EXT}`. OS labels are
`windows`, `linux` and `macos`; architecture labels are `amd64` and `arm64`.
These labels define naming, not additional supported build targets. The current
Windows archive is `lcstats-relay-v{VERSION}-windows-amd64.zip`. Previously
published immutable releases retain their original asset names.

A new release requires exactly one archive for each supported target plus
`SHA256SUMS` and `release-manifest.json`. Each archive includes `VERSION`,
`runtime-report.json`, licenses and the application. Publication rejects a
missing target, an unexpected archive name or inconsistent native architecture.
Existing releases are checked against their own signed manifests.
Alpha releases are marked prerelease and do not replace Latest.

Before promoting an alpha, verify configuration, OS credential persistence,
tracker receipt, archive output, network-failure behavior, clean shutdown and
retained data on the target installation. The native CI probe supplements
these operational checks. It does not claim live destination authentication.

## Failure and recovery

A source, build, startup or credential failure creates no published release.
Correct the candidate through a follow-up commit/PR and repeat the gates. An
upload failure can leave a mutable draft; retries may replace its assets only
when the source commit is unchanged. If its tag identifies another commit,
use a reviewed version bump or explicitly authorized draft recovery. Correct a
published immutable release with a new version, never by replacing its assets
or moving its tag.

## Linux runtime prerequisites

The Linux archive bundles Python and the application, not the desktop session.
On the supported Ubuntu baseline, install `libgtk-3-0`, `libsecret-1-0`,
`libjsoncpp25`, `libstdc++6` and `gnome-keyring`. Run the app in a graphical user
session with its Secret Service unlocked. The app reports a credential-store
failure when that service is unavailable; it does not save plaintext tokens.

After extraction, run `./lcstats-relay`. For a local native build, restore the
locked uv environment and install the build dependencies listed in the
`build-desktop` action, then run from the repository root:

```sh
bash .github/actions/build-desktop/build-linux.sh VERSION BUILD_VERSION BUILD_NUMBER dist
```

Replace the first three arguments with the actual root version, its numeric
three-part build version and a positive build number. The same script runs the
isolated native rendering and keyring checks before creating a tar.gz.
