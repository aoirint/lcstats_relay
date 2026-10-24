# Release desktop artifacts

## Scope and version identity

The first release profile is **Windows x64**, distributed as a portable ZIP.
Linux source checks remain in CI; native Linux release verification is deferred.
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
Their releases satisfy the seven-day cooldown. The official template receives
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
2. The Windows job builds, launches the actual bundled executable, captures its
   rendered first page and records actual Python/Flet/TLS versions.
3. Three separate launches save an inert credential for a reserved-domain key,
   read it after restart and delete it, then confirm its absence. Temporary
   settings and logs are isolated from production data. No live GAS request
   is made.
4. Retain Python package licenses, Flutter notices and versioned Dart source
   references. Exclude unused Tk, debug/test artifacts and caches; reject media
   runtimes outside this profile.
5. Package and inspect the same verified directory. Main repeats the gate for
   its exact commit even when `VERSION` remains `0.0.0`.
6. For a release request, publication downloads that job's artifact, creates
   checksums and schema-3 provenance, selects the dated changelog entry and
   verifies or creates the tag at the exact source commit, and prepares a mutable
   draft with `--verify-tag`. Verify source/tag identity before publishing, then
   require actual immutability and verify the release attestation. Do not rebuild
   the artifact.

A release contains the Windows ZIP, `SHA256SUMS` and `release-manifest.json`.
The ZIP includes `VERSION`, `runtime-report.json`, licenses and the application.
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
