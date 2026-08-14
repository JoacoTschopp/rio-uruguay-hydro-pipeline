# Wrapper invocado por la tarea programada "ANA_Backfill_Sync" (2x/dia, ver register_tasks.ps1).
# Sube los JSON del backfill ya descargados al Volume de Databricks. No dispara ningun job:
# el proximo run del job diario existente (All_Estacoes_ANA_Daily) los mergea solo.
#
# Requiere sesion valida de `databricks auth login --profile $DatabricksProfile` ya hecha
# a mano (el token OAuth se refresca solo mientras siga siendo valido; si expiro, esta
# tarea va a fallar y hay que loguear de nuevo manualmente, igual que con cualquier otro
# uso de la CLI de Databricks en este proyecto).

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$ScriptDir = "$RepoRoot\notebooks_local\ana_historic_backfill"
$Python = "$RepoRoot\.venv\Scripts\python.exe"
$DatabricksProfile = "joaquintschopp@gmail.com"

Set-Location $ScriptDir
& $Python "sync_to_databricks.py" "--profile" $DatabricksProfile
