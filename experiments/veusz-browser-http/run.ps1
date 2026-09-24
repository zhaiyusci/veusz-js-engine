param(
    [string]$Veusz = 'C:\Program Files\Veusz\veusz.exe',
    [string]$Browser = 'C:\Program Files\Mozilla Firefox\firefox.exe'
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $Veusz)) { throw "Veusz not found: $Veusz" }
if (!(Test-Path -LiteralPath $Browser)) { throw "Browser not found: $Browser" }
$plugin = Join-Path $PSScriptRoot 'plugin.py'
$output = Join-Path $PSScriptRoot 'output'
New-Item -ItemType Directory -Path $output -Force | Out-Null
# Invalidate previous success before launching, including startup failures.
Set-Content -LiteralPath (Join-Path $output 'results.json') -Value '{"status":"launching"}' -Encoding utf8
$oldQt = $env:QT_QPA_PLATFORM
$oldBrowser = $env:VEUSZ_HTTP_TEST_BROWSER
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:VEUSZ_HTTP_TEST_BROWSER = $Browser
    $process = Start-Process -FilePath $Veusz -ArgumentList @('--veusz-plugin', ('"' + $plugin + '"')) -PassThru -RedirectStandardOutput (Join-Path $output 'veusz.stdout.log') -RedirectStandardError (Join-Path $output 'veusz.stderr.log')
    Write-Output "Started disposable Veusz PID $($process.Id); HTTP and RPC execute inside this process."
    if (!$process.WaitForExit(180000)) {
        & taskkill /PID $process.Id /T /F
        throw 'Veusz experiment timed out; requested termination of only its process tree.'
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Veusz exited with code $($process.ExitCode); inspect output logs." }
    $report = [System.IO.File]::ReadAllText((Join-Path $output 'results.json')) | ConvertFrom-Json
    if ($report.status -ne 'passed') { throw "Experiment status: $($report.status); inspect $output\results.json" }
    Write-Output "PASS: Veusz-hosted HTTP, browser SVG and Qt rendering. Report: $output\results.json"
} finally {
    $env:QT_QPA_PLATFORM = $oldQt
    $env:VEUSZ_HTTP_TEST_BROWSER = $oldBrowser
}
