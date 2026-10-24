#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$BuildVersion,
    [Parameter(Mandatory)][string]$BuildNumber,
    [string]$OutputDirectory = "dist"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$ProgressPreference = "SilentlyContinue"
$taskRoot = (Get-Location).Path
$taskBuild = Join-Path $taskRoot "build"
$taskTools = if ($env:RUNNER_TEMP) { Join-Path $env:RUNNER_TEMP "lcstats-build" } else { Join-Path $taskRoot ".venv/native-tools" }
$taskProfile = Get-Content -LiteralPath "packaging/windows-toolchain.json" -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $taskTools | Out-Null
$taskDownloads = Join-Path $taskTools "downloads"
New-Item -ItemType Directory -Force -Path $taskDownloads | Out-Null
$env:FLET_CACHE_DIR = Join-Path $taskTools "flet-cache"
$env:PUB_CACHE = Join-Path $taskTools "pub-cache"
$env:PIP_CACHE_DIR = Join-Path $taskTools "pip-cache"
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONOPTIMIZE = "0"

# Verify upstream archives before executing or staging any of their contents.
$taskFiles = @{}
foreach ($taskInput in $taskProfile.inputs) {
    $taskFile = Join-Path $taskDownloads $taskInput.name
    if (-not (Test-Path -LiteralPath $taskFile)) {
        Write-Host "Download reviewed input: $($taskInput.name)"
        Invoke-WebRequest -Uri $taskInput.url -OutFile $taskFile
    }
    if ((Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskInput.sha256) {
        throw "Reviewed input checksum mismatch: $($taskInput.name)"
    }
    $taskFiles[$taskInput.name] = $taskFile
    if ($taskInput.cache) {
        $taskCacheFile = Join-Path $env:FLET_CACHE_DIR $taskInput.cache
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $taskCacheFile) | Out-Null
        Copy-Item -LiteralPath $taskFile -Destination $taskCacheFile
    }
}

$taskSdk = Join-Path $taskTools "sdk"
if (-not (Test-Path -LiteralPath (Join-Path $taskSdk "flutter/bin/flutter.bat"))) {
    # Expand-Archive requires a .zip suffix; the reviewed download has a stable name.
    Copy-Item -LiteralPath $taskFiles.flutter -Destination (Join-Path $taskDownloads "flutter.zip")
    Expand-Archive -LiteralPath (Join-Path $taskDownloads "flutter.zip") -DestinationPath $taskSdk
}
$env:FLUTTER_ROOT = Join-Path $taskSdk "flutter"
$env:PATH = "$(Join-Path $env:FLUTTER_ROOT 'bin');$env:PATH"
$taskFlutter = Join-Path $env:FLUTTER_ROOT "bin/flutter.bat"
$taskDart = Join-Path $env:FLUTTER_ROOT "bin/cache/dart-sdk/bin/dart.exe"
# First invocation can emit bootstrap output before machine-readable JSON.
& $taskFlutter --version
$taskFlutterJson = & $taskFlutter --version --machine | Out-String
$taskFlutterMetadata = $taskFlutterJson | ConvertFrom-Json
if ($taskFlutterMetadata.frameworkVersion -ne $taskProfile.flutter) { throw "Unexpected Flutter SDK" }

# Download only the uv-locked runtime wheels with the repaired builder's pip.
$taskWheels = Join-Path $taskTools "wheels"
$taskRequirements = Join-Path $taskTools "runtime-requirements.txt"
$taskConstraints = Join-Path $taskTools "runtime-constraints.txt"
uv export --locked --no-dev --no-default-groups --no-emit-project --no-header --no-annotate --output-file $taskRequirements | Out-Null
uv export --locked --no-dev --no-default-groups --no-emit-project --no-header --no-annotate --no-hashes --output-file $taskConstraints | Out-Null
if (-not $env:UV_PYTHON_INSTALL_DIR) { $env:UV_PYTHON_INSTALL_DIR = Join-Path $taskTools "python" }
$env:UV_PYTHON_BIN_DIR = Join-Path $taskTools "python-bin"
uv python install ((Get-Content -LiteralPath .python-version -Raw).Trim())
$taskBuilder = uv python find --system --managed-python
$taskPipVersion = & $taskBuilder -c "import pip; print(pip.__version__)"
if ($taskPipVersion -ne $taskProfile.builder_pip) { throw "Unexpected packaging pip version" }
& $taskBuilder -m pip download --disable-pip-version-check --require-hashes --only-binary=:all: --dest $taskWheels --requirement $taskRequirements
$env:PIP_NO_INDEX = "1"
$env:PIP_FIND_LINKS = ([Uri]$taskWheels).AbsoluteUri
$env:PIP_CONSTRAINT = ([Uri]$taskConstraints).AbsoluteUri
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_COMPILE = "1"
$env:SERIOUS_PYTHON_VERSION = "3.14"
$env:SERIOUS_PYTHON_FULL_VERSION = $taskProfile.embedded_python
$env:SERIOUS_PYTHON_BUILD_DATE = $taskProfile.python_build
$env:SERIOUS_PYTHON_DIST_RELEASE = $taskProfile.compiler_build

# Reference the uv-locked extension installed outside Flet's regenerated output.
if (-not (Test-Path -LiteralPath ".venv/Lib/site-packages/flutter/flet_secure_storage/pubspec.yaml")) { throw "Official SecureStorage extension missing" }
New-Item -ItemType Directory -Force -Path (Join-Path $taskBuild "flutter") | Out-Null
Copy-Item -LiteralPath packaging/pubspec.yaml, packaging/pubspec.lock -Destination (Join-Path $taskBuild "flutter")
& $taskDart pub get --enforce-lockfile --directory (Join-Path $taskBuild "flutter")

# Add only the reviewed lock to the official template. Runtime/bootstrap code stays intact.
$taskTemplate = Join-Path $taskTools "reviewed-template.zip"
Copy-Item -LiteralPath $taskFiles.template -Destination $taskTemplate
$taskZip = [System.IO.Compression.ZipFile]::Open($taskTemplate, [System.IO.Compression.ZipArchiveMode]::Update)
try {
    $taskEntry = $taskZip.CreateEntry("build/{{cookiecutter.out_dir}}/pubspec.lock")
    $taskStream = $taskEntry.Open()
    try {
        $taskLockBytes = [System.IO.File]::ReadAllBytes((Join-Path $taskRoot "packaging/pubspec.lock"))
        $taskStream.Write($taskLockBytes, 0, $taskLockBytes.Length)
    } finally { $taskStream.Dispose() }
} finally { $taskZip.Dispose() }

uv run --locked flet build windows --project lcstats_relay --python-version 3.14 --template $taskTemplate --build-version $BuildVersion --build-number $BuildNumber --yes --verbose

# Flet's extension registration changes its path spelling, not hosted resolutions.
# Reject any change in the reviewed set, versions, archive hashes or sources.
@'
from pathlib import Path
import yaml
def hosted(path):
    packages = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["packages"]
    assert all(p["source"] in {"hosted", "sdk", "path"} for p in packages.values())
    assert {n for n,p in packages.items() if p["source"] == "path"} == {"flet_secure_storage"}
    return {n:(p["version"],p["description"]) for n,p in packages.items() if p["source"] == "hosted"}
assert hosted("build/flutter/pubspec.lock") == hosted("packaging/pubspec.lock"), "Dart lock drift"
'@ | uv run --locked python -

$taskBundle = Join-Path $taskBuild "windows"
$taskBundlePrefix = [System.IO.Path]::GetFullPath($taskBundle) + [System.IO.Path]::DirectorySeparatorChar
# Remove unused Tk and debug/test-only runtime files copied by upstream CMake.
foreach ($taskDirectory in @("Lib/test", "Lib/idlelib", "Lib/tkinter", "Lib/turtledemo")) {
    $taskTarget = [System.IO.Path]::GetFullPath((Join-Path $taskBundle $taskDirectory))
    if (-not $taskTarget.StartsWith($taskBundlePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe cleanup target" }
    if (Test-Path -LiteralPath $taskTarget) { Remove-Item -LiteralPath $taskTarget -Recurse -Force }
}
foreach ($taskFile in Get-ChildItem -LiteralPath $taskBundle -Recurse -File) {
    if ($taskFile.Name -match '(_d\.(dll|pyd)$|^_test.*\.pyd$|^vcruntime.*d\.dll$|^ucrtbased\.dll$|^tcl90\.dll$|^tcl9tk90\.dll$|^libtommath\.dll$|\.pdb$)') {
        Remove-Item -LiteralPath $taskFile.FullName
    }
    if ($taskFile.Name -match '(mpv|ffmpeg)') { throw "Unexpected media runtime in the Windows profile" }
}
foreach ($taskDirectory in Get-ChildItem -LiteralPath $taskBundle -Recurse -Directory -Filter __pycache__) {
    $taskTarget = [System.IO.Path]::GetFullPath($taskDirectory.FullName)
    if (-not $taskTarget.StartsWith($taskBundlePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe cache cleanup" }
    Remove-Item -LiteralPath $taskTarget -Recurse -Force
}

foreach ($taskExcluded in @("Lib/ensurepip", "site-packages/pip", "site-packages/flet_cli", "site-packages/flet_desktop", "site-packages/flet_web")) {
    if (Test-Path -LiteralPath (Join-Path $taskBundle $taskExcluded)) { throw "Unexpected build tooling in the runtime bundle" }
}
Copy-Item -LiteralPath VERSION, LICENSE, THIRD_PARTY_NOTICES.md -Destination $taskBundle
foreach ($taskNotice in (Get-Content -LiteralPath packaging/licenses/SOURCES.json -Raw | ConvertFrom-Json)) {
    $taskNoticeFile = Join-Path "packaging/licenses" $taskNotice.file
    if ((Get-FileHash -LiteralPath $taskNoticeFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskNotice.sha256) { throw "Vendored license changed without provenance update" }
}
$taskLicenses = Join-Path $taskBundle "licenses"
New-Item -ItemType Directory -Force -Path $taskLicenses | Out-Null
Get-ChildItem -LiteralPath packaging/licenses -File | Copy-Item -Destination $taskLicenses
Copy-Item -LiteralPath (Join-Path $env:FLUTTER_ROOT "LICENSE") -Destination (Join-Path $taskLicenses "FLUTTER-LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $env:FLUTTER_ROOT "bin/cache/dart-sdk/LICENSE") -Destination (Join-Path $taskLicenses "DART-LICENSE.txt")
@'
from pathlib import Path
import json,os,shutil,yaml
root=Path("build/windows/licenses/dart");root.mkdir(parents=True,exist_ok=True)
sources=[]
for name,pkg in yaml.safe_load(Path("packaging/pubspec.lock").read_text())["packages"].items():
    if pkg["source"] != "hosted": continue
    source=Path(os.environ["PUB_CACHE"])/"hosted/pub.dev"/f"{name}-{pkg['version']}"
    notices=[p for p in source.iterdir() if p.is_file() and p.name.lower().startswith(("license","licence","copying","notice","copyright"))]
    assert notices, f"Missing upstream license: {name}"
    target=root/name;target.mkdir(exist_ok=True)
    for notice in notices:shutil.copyfile(notice,target/notice.name)
    sources.append({"name":name,"version":pkg["version"],"source":f"https://pub.dev/api/archives/{name}-{pkg['version']}.tar.gz","sha256":pkg["description"]["sha256"]})
(root/"SOURCES.json").write_text(json.dumps(sources,indent=2)+"\n",encoding="utf-8")
assert Path("build/windows/data/flutter_assets/NOTICES.Z").is_file()
'@ | uv run --locked python -

& (Join-Path $PSScriptRoot "verify-windows.ps1") -Bundle $taskBundle -Version $Version -ToolchainFile (Join-Path $taskRoot "packaging/windows-toolchain.json")
uv run --locked python scripts/package_desktop.py --build-directory $taskBundle --output-directory $OutputDirectory --artifact-name "lcstats-relay-$Version-windows" --format zip
uv run --locked python scripts/verify_desktop_archive.py --archive "$OutputDirectory/lcstats-relay-$Version-windows.zip" --launcher lcstats-relay.exe
