#!/usr/bin/env bash
set -euo pipefail

task_version="$1"
task_build_version="$2"
task_build_number="$3"
task_output="$4"
case "$(uname -m)" in
  x86_64) task_arch=amd64 ;;
  aarch64) task_arch=arm64 ;;
  *) echo "Unsupported Linux host architecture" >&2; exit 1 ;;
esac
task_profile="packaging/linux-$task_arch-toolchain.json"
task_tools="${RUNNER_TEMP:-$PWD/.venv/native-tools}/lcstats-linux"
mkdir -p "$task_tools/downloads"
export FLET_CACHE_DIR="$task_tools/flet-cache" PUB_CACHE="$task_tools/pub-cache"
export PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONOPTIMIZE=0

# Download and verify the same upstream inputs consumed by Flet's native build.
while IFS=$'\t' read -r task_name task_url task_hash task_cache; do
  task_file="$task_tools/downloads/$task_name"
  curl --fail --location --silent --show-error --retry 3 "$task_url" -o "$task_file"
  printf '%s  %s\n' "$task_hash" "$task_file" | sha256sum --check --status
  if [[ -n "$task_cache" ]]; then
    mkdir -p "$(dirname "$FLET_CACHE_DIR/$task_cache")"
    cp "$task_file" "$FLET_CACHE_DIR/$task_cache"
  fi
done < <(jq -r '.inputs[] | [.name,.url,.sha256,(.cache // "")] | @tsv' "$task_profile")

if jq --exit-status '.flutter_source' "$task_profile" >/dev/null; then
  mkdir -p "$task_tools/sdk"
  git clone --quiet --depth 1 --branch "$(jq -r .flutter_source.tag "$task_profile")" \
    "$(jq -r .flutter_source.repository "$task_profile")" "$task_tools/sdk/flutter"
  [[ "$(git -C "$task_tools/sdk/flutter" rev-parse HEAD)" == "$(jq -r .flutter_source.revision "$task_profile")" ]]
fi
uv run --locked python - "$task_tools" "$task_profile" <<'PY'
import json,os,stat,sys,tarfile,zipfile
from pathlib import Path,PurePosixPath
root=Path(sys.argv[1]);profile=json.loads(Path(sys.argv[2]).read_text())
(root/'sdk').mkdir(exist_ok=True)
if source:=profile.get('flutter_source'):
    sdk=root/'sdk/flutter';cache=sdk/'bin/cache';cache.mkdir(parents=True,exist_ok=True)
    assert (sdk/'bin/internal/engine.version').read_text().strip()==source['engine_revision']
    for entry in profile['inputs']:
        if 'sdk_extract' not in entry:continue
        target=cache/entry['sdk_extract'];target.mkdir(parents=True,exist_ok=True)
        assert target.resolve().is_relative_to(cache.resolve())
        with zipfile.ZipFile(root/'downloads'/entry['name']) as archive:
            for member in archive.infolist():
                path=PurePosixPath(member.filename)
                assert not path.is_absolute() and '..' not in path.parts and chr(92) not in member.filename
                assert not stat.S_ISLNK(member.external_attr>>16)
            archive.extractall(target)
            for member in archive.infolist():
                mode=(member.external_attr>>16)&0o777
                if mode&0o111:os.chmod(target/member.filename,mode)
    for name in ('engine-dart-sdk','flutter_sdk','linux-sdk'):
        (cache/f'{name}.stamp').write_text(source['engine_revision'])
    (cache/'material_fonts.stamp').write_text(source['material_fonts_version'])
else:
    with tarfile.open(root/'downloads/flutter') as archive:
        archive.extractall(root/'sdk',filter='data')
PY
export FLUTTER_ROOT="$task_tools/sdk/flutter"
export PATH="$FLUTTER_ROOT/bin:$PATH"
flutter --version
flutter --version --machine > "$task_tools/flutter-version.json"
jq --exit-status --arg version "$(jq -r .flutter "$task_profile")" \
  '.frameworkVersion == $version' "$task_tools/flutter-version.json" >/dev/null

uv export --locked --no-dev --no-default-groups --no-emit-project --no-header --no-annotate \
  --output-file "$task_tools/requirements.txt" >/dev/null
uv export --locked --no-dev --no-default-groups --no-emit-project --no-header --no-annotate \
  --no-hashes --output-file "$task_tools/constraints.txt" >/dev/null
uv python install "$(cat .python-version)"
task_builder="$(uv python find --system --managed-python)"
[[ "$("$task_builder" -c 'import pip; print(pip.__version__)')" == "$(jq -r .builder_pip "$task_profile")" ]]
"$task_builder" -m pip download --disable-pip-version-check --require-hashes --only-binary=:all: \
  --dest "$task_tools/wheels" --requirement "$task_tools/requirements.txt"
export PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_COMPILE=1
export PIP_FIND_LINKS="file://$task_tools/wheels" PIP_CONSTRAINT="file://$task_tools/constraints.txt"
export SERIOUS_PYTHON_VERSION=3.14
SERIOUS_PYTHON_FULL_VERSION="$(jq -r .embedded_python "$task_profile")"
SERIOUS_PYTHON_BUILD_DATE="$(jq -r .python_build "$task_profile")"
SERIOUS_PYTHON_DIST_RELEASE="$(jq -r .compiler_build "$task_profile")"
export SERIOUS_PYTHON_FULL_VERSION SERIOUS_PYTHON_BUILD_DATE SERIOUS_PYTHON_DIST_RELEASE

# Stage the official, uv-locked extension outside Flet's regenerated build tree.
uv run --locked python - <<'PY'
from importlib.metadata import distribution
from pathlib import Path
import shutil
source=distribution('flet-secure-storage').locate_file('flutter/flet_secure_storage')
shutil.copytree(source,Path('.venv/flutter-extensions/flet_secure_storage'),dirs_exist_ok=True)
PY
mkdir -p build/flutter
cp packaging/pubspec.yaml packaging/pubspec.lock build/flutter/
dart pub get --enforce-lockfile --directory build/flutter

uv run --locked python - "$task_tools" <<'PY'
from pathlib import Path
import shutil,sys,zipfile
root=Path(sys.argv[1]);shutil.copyfile(root/'downloads/template',root/'reviewed-template.zip')
with zipfile.ZipFile(root/'reviewed-template.zip','a') as archive:
    archive.write('packaging/pubspec.lock','build/{{cookiecutter.out_dir}}/pubspec.lock')
PY
uv run --locked flet build linux --project lcstats_relay --python-version 3.14 \
  --template "$task_tools/reviewed-template.zip" --build-version "$task_build_version" \
  --build-number "$task_build_number" --yes --verbose

uv run --locked python - <<'PY'
from pathlib import Path
import hashlib,json,os,shutil,yaml
def hosted(path):
    packages=yaml.safe_load(Path(path).read_text())['packages']
    assert all(p['source'] in {'hosted','sdk','path'} for p in packages.values())
    assert {n for n,p in packages.items() if p['source']=='path'}=={'flet_secure_storage'}
    return {n:(p['version'],p['description']) for n,p in packages.items() if p['source']=='hosted'}
assert hosted('build/flutter/pubspec.lock')==hosted('packaging/pubspec.lock'),'Dart lock drift'
bundle=Path('build/linux').resolve()
for relative in ('python3.14/test','python3.14/idlelib','python3.14/tkinter','python3.14/turtledemo'):
    target=bundle/relative
    assert target.resolve().is_relative_to(bundle)
    if target.exists():shutil.rmtree(target)
for path in bundle.rglob('__pycache__'):
    assert path.resolve().is_relative_to(bundle)
    shutil.rmtree(path)
for path in bundle.rglob('*'):
    if path.is_file() and path.name.startswith(('_test','_dbm.','_tkinter.')) and path.suffix=='.so':path.unlink()
    assert not (path.is_file() and any(n in path.name.lower() for n in ('mpv','ffmpeg'))),'Unexpected media runtime'
for relative in ('python3.14/ensurepip','site-packages/pip','site-packages/flet_cli','site-packages/flet_desktop','site-packages/flet_web'):
    assert not (bundle/relative).exists(),f'Unexpected runtime tooling: {relative}'
for name in ('VERSION','LICENSE','THIRD_PARTY_NOTICES.md'):shutil.copyfile(name,bundle/name)
licenses=bundle/'licenses';licenses.mkdir(exist_ok=True)
sources=json.loads(Path('packaging/licenses/SOURCES.json').read_text())
sources=[s for s in sources if s['file'] not in {'PYTHON-WINDOWS-LICENSE.txt','LIBLZMA-COPYING.txt'}]
for source in sources:
    path=Path('packaging/licenses')/source['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256'],'License provenance mismatch'
    shutil.copyfile(path,licenses/path.name)
(licenses/'SOURCES.json').write_text(json.dumps(sources,indent=2)+'\n')
notice_root=Path('packaging/licenses/linux-python')
for notice in json.loads((notice_root/'SOURCES.json').read_text())['files']:
    assert hashlib.sha256((notice_root/notice['file']).read_bytes()).hexdigest()==notice['sha256']
shutil.copytree(notice_root,licenses/'python',dirs_exist_ok=True)

sdk=Path(os.environ['FLUTTER_ROOT'])
shutil.copyfile(sdk/'LICENSE',licenses/'FLUTTER-LICENSE.txt')
shutil.copyfile(sdk/'bin/cache/dart-sdk/LICENSE',licenses/'DART-LICENSE.txt')
sources=[]
for name,pkg in yaml.safe_load(Path('packaging/pubspec.lock').read_text())['packages'].items():
    if pkg['source']!='hosted':continue
    source=Path(os.environ['PUB_CACHE'])/'hosted/pub.dev'/f"{name}-{pkg['version']}"
    notices=[p for p in source.iterdir() if p.is_file() and p.name.lower().startswith(('license','licence','copying','notice','copyright'))]
    assert notices,f'Missing upstream license: {name}'
    target=licenses/'dart'/name;target.mkdir(parents=True,exist_ok=True)
    for notice in notices:shutil.copyfile(notice,target/notice.name)
    sources.append({'name':name,'version':pkg['version'],'source':f"https://pub.dev/api/archives/{name}-{pkg['version']}.tar.gz",'sha256':pkg['description']['sha256']})
(licenses/'dart/SOURCES.json').write_text(json.dumps(sources,indent=2)+'\n')
assert (bundle/'data/flutter_assets/NOTICES.Z').is_file()
PY

# The keyring and display live for all three independent executable launches.
xvfb-run --auto-servernum dbus-run-session -- bash \
  .github/actions/build-desktop/verify-linux.sh "$PWD/build/linux" "$task_version" "$task_profile"
task_name="lcstats-relay-v$task_version-linux-$task_arch"
uv run --locked python scripts/package_desktop.py --build-directory build/linux \
  --output-directory "$task_output" --artifact-name "$task_name" --format gztar
uv run --locked python scripts/verify_desktop_archive.py --target linux \
  --archive "$task_output/$task_name.tar.gz" --launcher lcstats-relay
