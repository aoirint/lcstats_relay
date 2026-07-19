# Agent Instructions

## Agent Skills

Repository-local Agent Skills are deployed to `.agents/skills/` by
[APM](https://github.com/microsoft/apm). Do not edit that generated directory
directly.

## APM-managed Skills

- `apm.yml` pins the selected public
  [aoirint/skills](https://github.com/aoirint/skills); `apm.lock.yaml` records
  their resolved commits and content hashes.
- The initial pin is an explicit maintainer-directed exception to the normal
  seven-day dependency cooldown so this repository can adopt the current Flet
  quality baseline immediately.
- To restore the committed Skill set, run `apm install --frozen` from the
  repository root, then run `apm audit --ci`.
- Make all Skill changes in the public
  [aoirint/skills](https://github.com/aoirint/skills) repository. This
  repository only selects, pins, and deploys those Skills.
- To update a Skill dependency, review its source, commit pin, license, and
  cooldown first. Update `apm.yml`, run `apm lock`, review `apm.lock.yaml`, run
  `apm install --frozen` and `apm audit --ci`, then commit the manifest,
  lockfile, and generated `.agents/skills/` changes together.

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
