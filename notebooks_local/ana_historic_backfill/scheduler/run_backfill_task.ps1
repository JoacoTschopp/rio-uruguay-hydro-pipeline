# Wrapper invocado por la tarea programada "ANA_Backfill_Download" (ver register_tasks.ps1).
# Corre una tanda acotada del backfill (--max-windows) usando el venv del proyecto.
# La mutua exclusion con otras corridas (Task Scheduler u otra desde el dashboard Gradio)
# la maneja run_with_lock() en run_backfill_local.py (lock.py), no este wrapper.

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$ScriptDir = "$RepoRoot\notebooks_local\ana_historic_backfill"
$Python = "$RepoRoot\.venv\Scripts\python.exe"

# Corrida continua: sin --max-windows, run_backfill_local.py recorre todas las ventanas en
# una sola pasada hasta agotar las estaciones o llegar al piso 2000. El estado se
# checkpointea por ventana, asi que si Task Scheduler corta la corrida (ExecutionTimeLimit
# de 6h) o se reinicia la PC, el proximo disparo (cada 1h) retoma del historic_backfill_state.json.
Set-Location $ScriptDir
& $Python "run_backfill_local.py"
