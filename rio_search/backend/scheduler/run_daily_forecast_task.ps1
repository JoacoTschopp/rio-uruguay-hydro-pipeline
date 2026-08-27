# Wrapper invocado por la tarea programada "RioSearch_Daily_Forecast" (todos los dias a las
# 06:30 Montevideo, ver register_tasks.ps1). Corre `IssueDailyForecast` (Fase 6,
# docs/rio_search_plan.md §3.8) para el target `caudal`.
#
# Se programa a las 06:30 a proposito: la cadena diaria de Databricks (Silver_Gold_Daily_Incremental,
# job del roadmap del pipeline, fuera de este repo) corre a las 04:30 Montevideo y termina en
# Export_Gold_Snapshot -- a las 06:30 el snapshot del Volume ya deberia estar al dia, asi el
# paso 1 de IssueDailyForecast (RefreshDataset, protocolo de frescura §3.6) normalmente no
# dispara un `Export_Gold_Snapshot` ad hoc (lo dispara solo, sin intervencion, si igual esta
# atras -- eso es lo que verifica el protocolo, no algo que este script deba manejar).
#
# Requiere:
#   - `databricks auth login --profile joaquintschopp@gmail.com` ya hecho a mano (el token OAuth
#     se refresca solo mientras siga siendo valido; si expiro, esta tarea va a fallar y hay que
#     loguear de nuevo manualmente, igual que con cualquier otro uso de la CLI de Databricks en
#     este repo).
#   - Un campeon ya promovido para `caudal` (`rio-search champions set --run <run_id> --target
#     caudal`, PromoteChampion) -- si no hay campeon, este comando falla explicito
#     ("No hay campeon promovido...").
#
# `predict run` toma el mismo ProcessLock de archivo que `rio-search search run`/la API
# (Decision 044, docs/decisions.md): si una busqueda esta corriendo a las 06:30, esta tarea
# espera en vez de competir por el cache de tokens OAuth.
#
# --publish (§3.8 paso 5, sube el parquet al Volume de Databricks) queda deliberadamente
# comentado: se activa a mano una vez que el usuario reviso el campeon provisorio (§8 del plan,
# version 9 de weather.ml.rio_search_bilstm) y decide que los pronosticos deben llegar a
# Databricks automaticamente todos los dias.

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..\..").Path
$BackendDir = "$RepoRoot\rio_search\backend"
$Python = "$BackendDir\.venv\Scripts\python.exe"

Set-Location $BackendDir
& $Python -m rio_search.interfaces.cli.main predict run --target caudal
# & $Python -m rio_search.interfaces.cli.main predict run --target caudal --publish
