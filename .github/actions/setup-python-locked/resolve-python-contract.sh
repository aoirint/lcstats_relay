#!/usr/bin/env bash

set -euo pipefail

main() {
  : "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"

  local -a versions
  mapfile -t versions <.python-version
  local python_version=${versions[0]:-}
  python_version=${python_version%$'\r'}
  if [[ ${#versions[@]} -ne 1 || -z "$python_version" ]]; then
    printf '.python-version must select one Python version.\n' >&2
    return 1
  fi

  {
    printf 'python_version=%s\n' "$python_version"
    # Security exception: uv 0.13.5 removes compromised CA trust and supplies
    # repaired managed Python builds. Normal seven-day eligibility: 2026-10-29.
    printf 'uv_version=0.13.5\n'
  } >>"$GITHUB_OUTPUT"
}

main "$@"
