$ErrorActionPreference = 'Stop'
try {
    Add-Type -Name PathIdentity -Namespace Suzent -MemberDefinition @'
[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern uint GetLongPathName(string path, System.Text.StringBuilder result, uint size);
'@
    function Get-CanonicalExecutablePath([string]$path) {
        $full = [IO.Path]::GetFullPath($path)
        $buffer = New-Object Text.StringBuilder 32768
        $length = [Suzent.PathIdentity]::GetLongPathName($full, $buffer, $buffer.Capacity)
        if ($length -gt 0 -and $length -lt $buffer.Capacity) { return $buffer.ToString() }
        return $full
    }
    $root = [IO.Path]::GetFullPath($env:SUZENT_UPDATE_ROOT)
    $allowedPaths = @(
        [IO.Path]::Combine($root, 'bin\suzent-ui.exe'),
        [IO.Path]::Combine($root, 'src-tauri\target\release\suzent.exe'),
        [IO.Path]::Combine($root, 'src-tauri\target\debug\suzent.exe'),
        [IO.Path]::Combine($root, '.venv\Scripts\python.exe'),
        [IO.Path]::Combine($root, '.venv\Scripts\pythonw.exe')
    ) | ForEach-Object { Get-CanonicalExecutablePath $_ }
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
        if (-not $entry.ExecutablePath) { continue }
        # CIM may report an 8.3 path while the installation uses its long form.
        if ($allowedPaths -notcontains (Get-CanonicalExecutablePath $entry.ExecutablePath)) { continue }
        $process = $null
        try {
            try { $process = [Diagnostics.Process]::GetProcessById($entry.ProcessId) }
            catch [ArgumentException] { continue }
            # Hold the process handle and recheck identity before terminating it.
            $null = $process.Handle
            if ($process.HasExited) { continue }
            if ($allowedPaths -notcontains (Get-CanonicalExecutablePath $process.MainModule.FileName)) { continue }
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
