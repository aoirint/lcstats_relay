# Release desktop artifacts

## Scope

This procedure publishes Windows and Linux desktop archives to a GitHub Release.
The repository's immutable-release setting protects the tag and assets after
publication, and GitHub generates a release attestation for the published asset
set.

The canonical project version is `[project].version` in `pyproject.toml`.
Version `0.0.0` is a development placeholder that produces no release. Stable
and prerelease versions must be normalized PEP 440 versions. The workflow
creates the exact `v<project-version>` Git tag from the merged `main` commit.

## Prerequisites

- Prepare and merge the intended release changes through the normal pull request
  and required-check process.
- Set `[project].version` to the intended non-`0.0.0` release version in that
  reviewed commit. Do not create the release tag manually.
- Confirm that the Build, Lint, and Test pull request checks pass before merge.
  The Release workflow repeats their quality gates against the exact merged
  source commit before publication.
- Confirm that immutable releases remain enabled in the GitHub repository
  settings. The workflow checks this again before creating or publishing a
  release.

## Publish

Merge the version change and intended release contents into `main`. The push to
`main` starts the Release workflow. It performs these state-changing actions in
order:

1. Reads the normalized project version from `pyproject.toml`. Version `0.0.0`
   completes without release work. An already-published immutable version does
   so only after its exact asset set and attestation pass again.
2. Runs workflow lint, pin cooldown, Markdown lint, Ruff, strict mypy, and the
   full-coverage test suite against the resolved merged source commit.
3. Builds Windows and Linux from that same commit through the
   same local Composite Action used by the Build workflow.
4. Packages the Windows bundle as ZIP and the Linux bundle as tar.gz so Unix
   executable permissions survive extraction.
5. Creates `release-manifest.json` and `SHA256SUMS`, binding the artifacts to the
   source commit, workflow run, build number, Python, Flet, and uv versions.
6. Creates the version tag and mutable draft from the merged source commit, or
   resumes a matching draft, then uploads and checks the complete asset set.
7. Publishes the draft last. GitHub then makes the release tag and assets
   immutable and generates the release attestation.

The expected release assets are:

- `lcstats-relay-<version>-windows.zip`
- `lcstats-relay-<version>-linux.tar.gz`
- `release-manifest.json`
- `SHA256SUMS`

## Verify

Wait for the Release workflow to pass, then verify the release and each
downloaded artifact:

```powershell
gh release view v1.2.3 --json tagName,isDraft,isPrerelease,isImmutable,assets
gh release verify v1.2.3
gh release download v1.2.3 --dir dist
gh release verify-asset v1.2.3 dist/lcstats-relay-1.2.3-windows.zip
gh release verify-asset v1.2.3 dist/lcstats-relay-1.2.3-linux.tar.gz
```

Confirm that `isDraft` is `false`, `isImmutable` is `true`, the expected four
assets are present, and the downloaded archive digests match both
`release-manifest.json` and `SHA256SUMS`.

Release automation verifies the expected root launcher, license and notices,
absence of source-control/development content and unsafe paths, Linux executable
mode, checksums, and provenance. It does not replace target runtime checks.
Before announcing a release, launch the Windows and Linux bundles on their
supported target class and verify first run, configuration, tracker connection,
archive output, network failure, clean shutdown, and retained data after an
upgrade.

## Failure and recovery

- A validation or build failure creates no published release. Correct the source
  through a new pull request. A new `main` push reruns the version decision.
- An upload failure leaves a mutable draft. Re-running the failed workflow may
  replace the draft assets before publication when the source commit is
  unchanged.
- If another `main` commit lands with the same version while a draft exists, the
  workflow refuses to move its tag. Prefer a reviewed version bump; if the draft
  was never intended for publication, remove that mutable draft and tag through
  an explicit maintainer recovery action before rerunning.
- If the tag moves away from the commit built by the workflow, publication
  stops. Do not publish artifacts from a different commit under the same
  version.
- A published release is immutable. Do not attempt to replace its assets or move
  its tag. Correct a published defect with a new project version and release.

Update this procedure whenever the version source, supported targets, archive
formats, manifest schema, repository release controls, or workflow changes.
