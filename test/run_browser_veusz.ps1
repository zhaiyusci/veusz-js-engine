param(
    [string]$Veusz = 'C:\Program Files\Veusz\veusz.exe',
    [string]$Browser = 'C:\Program Files\Mozilla Firefox\firefox.exe',
    [ValidateSet('browser', 'quickjs')][string]$Backend = 'browser'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$plugin = Join-Path $PSScriptRoot 'browser_veusz_plugin.py'
$output = Join-Path $root ('build-test-browser-veusz\' + $Backend + '-' + [System.IO.Path]::GetFileNameWithoutExtension($Browser))
New-Item -ItemType Directory -Path $output -Force | Out-Null
Set-Content -LiteralPath (Join-Path $output 'results.json') -Value '{"status":"launching"}' -Encoding utf8
$names = @('QT_QPA_PLATFORM','VEUSZ_JS_ENGINE_BACKEND','VEUSZ_JS_ENGINE_BROWSER','VEUSZ_JS_ENGINE_QUICKJS')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    # Offscreen Qt on Windows can have stub fonts: use the real font backend.
    $env:QT_QPA_PLATFORM = 'windows'
    $env:VEUSZ_JS_ENGINE_BACKEND = $Backend
    $env:VEUSZ_JS_ENGINE_BROWSER = $Browser
    if ($Backend -eq 'browser') {
        $env:VEUSZ_JS_ENGINE_QUICKJS = Join-Path $root 'deliberately-missing-qjs.dll'
    } else {
        $env:VEUSZ_JS_ENGINE_QUICKJS = Join-Path $root 'qjs.dll'
    }
    # Launch directly rather than Start-Process: its Windows wrapper can yield
    # ExitCode=$null even after WaitForExit, particularly for fast GUI programs.
    # Inherit stdio (no anonymous/named pipe capture); the plugin writes JSON.
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Veusz
    $start.UseShellExecute = $false
    $start.ArgumentList.Add('--veusz-plugin')
    $start.ArgumentList.Add($plugin)
    $process = [System.Diagnostics.Process]::Start($start)
    Write-Output "Disposable Veusz PID $($process.Id), backend $Backend"
    if (!$process.WaitForExit(180000)) {
        & taskkill /PID $process.Id /T /F
        throw 'Integration test timed out; terminated only its process tree.'
    }
    $exitCode = $process.ExitCode
    if ($null -eq $exitCode -or $exitCode -ne 0) { throw "Veusz exit code unavailable or nonzero: $exitCode" }
    $result = [System.IO.File]::ReadAllText((Join-Path $output 'results.json')) | ConvertFrom-Json
    if ($result.status -ne 'passed') { throw "Integration status $($result.status). Inspect $output\results.json" }
    Write-Output "PASS: $output\results.json"
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
