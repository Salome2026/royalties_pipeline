$Base = "C:\royalties_pipeline"
$Python = Join-Path $Base ".venv\Scripts\python.exe"
$Script = Join-Path $Base "scripts\run_catalog_metadata_worker.py"

$Args = @(
    $Script,
    "--batch-size", "20",
    "--sleep-seconds", "900",
    "--rate-limit-sleep-seconds", "3600",
    "--max-retry-after-seconds", "1800",
    "--max-batches", "8",
    "--min-amounts", "100,50,10",
    "--label-backfill-limit", "20"
)

Start-Process `
    -FilePath $Python `
    -ArgumentList $Args `
    -WorkingDirectory $Base `
    -WindowStyle Hidden

Write-Host "Catalog metadata worker started."
Write-Host "Log: $Base\staging\catalog_metadata_worker\catalog_metadata_worker.log"
