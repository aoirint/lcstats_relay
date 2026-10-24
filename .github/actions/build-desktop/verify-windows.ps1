#Requires -Version 7.4
param(
    [Parameter(Mandatory)][string]$Bundle,
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$ToolchainFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$taskProfile = Get-Content -LiteralPath $ToolchainFile -Raw | ConvertFrom-Json
$taskBundle = (Resolve-Path -LiteralPath $Bundle).Path
$taskProbe = Join-Path (Split-Path -Parent $taskBundle) "native-probe"
New-Item -ItemType Directory -Force -Path $taskProbe | Out-Null
$taskMarker = Join-Path $taskProbe "startup.json"
$taskFixture = [Guid]::NewGuid().ToString("N")
$taskPhases = @("write", "read-delete", "absent")

# Process-scoped test profile: never read production settings or relay data.
$taskSavedEnvironment = @{}
$taskEnvironment = @{
    APPDATA = (Join-Path $taskProbe "roaming")
    LOCALAPPDATA = (Join-Path $taskProbe "local")
    FLET_APP_CONSOLE = (Join-Path $taskProbe "console.log")
    PYTHONDONTWRITEBYTECODE = "1"
    LCSTATS_RELAY_STARTUP_CHECK = $taskMarker
    LCSTATS_RELAY_PROBE_VALUE = $taskFixture
    LCSTATS_RELAY_PROBE_PHASE = ""
}
foreach ($taskName in $taskEnvironment.Keys) {
    $taskSavedEnvironment[$taskName] = [Environment]::GetEnvironmentVariable($taskName, "Process")
    [Environment]::SetEnvironmentVariable($taskName, $taskEnvironment[$taskName], "Process")
}
try {
    foreach ($taskPhase in $taskPhases) {
        $env:LCSTATS_RELAY_PROBE_PHASE = $taskPhase
        if (Test-Path -LiteralPath $taskMarker) { Remove-Item -LiteralPath $taskMarker }
        $taskProcess = Start-Process -FilePath (Join-Path $taskBundle "lcstats-relay.exe") -WorkingDirectory $taskBundle -WindowStyle Hidden -PassThru
        try {
            $null = $taskProcess.Handle
            if (-not $taskProcess.WaitForExit(45000)) { throw "Native startup timed out" }
            if ($taskProcess.ExitCode -ne 0) { throw "Native process failed" }
            if (-not (Test-Path -LiteralPath $taskMarker)) { throw "Native render/credential marker missing" }
            $taskReport = Get-Content -LiteralPath $taskMarker -Raw | ConvertFrom-Json
            if ($taskReport.version -ne $Version -or $taskReport.python_version -ne $taskProfile.embedded_python -or $taskReport.flet_version -ne $taskProfile.flet -or $taskReport.certifi_version -ne $taskProfile.certifi) { throw "Unexpected packaged runtime identity" }
            if ($taskReport.width -le 0 -or $taskReport.height -le 0 -or $taskReport.architecture_bits -ne 64) { throw "Native page did not render" }
            if ((Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($taskMarker, ".png")) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReport.png_sha256) { throw "Native render checksum mismatch" }
            Write-Host "Native render and credential phase passed: $taskPhase"
        } finally {
            if (-not $taskProcess.HasExited) { $taskProcess.Kill($true); $taskProcess.WaitForExit() }
            $taskProcess.Dispose()
        }
    }
    $taskReport | Add-Member -NotePropertyName credential_restart_check -NotePropertyValue $true
    $taskReport | Add-Member -NotePropertyName credential_phases -NotePropertyValue $taskPhases
    $taskReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $taskBundle "runtime-report.json") -Encoding utf8NoBOM
} finally {
    foreach ($taskName in $taskSavedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($taskName, $taskSavedEnvironment[$taskName], "Process")
    }
}
