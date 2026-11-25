#!/usr/bin/env bash
set -euo pipefail
task_bundle="$1"
task_version="$2"
task_profile="$3"
task_probe="$PWD/build/native-probe"
mkdir -p "$task_probe" "$task_probe/data" "$task_probe/config" "$task_probe/cache" "$task_probe/state"
export XDG_DATA_HOME="$task_probe/data" XDG_CONFIG_HOME="$task_probe/config"
mkdir -p "$task_probe/run"
chmod 700 "$task_probe/run"
export XDG_RUNTIME_DIR="$task_probe/run"
export XDG_CACHE_HOME="$task_probe/cache" XDG_STATE_HOME="$task_probe/state"
export FLET_APP_CONSOLE="$task_probe/console.log" PYTHONDONTWRITEBYTECODE=1
# Exercise native Wayland without an X11 or XWayland fallback.
unset DISPLAY WAYLAND_SOCKET
export GDK_BACKEND=wayland LIBGL_ALWAYS_SOFTWARE=1
export WAYLAND_DISPLAY=wayland-lcstats
weston --backend=headless --renderer=gl --no-config --idle-time=0 \
  --socket="$WAYLAND_DISPLAY" > "$task_probe/weston.log" 2>&1 &
weston_pid=$!
trap 'kill "$weston_pid" 2>/dev/null || true; wait "$weston_pid" 2>/dev/null || true' EXIT
for ((attempt=0; attempt<100; attempt++)); do
  [[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]] && break
  kill -0 "$weston_pid" 2>/dev/null || break
  sleep 0.1
done
if ! [[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]] || ! kill -0 "$weston_pid" 2>/dev/null; then
  cat "$task_probe/weston.log" >&2
  exit 1
fi
export LCSTATS_RELAY_STARTUP_CHECK="$task_probe/startup.json"
LCSTATS_RELAY_PROBE_VALUE="$(uv run --locked python -c 'import secrets; print(secrets.token_hex(24))')"
export LCSTATS_RELAY_PROBE_VALUE

# Create and unlock only this isolated session's GNOME login keyring.
printf '%s' "$LCSTATS_RELAY_PROBE_VALUE" | gnome-keyring-daemon --unlock --components=secrets \
  > "$task_probe/keyring.log" 2>&1
for task_phase in write read-delete absent; do
  export LCSTATS_RELAY_PROBE_PHASE="$task_phase"
  rm -f "$LCSTATS_RELAY_STARTUP_CHECK"
  timeout --kill-after=5 45 "$task_bundle/lcstats-relay" \
    > "$task_probe/$task_phase-stdout.log" 2> "$task_probe/$task_phase-stderr.log"
  uv run --locked python - "$task_version" "$task_profile" "$task_bundle" <<'PY'
from pathlib import Path
import hashlib,json,os,struct,sys
report=Path(os.environ['LCSTATS_RELAY_STARTUP_CHECK']);data=json.loads(report.read_text())
profile=json.loads(Path(sys.argv[2]).read_text())
assert data['version']==sys.argv[1]
assert data['python_version']==profile['embedded_python']
assert data['flet_version']==profile['flet'] and data['certifi_version']==profile['certifi']
assert data['architecture_bits']==64 and data['width']>0 and data['height']>0
assert data['architecture']==profile['architecture']
assert hashlib.sha256(report.with_suffix('.png').read_bytes()).hexdigest()==data['png_sha256']
header=(Path(sys.argv[3])/'lcstats-relay').read_bytes()[:20]
assert header[:6]==b'\x7fELF\x02\x01' and struct.unpack('<H',header[18:20])[0]=={'amd64':62,'arm64':183}[profile['architecture']],'Wrong executable architecture'
PY
  printf 'Native render and credential phase passed: %s\n' "$task_phase"
done
uv run --locked python - "$task_bundle" <<'PY'
from pathlib import Path
import json,os,sys
data=json.loads(Path(os.environ['LCSTATS_RELAY_STARTUP_CHECK']).read_text())
data.update(credential_restart_check=True,credential_phases=['write','read-delete','absent'])
(Path(sys.argv[1])/'runtime-report.json').write_text(json.dumps(data,indent=2)+'\n')
PY
