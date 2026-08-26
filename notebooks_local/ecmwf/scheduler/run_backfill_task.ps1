# Wrapper invocado por la tarea programada "TIGGE_Backfill_Download" (ver register_tasks.ps1).
# Corre run_tigge_backfill.py, que ya hace cf completo -> pf completo -> sync periodico
# internamente. La mutua exclusion la maneja tigge_lock.py (lock dedicado, no el compartido
# de ana_historic_backfill -- ver el docstring de tigge_lock.py).
#
# Por que Task Scheduler y no un backfill lanzado desde la sesion de Claude Code: los
# requests viejos de TIGGE/ECDS (anios 2006-2018) tardan mas en resolverse en MARS de lo que
# dura un proceso en background dentro de esa sesion (limite no documentado, confirmado
# empiricamente: ~20-40 min) -- un request de ese tipo nunca llegaba a completarse porque lo
# mataban antes de que MARS respondiera. Task Scheduler no tiene ese limite.

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$ScriptDir = "$RepoRoot\notebooks_local\ecmwf"
$Python = "$RepoRoot\.venv\Scripts\python.exe"
$DatabricksProfile = "joaquintschopp@gmail.com"
$LogFile = "$ScriptDir\tigge_backfill_task.log"

# Corrida continua: run_tigge_backfill.py recorre cf completo y despues pf completo en un
# solo proceso, sincronizando cada --sync-every-calls llamadas exitosas. Si Task Scheduler
# corta la corrida (ExecutionTimeLimit de 6h) o se reinicia la PC, el proximo disparo
# (cada 1h) retoma solo -- cada lote ya aterrizado queda marcado por la presencia de su JSON
# en disco (batch_fully_landed), no hace falta ningun estado adicional.
#
# Task Scheduler no captura stdout/stderr por si solo (sin esto quedaba sin ningun log
# accesible) -- se acumula en un solo archivo con marca de tiempo por corrida, para poder
# diagnosticar sin depender de que la sesion de Claude Code siga viva.
#
# IMPORTANTE: la redireccion tiene que hacerse via cmd.exe (`cmd /c ... >> log 2>&1`), NO con
# el operador nativo de PowerShell (`2>&1` o `*>>`) sobre un ejecutable externo. cdsapi loguea
# mensajes informativos ("Request ID is...", "status has been updated to...") por stderr en
# cada corrida exitosa -- en PowerShell 5.1, redirigir el stderr de un comando nativo lo
# envuelve en un NativeCommandError, y con $ErrorActionPreference = "Stop" (arriba) eso aborta
# el script AL INSTANTE, antes de que Python llegue a imprimir nada y sin pasar por el
# `finally: lock.release()` -- exactamente lo que causaba que la tarea programada fallara en
# silencio (exit code 1, log vacio, lock huerfano) en cada corrida, incluso con ECDS respondiendo
# bien. cmd.exe hace la redireccion a nivel de OS, sin reinterpretar stderr como error de
# PowerShell.
Set-Location $ScriptDir
"=== Corrida iniciada $(Get-Date) ===" | Out-File -FilePath $LogFile -Append -Encoding utf8
$PythonArgs = "run_tigge_backfill.py --max-batches-per-call 25 --sync-every-calls 3 --profile `"$DatabricksProfile`""
cmd /c "`"$Python`" $PythonArgs >> `"$LogFile`" 2>&1"
