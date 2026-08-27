# Registra la tarea programada de Windows para la inferencia diaria de Rio_Search (Fase 6,
# docs/rio_search_plan.md §3.8): corre `rio-search predict run --target caudal` todos los dias a
# las 06:30 Montevideo, despues de que la cadena diaria de Databricks
# (Silver_Gold_Daily_Incremental, job del roadmap del pipeline, fuera de este repo) ya actualizo
# Gold (corre a las 04:30 Montevideo).
#
# Mismo patron que notebooks_local/ana_historic_backfill/scheduler/register_tasks.ps1 y
# notebooks_local/ecmwf/scheduler/register_tasks.ps1 -- **adaptado, no importado**, a
# rio_search/ (encargo explicito de esta fase): la tarea corre `run_daily_forecast_task.ps1`,
# que usa el `.venv` propio de `rio_search/backend` (no el del resto del repo) y llama al mismo
# comando (`rio-search predict run`) que un usuario correria a mano.
#
# A diferencia de los backfills de ANA/TIGGE (corrida continua, redisparo horario), esta es una
# corrida diaria puntual: `New-ScheduledTaskTrigger -Daily -At "06:30"` (no `-Once` +
# `-RepetitionInterval`) -- `IssueDailyForecast` es rapida (segundos, no hay checkpoint que
# retomar) y correrla mas de una vez por dia no aporta nada distinto salvo que Gold haya
# cambiado de version en el medio, caso que igual cubre el proximo dia.
#
# Aviso operativo (Decision 044, docs/decisions.md): nunca correr dos procesos de Rio_Search
# contra Databricks/MLflow con el mismo perfil CLI al mismo tiempo (compiten por el cache de
# tokens OAuth en Windows). `rio-search predict run` toma el mismo `ProcessLock` de archivo que
# `SubprocessJobRunner` (la cola de la API)/`rio-search search run` a mano
# (`interfaces/cli/main.py::predict_run`), asi que una busqueda corriendo justo a las 06:30 no
# genera una colision real -- esta tarea espera a que termine.
#
# Correr una sola vez, a mano (no lo ejecuta el agente):
#   powershell -ExecutionPolicy Bypass -File register_tasks.ps1
# Para desregistrar:
#   Unregister-ScheduledTask -TaskName "RioSearch_Daily_Forecast" -Confirm:$false

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

# ExecutionTimeLimit de 1h: backstop generoso (una corrida normal tarda segundos a minutos,
# `dataset_export_job_s` puede sumar unos minutos mas si el snapshot esta atras de Gold, §3.6).
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\run_daily_forecast_task.ps1`""
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:30"

Register-ScheduledTask -TaskName "RioSearch_Daily_Forecast" `
    -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Rio_Search: IssueDailyForecast (rio-search predict run --target caudal), todos los dias a las 06:30 Montevideo, despues de Silver_Gold_Daily_Incremental (docs/rio_search_plan.md §3.8)." `
    -Force

Write-Host "Tarea registrada: RioSearch_Daily_Forecast (diaria, 06:30 Montevideo)."
Write-Host "Revisar/administrar desde el Programador de tareas de Windows (taskschd.msc)."
