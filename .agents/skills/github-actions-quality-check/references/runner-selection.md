# GitHub-hosted Linux Runner Selection

Select a runner per job from its actual resource, isolation, tool, and duration requirements. Do
not copy one workflow-wide label into every job without checking those requirements.

## Prefer `ubuntu-slim` for lightweight jobs

Use `ubuntu-slim` when all of these conditions hold:

- The job is short-running with enough measured headroom below the fixed 15-minute limit.
- One x64 CPU, 5 GB RAM, and 14 GB storage are sufficient.
- The job works in an unprivileged container on a shared VM.
- Every required command is in the current slim image inventory or is installed explicitly from a
  reviewed, pinned, integrity-checked source.
- Every external or local action used by the job is compatible with the slim environment.

Good candidates include repository metadata checks, issue or release API automation, small
format/lint/type/test jobs, and lightweight artifact assembly or publication. Measure the real job;
the category alone does not prove it fits.

`ubuntu-slim` is not a smaller full VM. GitHub provisions an unprivileged container with a minimal
tool set. Do not select it for jobs that require filesystem mounts, Docker-in-Docker, low-level
kernel features, nested virtualization, emulators, or other privileged host access. Treat Docker
container actions and service containers as unsupported until current official documentation and a
representative run prove the exact use case works. The installed Docker client does not imply that
a usable Docker daemon is available.

Avoid `ubuntu-slim` for typical heavyweight CI/CD builds, large native compilation, desktop/mobile
packaging toolchains, or jobs whose duration can approach 15 minutes. Split a genuinely lightweight
preflight or publication phase from a heavyweight build when the dependency graph remains explicit;
do not split jobs merely to claim slim usage.

## Choose a full Ubuntu VM deliberately

Use a standard Ubuntu VM when the job needs more CPU or memory, a full preinstalled toolchain,
privileged VM behavior, or longer execution. Prefer an explicit supported label such as
`ubuntu-24.04` when the OS version or native ABI is part of the build contract. Use
`ubuntu-latest` only when automatically following GitHub's newest stable Ubuntu image is an intended
maintenance policy and migration risk has been accepted.

Do not infer that `-latest` means the newest upstream Ubuntu release; it means GitHub's latest stable
hosted image and changes over time.

## Validate the selection

1. Read the current GitHub-hosted runner reference and `ubuntu-slim` software inventory before a
   migration; both runner capabilities and installed versions can change.
2. Inventory shell commands, local actions, external actions, package installation, caches,
   containers, services, artifacts, permissions, and expected peak resource use for each job.
3. Set `timeout-minutes` to at most 15 on a slim job. Leave operational headroom rather than using
   the limit as the expected duration.
4. Run every changed slim job on a representative event. Check setup logs, action compatibility,
   elapsed time, peak behavior, and outputs; a YAML-only review is insufficient.
5. Keep heavy and platform-specific jobs on the full runner they require. Record why each exception
   cannot use slim so future reviews can reconsider it.

Primary references:

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://github.com/actions/runner-images/blob/main/images/ubuntu-slim/ubuntu-slim-Readme.md
