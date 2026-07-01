$Processes = Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like "*run_catalog_metadata_worker.py*" }

if (-not $Processes) {
    Write-Host "No catalog metadata worker process found."
    exit 0
}

foreach ($Process in $Processes) {
    Stop-Process -Id $Process.ProcessId -Force
    Write-Host "Stopped catalog metadata worker PID $($Process.ProcessId)."
}

$LockPath = "C:\royalties_pipeline\staging\catalog_metadata_worker\catalog_metadata_worker.lock"
if (Test-Path $LockPath) {
    Remove-Item -LiteralPath $LockPath -Force
    Write-Host "Removed stale lock: $LockPath"
}
