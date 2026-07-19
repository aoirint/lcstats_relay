# Release desktop artifacts

## Scope

This procedure publishes Windows and Linux desktop archives to a GitHub Release.
The repository's immutable-release setting protects the tag and assets after
publication, and GitHub generates a release attestation for the published asset
set.

The canonical project version is `[project].version` in `pyproject.toml`.
Version `0.0.0` is an unreleasable development placeholder. Stable and
prerelease versions must be normalized PEP 440 versions whose Git tag is exactly
`v<project-version>`.

## Prerequisites

- Prepare and merge the intended release changes through the normal pull request
  and required-check process.
- Set `[project].version` to the intended non-`0.0.0` release version in that
  reviewed commit.
- Confirm that the Build, Lint, and Test workflows pass on `main`.
- Confirm that immutable releases remain enabled in the GitHub repository
  settings. The workflow checks this again before creating or publishing a
  release.
- Use a clean local checkout whose `main` exactly matches `origin/main`.

## Publish

Create an annotated tag on the reviewed `main` commit and push only that tag:

```powershell
git switch main
git fetch origin main
git merge --ff-only origin/main
git tag --annotate v1.2.3 --message "v1.2.3"
git push origin v1.2.3
```

Replace `1.2.3` with the exact normalized project version. The tag push starts
the Release workflow. It performs these state-changing actions in order:

1. Rejects a tag that differs from `pyproject.toml` or still uses `0.0.0`.
2. Builds Windows and Linux from the resolved tagged commit through the same
   local Composite Action used by the Build workflow.
3. Packages the Windows bundle as ZIP and the Linux bundle as tar.gz so Unix
   executable permissions survive extraction.
4. Creates `release-manifest.json` and `SHA256SUMS`, binding the artifacts to the
   source commit, workflow run, build number, Python, Flet, and uv versions.
5. Creates or reuses a mutable draft, uploads the complete asset set, and checks
   the exact uploaded file names.
6. Publishes the draft last. GitHub then makes the release tag and assets
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

Release automation verifies artifact structure and provenance but does not
replace target runtime checks. Before announcing a release, launch the Windows
and Linux bundles on their supported target class and verify first run,
configuration, tracker connection, archive output, network failure, clean
shutdown, and retained data after an upgrade.

## Failure and recovery

- A validation or build failure creates no release. Correct the source through a
  new pull request before replacing or pushing another tag.
- An upload failure leaves a mutable draft. Re-running the failed workflow may
  replace the draft assets before publication.
- If the tag moves away from the commit built by the workflow, publication stops.
  Restore the reviewed tag before rerunning; do not publish artifacts from a
  different commit under the same version.
- A published release is immutable. Do not attempt to replace its assets or move
  its tag. Correct a published defect with a new project version and release.

Update this procedure whenever the version source, supported targets, archive
formats, manifest schema, repository release controls, or workflow changes.
