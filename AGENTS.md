# Agent Instructions

## Agent Skills

Repository-local Agent Skills are deployed to `.agents/skills/` by
[APM](https://github.com/microsoft/apm). Do not edit that generated directory
directly.

## APM-managed Skills

- `apm.yml` pins the selected public
  [aoirint/skills](https://github.com/aoirint/skills); `apm.lock.yaml` records
  their resolved commits and content hashes.
- Keep this unpublished APM project at `version: 0.0.0` until its
  distribution and versioning design is explicitly decided.
- To restore the committed Skill set, run `apm install --frozen` from the
  repository root, then run `apm audit --ci`.
- Make shared Skill changes in
  [aoirint/skills](https://github.com/aoirint/skills) repository. This
  repository only selects, pins, and deploys them.
- To update the Skill dependency, review its source, commit pin, license, and
  cooldown first. Regenerate the lockfile with APM, then run
  `apm install --frozen` and `apm audit --ci`. Commit the manifest, lockfile,
  notices, and generated
  `.agents/skills/` changes together.

### Approved cooldown exception

Use APM CLI 0.26.0 for lock operations. Its normal seven-day cooldown was
explicitly waived because it fixes virtual-package `config-consistency` audit
failures. The waiver covers only the CLI release time gate.

A maintainer may explicitly waive the normal seven-day wait for the latest
`aoirint/skills` main commit. Record the waiver and exact full commit SHA in
the pull request. That waiver applies only to the `aoirint/skills` commit; it
does not waive review or cooldown requirements for any of its dependencies.

## Markdown Checks

Use pnpm 11 or newer. Keep the exact package pin and all fail-closed cooldown
settings when reproducing the Markdown check locally:

```shell
pnpm \
  --config.minimumReleaseAge=10080 \
  --config.minimumReleaseAgeStrict=true \
  --config.minimumReleaseAgeIgnoreMissingTime=false \
  --config.minimumReleaseAgeExclude= \
  dlx markdownlint-cli2@0.22.0 \
  --config .markdownlint-cli2.yaml \
  '**/*.md'
```

Add `--fix` after the package version to apply supported automatic fixes, then
run the normal command again. Some rules, including prose line length, still
require a meaning-preserving manual edit.

## Pull Request Merges

- Merge pull requests with squash merge.
- Before confirming the merge, set the squash commit title to
  `<pull request title> (#<number>)`, including the pull request number as in
  GitHub's default squash-merge title.

## Documentation

- Use `docs/README.md` as the developer documentation index.
- Put external systems, protocols, and behavioral contracts in `docs/domain/`.
- Put component boundaries, dependency direction, state ownership, and design
  decisions in `docs/architecture/`.
- Put reproducible development, verification, recovery, and release procedures
  in `docs/operations/`.
- Keep the fixed directories above even when one is temporarily small. New
  subdirectories are allowed when a topic outgrows a single document.
- Update the owning document in the same change as the behavior it describes.
  Do not copy one fact into several documents; link to its canonical owner.
- Record current behavior as current behavior. Label proposed designs, known
  limitations, and unverified release assumptions explicitly.
- Use `software-documentation-maintenance` for documentation-system changes and
  `prose-quality-check` for wording review.
