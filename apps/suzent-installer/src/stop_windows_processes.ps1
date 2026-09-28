$ErrorActionPreference = 'Stop'
try {
    $root = [IO.Path]::GetFullPath($env:SUZENT_UPDATE_ROOT)
    $allowedPaths = @(
        [IO.Path]::Combine($root, 'bin\suzent-ui.exe'),
        [IO.Path]::Combine($root, '.venv\Scripts\python.exe'),
        [IO.Path]::Combine($root, '.venv\Scripts\pythonw.exe')
    )
    $processes = @(Get-CimInstance Win32_Process)
    $protected = New-Object 'System.Collections.Generic.HashSet[uint32]'
    foreach ($start in @([uint32]$PID, [uint32]$env:SUZENT_UPDATER_PID)) {
        $current = $start
        while ($current -ne 0 -and $protected.Add($current)) {
            $entry = $processes | Where-Object { $_.ProcessId -eq $current } | Select-Object -First 1
            if ($null -eq $entry) { break }
            $current = [uint32]$entry.ParentProcessId
        }
    }
    foreach ($entry in $processes) {
        if ($protected.Contains([uint32]$entry.ProcessId)) { continue }
        if (-not $entry.ExecutablePath -or $allowedPaths -notcontains $entry.ExecutablePath) { continue }
        $process = $null
        try {
            try { $process = [Diagnostics.Process]::GetProcessById($entry.ProcessId) }
            catch [ArgumentException] { continue }
            # Hold the process handle and recheck identity before terminating it.
            $null = $process.Handle
            if ($process.HasExited) { continue }
            if ($allowedPaths -notcontains $process.MainModule.FileName) { continue }
            # CIM timestamps may lose sub-millisecond precision.
            if ([Math]::Abs(($process.StartTime.ToUniversalTime() - $entry.CreationDate.ToUniversalTime()).TotalMilliseconds) -gt 1) { continue }
            $process.Kill()
            [Console]::Out.WriteLine($entry.ProcessId)
        } catch {
            if ($null -ne $process -and $process.HasExited) { continue }
            throw "Cannot stop PID $($entry.ProcessId) ($($entry.ExecutablePath)): $($_.Exception.Message)"
        } finally {
            if ($null -ne $process) { $process.Dispose() }
        }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
