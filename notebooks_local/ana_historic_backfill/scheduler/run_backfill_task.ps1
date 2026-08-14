# Wrapper invocado por la tarea programada "ANA_Backfill_Download" (ver register_tasks.ps1).
# Corre una tanda acotada del backfill (--max-windows) usando el venv del proyecto.
# La mutua exclusion con otras corridas (Task Scheduler u otra desde el dashboard Gradio)
# la maneja run_with_lock() en run_backfill_local.py (lock.py), no este wrapper.

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$ScriptDir = "$RepoRoot\notebooks_local\ana_historic_backfill"
$Python = "$RepoRoot\.venv\Scripts\python.exe"
$MaxWindowsPerRun = 10  # ~10 ventanas por disparo, ver register_tasks.ps1 para el intervalo

Set-Location $ScriptDir
& $Python "run_backfill_local.py" "--max-windows" $MaxWindowsPerRun
