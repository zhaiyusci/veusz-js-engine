# Requires PowerShell 7 (ProcessStartInfo.ArgumentList). Never kills a user's browser.
param(
    [string]$Browser = 'C:\Program Files\Mozilla Firefox\firefox.exe',
    [string]$Veusz = 'C:\Program Files\Veusz\veusz.exe',
    [ValidateRange(10, 600)][int]$ReadyTimeoutSeconds = 180
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$browserStem = [IO.Path]::GetFileNameWithoutExtension($Browser).ToLowerInvariant()
if ($browserStem -notin @('firefox', 'msedge')) { throw 'Browser must name firefox.exe or msedge.exe.' }
$label = if ($browserStem -eq 'firefox') { 'Firefox' } else { 'msedge' }
$output = Join-Path $root "build-test-browser-owner-death\$label"
New-Item -ItemType Directory -Path $output -Force | Out-Null
# Hold a per-output lock, so concurrent runs cannot consume each other's ready file.
$lock = [IO.File]::Open((Join-Path $output 'runner.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$veuszProcess = $null
$owned = @{}
$profile = $null
$ready = $null
$result = [ordered]@{
    status = 'running'; passed = $false; browser = $Browser; veusz = $Veusz
    before_pid_list = @(); before = @(); exit_statuses = @()
    profile_retained = $null; profile_cleanup = 'not attempted'
    profile_retention_note = 'Crash-time profile retention is expected and does not fail this test.'
    cleanup_performed = $false; cleanup_counts_toward_pass = $false; cleanup_errors = @()
}
$names = @('VEUSZ_JS_ENGINE_BACKEND', 'VEUSZ_JS_ENGINE_BROWSER', 'QT_QPA_PLATFORM')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

function Get-Snapshot { @(Get-CimInstance Win32_Process -ErrorAction Stop) }
function Get-Tree($snapshot, [int]$rootId) {
    $seen = @{}
    $rootRow = $snapshot | Where-Object { [int]$_.ProcessId -eq $rootId }
    if (!$rootRow) { return @() }
    $seen[$rootId] = $rootRow.CreationDate
    do {
        $changed = $false
        foreach ($row in $snapshot) {
            # Reject historical children of a recycled parent PID.
            if ($seen.ContainsKey([int]$row.ParentProcessId) -and !$seen.ContainsKey([int]$row.ProcessId) -and
                $row.CreationDate -ge $seen[[int]$row.ParentProcessId]) {
                $seen[[int]$row.ProcessId] = $row.CreationDate; $changed = $true
            }
        }
    } while ($changed)
    @($snapshot | Where-Object { $seen.ContainsKey([int]$_.ProcessId) })
}
function Capture-Row($row) {
    $idValue = [int]$row.ProcessId
    if ($owned.ContainsKey($idValue)) { return }
    $process = $null
    try {
        $process = [Diagnostics.Process]::GetProcessById($idValue)
        # Force OpenProcess now: all later checks/kills use this held identity,
        # never reopen a PID after host death (PID reuse must not target strangers).
        $null = $process.Handle
        if ($process.HasExited) { $process.Dispose(); return }
        # CIM snapshot can race with PID reuse before OpenProcess.
        if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $row.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 100) {
            throw "PID $idValue changed identity during capture"
        }
        $owned[$idValue] = @{ process = $process; row = $row }
    } catch {
        if ($null -ne $process) { $process.Dispose() }
        throw
    }
}
function Get-ExitStatuses {
    @($owned.Values | ForEach-Object {
        $p = $_.process
        $exited = $p.HasExited
        [ordered]@{ pid = $p.Id; exited = $exited; exit_code = $(if ($exited) { $p.ExitCode } else { $null }) }
    } | Sort-Object { $_.pid })
}
function Get-ProfileRows {
    if (!$profile) { return @() }
    @(Get-Snapshot | Where-Object {
        $_.CommandLine -and $_.CommandLine.IndexOf($profile, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.Name -ieq ([IO.Path]::GetFileName($Browser))
    })
}
try {
    foreach ($file in @('ready.json', 'failed.json', 'results.json', 'ready.json.tmp', 'failed.json.tmp')) {
        Remove-Item -LiteralPath (Join-Path $output $file) -Force -ErrorAction SilentlyContinue
    }
    if (!(Test-Path -LiteralPath $Browser -PathType Leaf)) { throw "Browser not found: $Browser" }
    if (!(Test-Path -LiteralPath $Veusz -PathType Leaf)) { throw "Veusz not found: $Veusz" }
    $env:VEUSZ_JS_ENGINE_BACKEND = 'browser'
    $env:VEUSZ_JS_ENGINE_BROWSER = $Browser
    $env:QT_QPA_PLATFORM = 'windows'
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Veusz
    $start.UseShellExecute = $false
    # No redirects: inherit stdio without pipes or Start-Process ExitCode issues.
    $start.ArgumentList.Add('--veusz-plugin')
    $start.ArgumentList.Add((Join-Path $PSScriptRoot 'browser_owner_death_plugin.py'))
    $veuszProcess = [System.Diagnostics.Process]::Start($start)
    $null = $veuszProcess.Handle
    $result.veusz_pid = $veuszProcess.Id
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while (!(Test-Path -LiteralPath (Join-Path $output 'ready.json'))) {
        if (Test-Path -LiteralPath (Join-Path $output 'failed.json')) {
            $result.plugin_failure = Get-Content -LiteralPath (Join-Path $output 'failed.json') -Raw | ConvertFrom-Json
            throw 'Frozen Veusz plugin failed; see failed.json.'
        }
        if ($veuszProcess.HasExited) { throw "Veusz exited before ready: $($veuszProcess.ExitCode)" }
        if ($timer.Elapsed.TotalSeconds -ge $ReadyTimeoutSeconds) { throw 'Timed out waiting for ready.json.' }
        Start-Sleep -Milliseconds 100
    }
    $ready = Get-Content -LiteralPath (Join-Path $output 'ready.json') -Raw | ConvertFrom-Json
    $result.ready = $ready
    if ($ready.veusz_pid -ne $veuszProcess.Id -or !$ready.frozen -or $ready.status -ne 'ready') { throw 'Ready file host identity mismatch.' }
    if ($veuszProcess.HasExited) { throw 'Host died before the deliberate kill.' }
    if ($ready.session.process_lifetime.mechanism -ne 'windows-job-object' -or
        $ready.session.process_lifetime.atomic_job_assignment -ne $true) { throw 'Atomic Windows Job Object not active.' }
    if ($ready.js_result.parsed.name -ne 'mathjax') { throw 'Missing actual MathJax JS result.' }
    $profile = [string]$ready.session.temporary_directory
    if (!$profile -or !(Test-Path -LiteralPath $profile -PathType Container)) { throw 'Dedicated profile directory missing.' }
    $result.profile = $profile
    $snapshot = Get-Snapshot
    $browserRoot = [int]$ready.session.pid
    $hostTree = @(Get-Tree $snapshot $veuszProcess.Id)
    if (!($hostTree | Where-Object { [int]$_.ProcessId -eq $browserRoot })) { throw 'Browser root is not owned by this Veusz host.' }
    $browserRows = @(Get-Tree $snapshot $browserRoot)
    $rootRow = $browserRows | Where-Object { [int]$_.ProcessId -eq $browserRoot }
    if (!$rootRow -or $rootRow.Name -ine ([IO.Path]::GetFileName($Browser)) -or
        !$rootRow.CommandLine -or $rootRow.CommandLine.IndexOf($profile, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw 'Browser root does not identify the dedicated profile.'
    }
    foreach ($row in $browserRows) { Capture-Row $row }
    if (!$owned.ContainsKey($browserRoot) -or $owned.Count -lt 2) { throw 'Need a live browser root and at least one live child.' }
    $result.before_pid_list = @($owned.Keys | Sort-Object)
    $result.before = @($owned.Values | ForEach-Object {
        [ordered]@{ pid = $_.process.Id; parent_pid = $_.row.ParentProcessId; name = $_.row.Name
            creation_time = $_.row.CreationDate; exited = $_.process.HasExited; handle_captured = $true }
    })
    if (@($result.before | Where-Object { $_.exited }).Count) { throw 'Browser exited before host kill.' }
    # This is the ONLY kill in the measurement phase: no /T, no browser kill.
    $result.kill_method = 'veuszProcess.Kill() (host only)'
    $veuszProcess.Kill()
    $timer.Restart()
    do {
        $statuses = @(Get-ExitStatuses)
        if (@($statuses | Where-Object { !$_.exited }).Count -eq 0) { break }
        Start-Sleep -Milliseconds 50
    } while ($timer.Elapsed.TotalSeconds -lt 15)
    $result.elapsed_after_kill_ms = $timer.ElapsedMilliseconds
    $result.exit_statuses = @(Get-ExitStatuses)
    $result.profile_retained = Test-Path -LiteralPath $profile
    $leftovers = @(Get-ProfileRows)
    $result.profile_remaining_pids = @($leftovers | ForEach-Object { [int]$_.ProcessId })
    if (@($result.exit_statuses | Where-Object { !$_.exited }).Count -or $leftovers.Count) { throw 'Owned browser processes survived host death.' }
    if (!$veuszProcess.WaitForExit(1000)) { throw 'Host did not exit after Kill().' }
    $result.veusz_exit_code = $veuszProcess.ExitCode
    $result.status = 'passed'; $result.passed = $true
} catch {
    $result.status = 'failed'; $result.passed = $false; $result.error = $_.ToString()
} finally {
    # Record verdict BEFORE cleanup. Cleanup can never turn a failed test into pass.
    if (!$result.passed) {
        $result.cleanup_performed = $true
        try {
            # On startup failure, capture only descendants of our still-live host.
            if ($null -ne $veuszProcess -and !$veuszProcess.HasExited) {
                foreach ($row in @(Get-Tree (Get-Snapshot) $veuszProcess.Id)) {
                    if ([int]$row.ProcessId -ne $veuszProcess.Id) {
                        try { Capture-Row $row } catch { $result.cleanup_errors += $_.ToString() }
                    }
                }
            }
            # Profile-tagged late browser processes are also exclusively ours.
            foreach ($row in @(Get-ProfileRows)) {
                foreach ($child in @(Get-Tree (Get-Snapshot) ([int]$row.ProcessId))) {
                    try { Capture-Row $child } catch { $result.cleanup_errors += $_.ToString() }
                }
            }
        } catch { $result.cleanup_errors += $_.ToString() }
        if ($null -ne $veuszProcess) {
            try { if (!$veuszProcess.HasExited) { $veuszProcess.Kill(); $null = $veuszProcess.WaitForExit(5000) } }
            catch { $result.cleanup_errors += $_.ToString() }
        }
        foreach ($entry in $owned.Values) {
            try { if (!$entry.process.HasExited) { $entry.process.Kill(); $null = $entry.process.WaitForExit(5000) } }
            catch { $result.cleanup_errors += $_.ToString() }
        }
        try { $result.after_cleanup = @(Get-ExitStatuses) } catch { $result.cleanup_errors += $_.ToString() }
    } elseif ($profile -and $result.profile_retained) {
        # Only remove our unique backend temp directory after all browser handles
        # exited and a profile-command-line scan found no remaining browser.
        try {
            $full = [IO.Path]::GetFullPath($profile)
            $temp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
            if (!$full.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase) -or $full.TrimEnd('\') -eq $temp.TrimEnd('\')) {
                throw 'Refusing profile removal outside a strict child of the temporary directory.'
            }
            if ((Get-Item -LiteralPath $full).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing reparse-point profile removal.' }
            Remove-Item -LiteralPath $full -Recurse -Force
            $result.profile_cleanup = 'removed after verified browser exit'
        } catch { $result.profile_cleanup = 'retained: ' + $_.ToString() }
    }
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    try {
        $result | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath (Join-Path $output 'results.json') -Encoding utf8
    } finally {
        foreach ($entry in $owned.Values) { $entry.process.Dispose() }
        if ($null -ne $veuszProcess) { $veuszProcess.Dispose() }
        $lock.Dispose()
    }
}
if (!$result.passed) { throw "FAIL: $output\results.json — $($result.error)" }
Write-Output "PASS: $output\results.json (cleanup was not used to obtain this verdict)"
