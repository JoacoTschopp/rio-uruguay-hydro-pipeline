# Wrapper invocado por la tarea programada "ECMWF_FC_Daily_Download" (ver register_tasks.ps1).
# Corre landing_fc_opendata.py (una corrida = la mas reciente disponible de `fc`, resumible via
# already_landed -- si ya se bajo esa corrida, sale sin hacer nada) y despues sync_to_databricks.py
# (sube cf/pf/fc pendientes, mismo script que ya usa TIGGE).
#
# Por que urgente (Fase 8 del roadmap, Decision 013): ECMWF Open Data retiene solo ~12 corridas
# (2-3 dias) de `fc` -- cada dia sin bajarlo es archivo perdido de forma irrecuperable. Se
# redispara cada 4h (hay 4 corridas/dia, a las 00/06/12/18 UTC) para no depender de que una sola
# ejecucion diaria coincida justo con la publicacion.
#
# Mismo gotcha de PowerShell que TIGGE (ver run_backfill_task.ps1): la redireccion via cmd.exe
# evita que el stderr informativo de las librerias (tqdm, ecmwf.opendata) aborte el script con
# $ErrorActionPreference = "Stop".

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$ScriptDir = "$RepoRoot\notebooks_local\ecmwf"
$Python = "$RepoRoot\.venv\Scripts\python.exe"
$DatabricksProfile = "joaquintschopp@gmail.com"
$LogFile = "$ScriptDir\fc_daily_task.log"

Set-Location $ScriptDir
"=== Corrida iniciada $(Get-Date) ===" | Out-File -FilePath $LogFile -Append -Encoding utf8
cmd /c "`"$Python`" landing_fc_opendata.py >> `"$LogFile`" 2>&1"
cmd /c "`"$Python`" sync_to_databricks.py --profile `"$DatabricksProfile`" >> `"$LogFile`" 2>&1"
