# Catálogo de fuentes de datos

## 1. Objetivo del documento

Este documento describe las fuentes de datos utilizadas (o candidatas) para construir el dataset de tesis sobre niveles del Río Uruguay.

Para cada fuente se registra: origen, endpoint o ruta, frecuencia, cobertura observada, ruta Landing, tabla Bronze destino, estado y uso previsto.

Las decisiones metodológicas asociadas se documentan por separado en `decisions.md`. La definición funcional del dataset está en `dataset_definition.md`.

## 2. Resumen rápido

| Fuente                          | Tipo          | Estado en pipeline | Tabla Bronze                    | Frecuencia origen | Uso previsto       |
| ------------------------------- | ------------- | ------------------ | ------------------------------- | ----------------- | ------------------ |
| ANA — Inventario estaciones     | Hidrológica   | Bronze + diaria    | `weather.bronze.ana_rio_uruguai`| Subdiaria          | Referencia / lluvia |
| ANA — Niveles telemétricos      | Hidrológica   | Bronze + diaria    | `weather.bronze.nivel_ana`      | Subdiaria          | Target / features  |
| METAR — Aeropuertos Brasil      | Meteorológica | Bronze + diaria    | `weather.bronze.metar`          | Horaria            | Features temperatura |
| ANA — Lluvias estaciones pluvio | Hidrológica   | Compartida con ANA | `weather.bronze.ana_rio_uruguai`| Subdiaria          | Features lluvia     |
| Salto Grande — Lluvia estaciones| Hidrológica   | Pipeline nuevo     | `weather.bronze.sg_rainfall`    | Diaria             | Features lluvia     |
| ECMWF — Pronóstico precipitación (cf + pf) | Pronóstico | Bronze + Silver + diaria | `weather.bronze.ecmwf_forecast_cf` / `_pf` | Diaria (grilla 0,25°) | Features futuras |
| ANA — Curvas de aforo (rating curve) | Hidrológica | Bronze + Silver + Gold, grupo A completo | `weather.bronze.ana_rating_curve_segments` / `ana_discharge_measurements` | Estática (revisión trimestral) | Conversión nivel→caudal |
| Evaporación                     | Meteorológica | No ingestada       | —                               | Diaria             | Features            |
| CPTEC — MERGE (lluvia observada en grilla) | Observación en grilla | Bronze + Silver + Gold + diaria (Fase 9) | `weather.bronze.merge_precip_grid` | Diaria (0,1°, ventana 12Z-12Z) | Features lluvia (media areal `alta_frontera`) |
| CPTEC — SAMeT (temperatura observada en grilla) | Observación en grilla | Bronze + Silver + Gold + diaria (Fase 9) | `weather.bronze.samet_temp_grid` | Diaria (0,05°, día UTC) | Features temperatura (media areal `alta_frontera`) |
| CPTEC/INPE — Modelos NWP (WRF 7 km, Eta, BAM, MONAN) | Pronóstico | Evaluada, no ingestada (Decisión 032) | — | Diaria | Candidata a `forecast_source` sólo 2020+ |

---

## 3. ANA — Inventario y serie telemétrica adoptada

### 3.1. Origen

* Proveedor: Agência Nacional de Águas e Saneamento Básico (ANA), Brasil.
* Servicio: HidroWebService.
* Base URL: `https://www.ana.gov.br/hidrowebservice`.
* Endpoint autenticación: `/EstacoesTelemetricas/OAUth/v1`.
* Endpoint datos: `/EstacoesTelemetricas/HidroinfoanaSerieTelemetricaAdotada/v2`.
* Autenticación: usuario + password (Bearer token), parametrizado por widgets `USER_API_ANA` / `PASS_API_ANA` en Databricks.

### 3.2. Cobertura espacial

* Estaciones del listado local `/Volumes/weather/raw/ana_volume/estaciones_rio_uruguai_pluvio_fluvio.json` (estaciones pluvio + fluvio del Río Uruguay).
* Hasta 10 estaciones por request; el daily las consume en lotes de 5.

### 3.3. Cobertura temporal observada (Bronze)

* Tabla `weather.bronze.ana_rio_uruguai`: registros desde 1950 (ver `notebooks/03_EDA/EDA_in_Bronze.ipynb`, sección "ANA Lluvias registradas").
* Tabla `weather.bronze.nivel_ana`: registros desde 1950, con buena completitud anual.

### 3.4. Notebooks asociados

* Landing diaria: `notebooks/00_Landing/ANA_Hidrico/Daily_ANA.ipynb`.
* Landing histórica: **movida a ejecución local** (`notebooks_local/ana_historic_backfill/run_backfill_local.py`, rama `feature/ana-backfill-automation`, no en `main`). `notebooks/00_Landing/ANA_Hidrico/Historic_ANA.ipynb` documenta la lógica (mismo endpoint/batching) pero ya no corre en Databricks — ver Decisión 016. El notebook original que pegaba contra el endpoint legado (`snirh.gov.br/hidroweb/rest/api/seriehistorica`, hoy muerto con 401) fue reescrito el 2026-08-05 (Decisión 015) antes de moverse a local el 2026-08-14.
* Bronze diaria: `notebooks/02_Bronze/ETL_Bronze_ANA.ipynb` (también consume el histórico: lee todo el folder `json/` sin distinguir origen del archivo, así que los JSON subidos por `notebooks_local/ana_historic_backfill/sync_to_databricks.py` se mergean en el próximo run diario sin ningún job adicional).

### 3.5. Rutas de almacenamiento

* Landing daily: `/Volumes/weather/raw/ana_volume/json/` (archivos `ANA_YYYY_MM_DD.json`).
* Landing histórico: `/Volumes/weather/raw/ana_volume/json/` (archivos `ANA_HIST_<inicio>_<fin>.json`, subidos desde local — ver Decisión 016).

### 3.6. Job Databricks

* `All_Estacoes_ANA_Daily`: `Daily_ANA -> ETL_Bronze_ANA`. Ejecución serverless. También absorbe el backfill histórico subido desde local (mismo folder `json/`).
* ~~`ANA_Historic_Backfill`~~: eliminado de `databricks.yml` (Decisión 016). El backfill histórico corre 100% local (`notebooks_local/ana_historic_backfill/`), con Task Scheduler de Windows para automatizarlo y un dashboard Gradio (`dashboard_app.py`) para monitorear/controlar. Databricks solo recibe los JSON ya descargados vía `sync_to_databricks.py`.

### 3.7. Campos clave

* `codigoestacao`: identificador de estación.
* `Data_Hora_Medicao`: timestamp de medición.
* `Data_Atualizacao`: timestamp de actualización (usado para deduplicar).
* `Chuva_Adotada`: lluvia adoptada (string con coma decimal).
* `Cota_Adotada`: nivel adoptado.

### 3.8. Estado

`Bronze operativo + ingesta diaria activa`

### 3.9. Limitaciones conocidas

* Algunos campos numéricos vienen como string con coma decimal (`Chuva_Adotada`).
* Frecuencia subdiaria; requiere agregación en Silver para granularidad diaria.
* Posibles duplicados por `(codigoestacao, Data_Hora_Medicao)`; el daily ya hace dedupe por `Data_Atualizacao`.
* **`Chuva_Adotada` en las 22 estaciones con curva de `alta_frontera` (grupo A) es escasa**: sólo 9
  de las 22 reportan lluvia alguna vez, y sólo desde 2026-03-03. Pero esto **no es representativo
  de la cobertura real de lluvia de la sub-cuenca** — ver 3.10. `weather.silver.rainfall_daily`
  (agregación diaria por `codigoestacao`, `ETL_Silver_Rainfall_Daily.ipynb`) publica toda estación
  con dato real, sin umbral de exclusión (R8); la cobertura real llega a Gold como columna
  (`lluvia_agregado_alta_frontera_cobertura_pct`), no como portón binario.

### 3.10. Tabla de referencia `weather.silver.estacion_subcuenca`

* **Qué es**: mapea cada `codigoestacao` del inventario ANA a su sub-cuenca (`alta_frontera`,
  `intermedia_paso_libres`, `baja_salto_grande`). La usan tanto el agregado de lluvia como el de
  caudal en `ETL_Gold_Training_Dataset_v0.ipynb` para filtrar a `alta_frontera` (Decisión 018).
* **Origen del campo `subcuenca`**: viene resuelto por el proveedor en el mismo inventario que ya
  usa `Daily_ANA.ipynb` como universo de descarga
  (`/Volumes/weather/raw/ana_volume/estaciones_rio_uruguai_pluvio_fluvio.json`, columna
  `subcuenca_nombre`). Se validó con un join espacial independiente (`geopandas`) contra
  `SIG/subcuenca_1_frontera.gpkg`: 1.386/1.387 coincidencias (99,9%).
* **Siembra**: `MERGE` idempotente en `notebooks/04_Silver/DDL_Silver_Gold.ipynb`, corre en cada
  ejecución del job (`Silver_Gold_Initial_Load_v0` y `Silver_Gold_Daily_Incremental`), no es un paso
  manual. Hasta 2026-08-22 la tabla tenía **sólo 22 filas** (el grupo A, sembradas a mano fuera de
  cualquier notebook, origen no documentado) — ver Decisión 024. Desde esa fecha tiene las
  **1.387** estaciones del inventario completo: 782 en `alta_frontera`, 581 en
  `intermedia_paso_libres`, 24 en `baja_salto_grande`.
* **Efecto en lluvia**: de las 782 estaciones de `alta_frontera` en el inventario, **332 tienen
  `Chuva_Adotada` real** en `weather.bronze.ana_rio_uruguai`, con historia desde **1923-01-01**. El
  hallazgo "0 días de lluvia en 26 años" de la Decisión 023 era un artefacto de esta tabla teniendo
  sólo 22 filas, no una limitación de la fuente (Decisión 024). Con la tabla completa,
  `training_dataset_v0.lluvia_acumulada_mm` pasa de 1,42% a 99,65% de filas no nulas, con 100% de
  cobertura anual todos los años 2000-2025.
* **Sí afecta caudal** (corrección 2026-08-24, Decisión 028): la Decisión 024 había registrado que
  el agregado de caudal quedaba fuera de este cambio porque depende de
  `weather.silver.river_discharge_daily` y no de `estacion_subcuenca` — afirmación incompleta.
  `ETL_Gold_Training_Dataset_v0.ipynb` filtra `river_discharge_daily` a `alta_frontera` con el
  mismo `JOIN` contra `estacion_subcuenca` que usa lluvia, así que el caudal sí depende de las dos
  tablas a la vez (curva vigente **y** sub-cuenca). Al resembrar el inventario completo, la
  Decisión 024 amplió sin saberlo también el universo del agregado de caudal: de las 40 estaciones
  "grupo B" (con curva, fuera de la cuenca alta según el barrido de la Fase 2), 14 caen en
  `alta_frontera` con la unión espacial real y ya contribuyen a
  `caudal_agregado_alta_frontera_m3s` sin haber tocado el código de agregación (era dinámico desde
  el principio). Detalle completo, incluyendo los 14 códigos y la densificación por año, en la
  Decisión 028 (cierre de la Fase 7 del roadmap).

---

## 4. ANA — Niveles hidrométricos (target)

### 4.1. Origen

* Misma API que sección 3 (HidroinfoanaSerieTelemetricaAdotada/v2).
* Filtra a una estación específica por defecto (`STATION_CODE = 74100000`); el job histórico cubre múltiples estaciones objetivo.

### 4.2. Cobertura espacial

* Estaciones objetivo candidatas para puntos críticos de predicción: `2751083`, `2751037`, `2752032`, `2751066`, `2753044` (definición pendiente, ver `decisions.md` Decisión 005).

### 4.3. Cobertura temporal observada (Bronze)

* Tabla `weather.bronze.nivel_ana`: rango y conteo registrados en `notebooks/03_EDA/EDA_in_Bronze.ipynb`.
* EDA marca uso preferente desde 1950 por completitud anual.

### 4.4. Notebooks asociados

* Landing diaria: `notebooks/00_Landing/ANA_Hidrico/Daily_Nivel_ANA.ipynb`.
* Landing histórica: `notebooks/00_Landing/ANA_Hidrico/Historic_Nivel_ANA.ipynb`.
* Bronze diaria: `notebooks/02_Bronze/ETL_Bronze_Nivel_ANA.ipynb` (MERGE Delta por `codigoestacao + Data_Hora_Medicao`).
* Bronze histórica: `notebooks/02_Bronze/ETL_Bronze_Nivel_ANA_Histo.ipynb`.

### 4.5. Rutas

* Landing daily: `/Volumes/weather/raw/ana_volume/json/daily/`.
* Landing histórico: `/Volumes/weather/raw/ana_volume/json/serie_<codigo>.json`.

### 4.6. Job Databricks

* `Nivel_ANA_Target`: `Daily_Nivel_ANA -> ETL_Bronze_Nivel_ANA`. Ejecución serverless.

### 4.7. Campos clave

* `codigoestacao`, `Data_Hora_Medicao`, `Cota_Adotada` (nivel en cm o m según estación — verificar en Silver).

### 4.8. Estado

`Bronze operativo + ingesta diaria activa + EDA realizado`

### 4.9. Limitaciones conocidas

* Frecuencia subdiaria irregular; mediana de intervalo varía por estación (ver función `analizar_frecuencia` en EDA).
* Posibles outliers detectados por IQR sobre `Cota_Adotada`.
* Algunas estaciones del listado objetivo pueden estar ausentes en Bronze; el EDA tiene check explícito.

---

## 5. METAR — Temperatura aeropuertos Brasil

### 5.1. Origen

* Proveedor: NOAA / Aviation Weather Center.
* Endpoint: `https://aviationweather.gov/api/data/metar`.
* Sin autenticación.
* Parámetros: `ids`, `hours`, `format=json`.

### 5.2. Cobertura espacial

* Aeropuertos: `SBGR` (São Paulo/Guarulhos), `SBCT` (Curitiba), `SBPA` (Porto Alegre), `SBFL` (Florianópolis).

### 5.3. Cobertura temporal observada (Bronze)

* Tabla `weather.bronze.metar`: rango por `icaoId` registrado en EDA.
* Frecuencia horaria.

### 5.4. Notebooks asociados

* DDL Landing: `notebooks/00_Landing/Temp_Airport/DDL_SCHEMA_RAW.ipynb`.
* Landing diaria: `notebooks/00_Landing/Temp_Airport/Daily/Daily_Temp_Airport.ipynb`.
* Landing histórica: `notebooks/00_Landing/Temp_Airport/Historic/`.
* Bronze diaria: `notebooks/02_Bronze/ETL_Bronze_Temp_Daily.ipynb`.
* Bronze histórica: `notebooks/02_Bronze/ETL_Bronze_Temp_Airport_Hist.ipynb`.

### 5.5. Rutas

* Landing daily: `/Volumes/weather/raw/noaa_volume/json/daily/` (archivos `METAR_YYYY_MM_DD.json`).

### 5.6. Job Databricks

* `Temperature_Airport_Brasil`: `Daily_Temp_Aeroport -> ETL_Bronze_Temp_Aeroport`. Ejecución serverless.

### 5.7. Campos clave

* `icaoId` / `stationId`: aeropuerto.
* `obsTime`: epoch UTC de la observación.
* `reportTime`: timestamp de reporte.
* `temp`: temperatura en °C.
* `tmpf`: temperatura en °F.
* `rawText`: METAR crudo.

### 5.8. Estado

`Bronze operativo + ingesta diaria activa + EDA realizado`

### 5.9. Limitaciones conocidas

* Frecuencia horaria; requiere agregación diaria (min/max/avg) en Silver.
* Cobertura limitada a 4 aeropuertos en esta etapa; ampliar requiere actualizar lista en `Daily_Temp_Airport.ipynb`.
* Cuenca del Río Uruguay propiamente dicha está parcialmente cubierta (SBPA y SBFL son cercanos; SBGR/SBCT son más lejanos pero cubren el área de descarga atmosférica del sistema).

---

## 6. Salto Grande — Lluvia estaciones

### 6.1. Origen

* Proveedor: Comisión Técnica Mixta de Salto Grande.
* Endpoint SOAP: `https://www.saltogrande.org/ws.php`.
* Operación: `HidroSerieHistorica`.
* Variable ingestada: `P` (precipitación).
* Autenticación: no requerida en el script disponible.

### 6.2. Cobertura espacial

* Estaciones activas disponibles en `/Volumes/weather/raw/sg_volume/sg_estaciones_activas/estaciones_activas.csv`.
* Se filtran estaciones cuyo campo `Variables` contiene `P`.
* El inventario observado por MCP en Databricks contiene columnas `Id`, `Nombre`, `Latitud`, `Longitud`, `Fecha`, `Variables`.

### 6.3. Cobertura temporal

* La API expone hasta 30 días recientes.
* La ingesta diaria calcula la ventana desde `hoy - 30 días` hasta `ayer` y descarga solo los días faltantes en Raw.
* Raw guarda un archivo por día para permitir reprocesamiento y auditoría.

### 6.4. Notebooks asociados

* DDL: `notebooks/01_DDL/DDL_SG_Rainfall.ipynb`.
* Landing diaria: `notebooks/00_Landing/Salto_Grande/Daily_SG_Rainfall.ipynb`.
* Bronze diaria: `notebooks/02_Bronze/ETL_Bronze_SG_Rainfall.ipynb`.
* Silver diaria: `notebooks/04_Silver/ETL_Silver_SG_Rainfall_Daily.ipynb`.

### 6.5. Rutas

* Inventario estaciones: `/Volumes/weather/raw/sg_volume/sg_estaciones_activas/estaciones_activas.csv`.
* Landing daily: `/Volumes/weather/raw/sg_volume/json/daily/` (archivos `SG_P_YYYY_MM_DD.json`).

### 6.6. Tablas

* Bronze: `weather.bronze.sg_rainfall`.
* Silver: `weather.silver.sg_rainfall_daily`.
* Calidad: `weather.silver.attribute_quality` con `source_table = 'weather.silver.sg_rainfall_daily'`.

### 6.7. Job Databricks

* `SG_Rainfall_Daily_Incremental`: `DDL_SG_Rainfall -> Daily_SG_Rainfall -> ETL_Bronze_SG_Rainfall -> ETL_Silver_SG_Rainfall_Daily`.
* Schedule propuesto: `03:30` America/Montevideo.

### 6.8. Campos clave

* `Id_Estacion`: identificador de estación SG.
* `Fecha`: día de medición.
* `P`: precipitación diaria.
* `Nombre`, `Latitud`, `Longitud`: metadata de estación copiada desde el inventario activo.

### 6.9. Estado

`Pipeline versionado para Raw + Bronze + Silver`

### 6.10. Limitaciones conocidas

* La API solo permite recuperar la ventana reciente de 30 días; si el job falla más de 30 días, habrá una brecha no recuperable desde este endpoint.
* Se escriben archivos Raw vacíos para días sin registros, evitando reconsultas infinitas de días válidos sin datos.
* **Ninguna estación SG cae en `alta_frontera`** (Decisión 023, 2026-08-21): el inventario de
  estaciones activas ya trae `subcuenca_id`/`subcuenca_nombre` resueltos por el proveedor — 59 de
  69 estaciones activas en `baja_salto_grande`, las 10 restantes en `intermedia_paso_libres`, 0 en
  `alta_frontera`. `weather.silver.sg_rainfall_daily` por lo tanto no se une al agregado de lluvia
  de Gold, que sólo publica `alta_frontera` (Decisión 018): conectarla violaría el mismo alcance
  espacial que la Decisión 023 corrigió para la lluvia de ANA.
* SG se mantiene en tablas separadas de ANA para preservar trazabilidad por fuente.

---

## 7. ECMWF — Pronóstico de precipitación (control forecast + perturbed forecast)

### 7.1. Origen

* `cf` (control forecast del ensemble) y `pf` (perturbed forecast, 50 miembros): dataset `tigge-forecasts` en el portal nuevo ECMWF Data Stores (`https://ecds.ecmwf.int`), vía paquete estándar `cdsapi`. Request MARS clásico (`origin=ecmf`, `levtype=sfc`, `param=228228`, `type=cf`/`pf`).
* Autenticación: credenciales `cdsapi_url` / `cdsapi_key` (del `~/.cdsapirc` del usuario) guardadas en el Databricks secret scope `ecmwf`, leídas vía `dbutils.secrets.get`.
* Nota histórica: el ECMWF Web API legacy (`api.ecmwf.int`, paquete `ecmwfapi`) quedó deshabilitado (token) y fue reemplazado por este portal nuevo — ver `decisions.md`.
* `fc` (determinístico, HRES vía ECMWF Open Data, `ecmwf.opendata.Client`) se evaluó e implementó, pero se **descartó**: requiere `cfgrib`/`eccodes`, que desde la versión ≥2.39 depende de la librería nativa `eckit` y esta aborta el proceso (`SIGABRT`) en el compute serverless de este workspace — el workspace no permite compute clásico como alternativa. Ver Decisión 013 en `decisions.md` para el diagnóstico completo.

### 7.2. Cobertura espacial

* Bounding box de descarga calculado dinámicamente antes de cada corrida a partir de `SIG/subcuencas_modelo.geojson` (función `compute_download_area()`, sin `geopandas`: lee el GeoJSON a mano), redondeado al múltiplo de grilla 0,25° más cercano + 1 celda de margen. No se descarga un área fija ni el grid global.
* Resolución nativa 0,25° x 0,25°.
* El recorte al polígono exacto de las 3 sub-cuencas (con buffer ~0,15°, ~15 km) se aplica recién en **Silver**, no en Landing/Bronze — Bronze conserva todo el bounding box descargado sin recortar.

### 7.3. Cobertura temporal

* Horizonte de pronóstico: todos los steps disponibles cada 24h, de 0h a 360h (`range(0, 361, 24)`), por corrida.
* TIGGE tiene latencia de archivo — la corrida de `hoy` y `hoy-1` normalmente no están disponibles; el notebook busca hacia atrás desde `hoy-2` hasta `hoy-5` (`TIGGE_LAG_DAYS=2`, `MAX_LAG_SEARCH=5`) hasta encontrar la primera corrida publicada.
* `tp` (precipitación acumulada desde el inicio de la corrida): `tigge-forecasts` vía `cdsapi` entrega en kg/m² (equivalente a mm, sin conversión) — confirmado empíricamente vía `GRIB_units`, no asumido.

### 7.4. Notebooks asociados

* DDL: `notebooks/01_DDL/DDL_ECMWF_Forecast.ipynb` (crea el volumen, carpetas, tablas Bronze y Silver).
* Landing diaria: `notebooks/00_Landing/ECMWF/Daily_ECMWF_CF.ipynb` y `Daily_ECMWF_PF.ipynb`.
* Bronze diaria: `notebooks/02_Bronze/ETL_Bronze_ECMWF_CF.ipynb` y `ETL_Bronze_ECMWF_PF.ipynb`.
* Silver diaria (recorte al polígono real): `notebooks/04_Silver/ETL_Silver_ECMWF_CF.ipynb` y `ETL_Silver_ECMWF_PF.ipynb`.

### 7.5. Rutas de almacenamiento

* Volumen: `weather.raw.ecmwf_volume`.
* `cf`: `/Volumes/weather/raw/ecmwf_volume/cf_tigge/{raw,json}/` (archivos `ECMWF_CF_YYYY_MM_DD_t{HH}.{nc,json}`).
* `pf`: `/Volumes/weather/raw/ecmwf_volume/pf_tigge/{raw,json}/` (archivos `ECMWF_PF_YYYY_MM_DD_t{HH}.{nc,json}`).
* Idempotencia: si ya existe el JSON de la corrida (`run_date`+`run_time`), se saltea salvo `force_reload=true`.

### 7.6. Tablas

* Bronze: `weather.bronze.ecmwf_forecast_cf`, `weather.bronze.ecmwf_forecast_pf` (ambas con columna `number` de ensemble). Contienen todo el bounding box descargado, sin recortar al polígono.
* Silver: `weather.silver.ecmwf_forecast_cf_basin`, `weather.silver.ecmwf_forecast_pf_basin`. Solo puntos de grilla dentro del buffer del polígono de las 3 sub-cuencas, tageados con `subcuenca_id`/`subcuenca_nombre`.

### 7.7. Job Databricks

* `ECMWF_Forecast_Daily_Incremental`: `DDL_ECMWF_Forecast -> Daily_ECMWF_CF -> ETL_Bronze_ECMWF_CF -> ETL_Silver_ECMWF_CF` (y, si se agrega `pf` diario, en paralelo).
* Schedule: `08:00 UTC` diario (ciclos ECMWF son en UTC).
* Validado manualmente end-to-end en Databricks (Landing → Bronze → Silver) antes de activar el schedule.

### 7.8. Campos clave

* `run_date`, `run_time`: fecha/hora de la corrida del modelo (UTC).
* `step_hours`: horizonte de pronóstico en horas (0–360).
* `valid_date`, `valid_datetime`: momento al que corresponde el pronóstico (`run` + `step`).
* `latitude`, `longitude`: punto de grilla (longitud normalizada a convención -180/180).
* `tp_mm`: precipitación acumulada desde el inicio de la corrida, en mm.
* `number`: identificador del miembro del ensemble (`cf` = control = 0; `pf` = 1–50).
* `subcuenca_id`, `subcuenca_nombre` (solo Silver): sub-cuenca a la que pertenece el punto de grilla.

### 7.9. Estado

`Bronze + Silver operativos, job diario activo (validado manualmente el 2026-07-27). fc descartado (ver 7.1 y Decision 013).`

### 7.10. Limitaciones conocidas

* `tp` es acumulado desde el inicio de la corrida, no incremental entre steps consecutivos — no sumar entre steps sin restar el acumulado previo.
* `cf`/`pf` no están disponibles el mismo día ni el día anterior (latencia de archivo TIGGE); el `run_date` efectivo normalmente queda 2+ días detrás de la fecha de ejecución del job.
* El compute (Databricks Free Edition) invalida la sesión de `spark` si un notebook llama a `dbutils.library.restartPython()` después de un `%pip install` — los notebooks Silver instalan `geopandas`/`pyogrio` sin reiniciar el kernel para evitarlo.
* `type="cf"`/`type="pf"` con `param="tp"` no existen en ECMWF Open Data (solo en `tigge-forecasts`); por eso salen exclusivamente del portal ECMWF Data Stores.

### 7.11. Reconstrucción histórica (backfill) de `cf` y `pf`

* Cobertura real disponible: **2006-10-01 → hoy**. El archivo TIGGE no tiene datos anteriores a octubre de 2006 (confirmado en la documentación de ECMWF); no es posible reconstruir desde 2000 con esta fuente. `fc` (Open Data) ya está fuera de alcance por completo (7.1) — nunca hubiera tenido archivo histórico de todas formas: solo retiene ~12 corridas (2-3 días), reconstruirlo hubiera requerido un Service Agreement/acceso MARS distinto con ECMWF (ver Decisión 012 en `decisions.md`).
* Notebooks: `notebooks/00_Landing/ECMWF/Historic_ECMWF_CF.ipynb` y `Historic_ECMWF_PF.ipynb`. Reusan las mismas tablas Bronze/Silver que el job diario sin ningún cambio de esquema — escriben un JSON por día en el mismo folder (`cf_tigge/json/`, `pf_tigge/json/`), con lo cual Bronze (que lee toda la carpeta) no distingue si el archivo vino del job diario o del backfill.
* Estrategia anti-bloqueo de API: un solo request de `cdsapi` a la vez, agrupando fechas en un único request por lote en vez de un request por día — 1 año calendario por request para `cf` (~5.840 "fields": 365 días × 16 steps), 1 mes calendario por request para `pf` (~24.000 fields con los 50 miembros, para no acercarse a órdenes de magnitud grandes sin límite documentado). Tope de `max_batches_per_run` lotes por corrida (25 para `cf`, 50 para `pf`), corte inmediato ante el primer fallo (no reintentos en bucle), resumible por diseño (saltea lotes con todos los días ya aterrizados).
* Bug encontrado y corregido (2026-08-04): `date_range_str()` construía el rango con sintaxis MARS clásica (`"start/to/end"`), que el portal nuevo ECMWF Data Stores (`ecds.ecmwf.int`) rechaza con `400 Bad Request: Date ranges must be of the form "start_date/end_date"`. Como el fallo se tragaba silenciosamente (diseño: "corta ante el primer fallo, no reintenta", pero sin marcar el task como fallido), el backfill venía reportando `SUCCESS` en Databricks sin haber avanzado nunca más allá del primer lote. Fix: `"start/end"` sin `/to/`.
* Job Databricks: `ECMWF_Forecast_Historic_Backfill`, **sin schedule** (se dispara a mano, "Run now", tantas veces como haga falta hasta terminar). Encadena `Historic_ECMWF_CF` → Bronze → Silver → `Historic_ECMWF_PF` → Bronze → Silver de forma estrictamente secuencial (nunca en paralelo entre sí ni con `ECMWF_Forecast_Daily_Incremental`, porque comparten cuenta/token contra la misma cola de TIGGE/ECDS).
* Silver histórico usa un tercer `load_mode=backfill` (además de `full`/`incremental`) con `range_start`/`range_end` explícitos — necesario porque el modo `incremental` filtra por `MAX(run_date) - lookback` y nunca recogería filas más viejas que el máximo ya cargado por el job diario. El job de backfill pasa ese rango automáticamente vía task values (`{{tasks.Historic_ECMWF_CF.values.range_start}}`), publicados por el propio notebook histórico al final de cada corrida.
* Estado: `Implementado, no corrido en Databricks todavía (2026-07-28). Falta validar contra la API real y calibrar max_batches_per_run según el tiempo de cola observado.`

---

## 8. ANA — Curvas de aforo (rating curve) y conversión nivel → caudal

### 8.1. Origen

* Misma API que sección 3 (HidroWebService), otros dos endpoints:
  * `/EstacoesTelemetricas/HidroSerieCurvaDescarga/v1`: segmentos de curva-chave (coeficientes `Coef_a`, `Coef_h0`, `Coef_n` de `Q = A·(H−H0)^N`, por vigencia).
  * `/EstacoesTelemetricas/HidroSerieResumoDescarga/v1`: aforos reales (medições de campo), usados para validar la curva, no para calcular caudal.
* El endpoint de curva filtra por `Data_Ultima_Alteracao` (fecha de modificación del registro en el sistema de ANA), no por vigencia — ver Decisión 017 en `docs/decisions.md` para el detalle de la calibración y de la ventana de barrido adoptada.

### 8.2. Cobertura espacial

* Universo calculado en vivo: `notebooks_local/ana_rating_curve/estaciones_nivel.json`, todas las estaciones con `Cota_Adotada` en `weather.bronze.ana_rio_uruguai` (392 al 2026-08-19). Grupo A (22, historia profunda) completo; grupo B (~370) en descarga.

### 8.3. Cobertura temporal observada

* Curvas: histórico completo por estación (para 74100000, 8 vigencias desde 1948).
* Aforos: descargados desde 2000-01-01 (piso del dataset, Decisión D4 del plan).
* `river_discharge_daily`: 2000-01-01 → hoy, grupo A verificado con 210.106 filas / 22 estaciones.

### 8.4. Notebooks asociados

* Landing local (no Databricks): `notebooks_local/ana_rating_curve/download_rating_curves_batch.py` (barrido multi-estación) y `download_rating_curve.py` (script original, una estación, reutilizado como librería de funciones).
* Bronze: `notebooks/02_Bronze/ETL_Bronze_Rating_Curve.ipynb`.
* Silver: `notebooks/04_Silver/ETL_Silver_River_Discharge_Daily.ipynb` (también puebla `weather.silver.rating_curve_segments`).
* Gold: cambios integrados en `notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb` (no es un notebook aparte).
* Calidad: `notebooks/06_Quality/Validate_River_Discharge.ipynb`.
* DDL: tablas nuevas en `notebooks/04_Silver/DDL_Silver_Gold.ipynb`.

### 8.5. Rutas de almacenamiento

* `/Volumes/weather/raw/ana_volume/rating_curves/curve_segments/` — un JSON por estación (`curva_<codigo>.json`).
* `/Volumes/weather/raw/ana_volume/rating_curves/discharge_measurements/` — un JSON por estación (`aforos_<codigo>.json`).

### 8.6. Tablas

* Bronze: `weather.bronze.ana_rating_curve_segments`, `weather.bronze.ana_discharge_measurements`.
* Silver: `weather.silver.rating_curve_segments`, `weather.silver.river_discharge_daily`, `weather.silver.estacion_subcuenca` (referencia estación→sub-cuenca, sembrada solo para el grupo A).
* Gold: columnas de caudal en `weather.gold.training_dataset_v0` (`caudal_actual_m3s`, `caudal_t_mas_*`, `caudal_agregado_<subcuenca>_*`, etc. — ver DDL para la lista completa).

### 8.7. Job Databricks

* `Rating_Curve_Discharge_Initial_Load`: `ETL_Bronze_Rating_Curve -> ETL_Silver_River_Discharge_Daily -> Validate_River_Discharge`. Sin schedule, se dispara a mano mientras dura la Fase 1. El Gold se corre por separado (`silver_gold_initial_load_v0`, task `ETL_Gold_Training_Dataset_v0`) hasta que se decida encadenarlo.

### 8.8. Campos clave

* Curva: `codigoestacao`, `Numero_Curva` (segmento/total), `Periodo_Validade_Inicio`/`Fim` (vigencia), `Coef_a`, `Coef_h0` (ya en metros), `Coef_n`, `Cota_Minima`/`Maxima` (rango calibrado, cm).
* Aforos: `codigoestacao`, `Data_Hora_Dado`, `Cota (cm)`, `Vazao (m3/s)` (nombres de campo con espacios/unidades, distinto del resto de endpoints ANA).
* Silver: `caudal_m3s`, `caudal_metodo` (`interpolado`/`extrapolado_superior`/`extrapolado_inferior`/`bajo_cero_curva`/`sin_curva`), `distancia_fuera_rango_cm`, `supera_aforo_maximo`, `caudal_confiable`.

### 8.9. Estado

`Bronze + Silver + Gold operativos para el grupo A (22 estaciones). Grupo B (~370) en descarga de curvas al 2026-08-19, sin aforos todavía (pasada aparte, no bloqueante). Sin schedule ni cadencia de refresco definida.`

### 8.10. Limitaciones conocidas

* `weather.silver.estacion_subcuenca` solo tiene mapeo para el grupo A (todas en `alta_frontera`) — los agregados de caudal por sub-cuenca de `intermedia_paso_libres`/`baja_salto_grande` están vacíos hasta mapear el grupo B.
* Dos estaciones del grupo A (70100000, 70300000) tienen MAPE > 100% contra aforos reales — quedan marcadas `is_usable=false`, sin investigar la causa raíz (coeficientes sospechosos o vigencia mal resuelta).
* Ninguna estación del grupo A tuvo filas `extrapolado_*` en el histórico 2000-2026 — la lógica D3 (extrapolar con flag en vez de NULL) está implementada pero no ejercitada todavía por datos reales; falta observarla en una crecida real o en estaciones del grupo B con rango calibrado más angosto.
* La curva completa de una estación se descarga sin recortar por fecha (puede incluir vigencias anteriores a 2000), pero `river_discharge_daily` sí aplica el piso 2000-01-01 al nivel — ver plan §2.1.

## 9. Fuentes candidatas no ingestadas

### 9.1. Evaporación

* Variables: evaporación diaria, acumulada.
* Estado: `No ingestada`.
* Postergada para `training_dataset_v1`.

### 9.2. Lluvias y niveles Argentina

* Posibles proveedores: SNIH (Sistema Nacional de Información Hídrica), INA (Instituto Nacional del Agua).
* Estado: `No ingestada`.
* Importancia para el punto crítico Salto Grande.

### 9.3. Temperatura — INMET (Instituto Nacional de Meteorologia, Brasil)

* Complemento a METAR aeropuertos (Decisión de mantener METAR: sección 5). METAR cubre 4
  aeropuertos, lejanos al eje del río; INMET tiene estaciones automáticas dedicadas dentro de la
  cuenca.
* Estado: **Ingestada (2026-08-24)**, Fase 3 del roadmap cerrada. Investigación 2026-08-22,
  implementación y backfill histórico completo 2026-08-24.

**Catálogo de estaciones (verificado)**

* Endpoint: `GET https://apitempo.inmet.gov.br/estacoes/T` (automáticas) / `.../estacoes/M`
  (manuales/convencionales). Sin autenticación, pero **requiere un header `User-Agent` de
  navegador**: con el `User-Agent` por defecto de `curl`/`requests` el servidor corta la conexión
  TLS (`Connection reset`) antes de responder; con un `User-Agent` de Chrome responde `200` normal.
* Devuelve JSON con 674 estaciones automáticas a nivel nacional: `CD_ESTACAO`, `DC_NOME`,
  `SG_ESTADO`, `VL_LATITUDE`, `VL_LONGITUDE`, `VL_ALTITUDE`, `DT_INICIO_OPERACAO`, `CD_SITUACAO`
  (`Operante`/`Pane`).
* Filtrando a un bounding box aproximado de la cuenca (lat -29,5 a -26,5, lon -54,5 a -49,5):
  **49 estaciones automáticas** caen dentro del rectángulo, pero el bounding box es más grande
  que el polígono real de la cuenca (incluye terreno vecino fuera de cualquier sub-cuenca). El
  join espacial exacto contra `SIG/subcuencas_modelo.geojson` (`notebooks_local/inmet_backfill/
  fetch_station_catalog.py`, `geopandas.sjoin` con predicado `within`) da el número real:
  **27 estaciones dentro de alguna de las tres sub-cuencas — 15 en `alta_frontera`, 12 en
  `intermedia_paso_libres`, 0 en `baja_salto_grande`** (esa sub-cuenca no cae en el bounding
  box). Corrige la estimación de 42 hecha en la investigación inicial (2026-08-22), que era
  sólo el filtro de bounding box sin el join de polígono. La mayoría de las 15 de
  `alta_frontera` operan desde 2006-2008; unas pocas abrieron entre 2025 y 2026.

**Histórico masivo (verificado, mecanismo recomendado para backfill)**

* `GET https://portal.inmet.gov.br/uploads/dadoshistoricos/{AAAA}.zip` — un ZIP por año calendario,
  **2000 a 2026 confirmados existentes** (HEAD 200 en ambos extremos probados). Sin autenticación,
  mismo requisito de `User-Agent` de navegador.
* Cada ZIP (~100 MB, probado con 2023: 107 MB, 567 archivos) trae **un CSV por estación,
  nacional** (todos los tipos), no sólo la cuenca — hay que filtrar client-side por los 27 códigos
  de estación de la cuenca (confirmado en la implementación: `download_inmet_zips.py` matchea por
  patrón `_{codigo}_` en el nombre de archivo dentro del ZIP).
* Formato del CSV (verificado en `INMET_S_RS_A805_SANTO AUGUSTO_01-01-2023_A_31-12-2023.CSV`):
  encoding `latin-1`, separador `;`, decimal con coma, 8 líneas de metadata (`REGIAO`, `UF`,
  `ESTACAO`, `CODIGO (WMO)`, `LATITUDE`, `LONGITUDE`, `ALTITUDE`, `DATA DE FUNDACAO`) seguidas de
  una fila de encabezado y filas horarias (`Data`, `Hora UTC`, y luego las variables). Campo de
  temperatura relevante: `TEMPERATURA DO AR - BULBO SECO, HORARIA (°C)` (instantánea), más máx/mín
  de la hora anterior y punto de rocío. También trae `PRECIPITAÇÃO TOTAL, HORÁRIO (mm)` — mismo
  archivo serviría para densificar lluvia si alguna vez hiciera falta.

**Endpoint incremental/tiempo real (investigado, no funcional al 2026-08-22)**

* La documentación comunitaria (paquetes `inmetpy`, scripts públicos en GitHub) describe rutas
  `GET /estacao/{data_ini}/{data_fin}/{cod_estacao}` (horario) y
  `GET /estacao/diaria/{data_ini}/{data_fin}/{cod_estacao}` (diario) sobre la misma base
  `apitempo.inmet.gov.br`.
* **Probado en vivo (2026-08-22)** con múltiples combinaciones de estación/rango
  (`A001`/`A805`, rangos en 2015, 2025 y 2026): la ruta horaria responde `204 No Content` en
  *todos* los casos (ruta reconocida, sin datos) y la ruta diaria y `/estacao/dados/{fecha}`
  responden `404 E_ROUTE_NOT_FOUND`. El manual oficial
  (`portal.inmet.gov.br/manual/manual-de-uso-da-api-estações`) también devuelve `404`.
  **Conclusión: esa superficie de la API cambió o se dio de baja** desde que se escribieron esas
  integraciones (coincide con reportes públicos de que `inmetpy` quedó roto por un cambio de
  INMET). No sirve hoy para un job diario incremental tal como está documentada.
* No se implementó re-descarga periódica del ZIP del año en curso como mecanismo incremental
  (quedó fuera de esta fase, ver Decisión 025): no hay job diario de INMET en `databricks.yml`,
  sólo el backfill histórico local. Queda documentado como opción futura si se identifica el
  endpoint vivo actual, o si se decide vivir con la re-descarga del ZIP corriente.

**Implementación (2026-08-24, Decisión 025)**

* Landing local en `notebooks_local/inmet_backfill/` (mismo patrón que
  `notebooks_local/ana_historic_backfill/`): `fetch_station_catalog.py` resuelve las 27
  estaciones de la cuenca (con sub-cuenca real via `geopandas.sjoin`) y
  `download_inmet_zips.py` descarga los 27 ZIP anuales (2000-2026), extrae en memoria sólo
  los CSV de esas estaciones (sin guardar los ~2,6 GB de ZIP en disco) y escribe JSON por
  estación/año. Backfill completo corrido 2026-08-24: **2.593.410 registros horarios** en 340
  archivos estación/año, 0 años fallidos. `sync_to_databricks.py` sube el catálogo y los JSON
  al Volume `weather.raw.inmet_volume`.
* Tabla Bronze: `weather.bronze.inmet (codigo_estacao STRING, data_hora_medicao STRING,
  temp_c DOUBLE, source_file STRING)`, clave lógica `(codigo_estacao, data_hora_medicao)`
  (DDL en `notebooks/04_Silver/DDL_Silver_Gold.ipynb`; MERGE append-only en
  `notebooks/02_Bronze/ETL_Bronze_INMET.ipynb`, mismo patrón que `ETL_Bronze_Temp_Daily.ipynb`
  para METAR). Sólo se conservan filas con temperatura no nula (tabla especifica de
  temperatura, no un passthrough crudo genérico).
* Unificación con METAR en `weather.silver.temperature_daily`: agregación horaria → diaria
  (avg/min/max) igual que METAR, con columna `fuente` (`metar`|`inmet`) y clave genérica
  `estacion_id` (= `icao_id` para METAR, = `codigo_estacao` para INMET). **No hizo falta
  ninguna regla de prioridad entre fuentes**: los 4 aeropuertos METAR están geográficamente
  fuera de las tres sub-cuencas (ver Decisión 025), así que METAR e INMET nunca compiten por
  el mismo territorio — Gold usa sólo INMET para el agregado de `alta_frontera`.

**Lado argentino/uruguayo de la cuenca (descartado por geografía, 2026-08-22)**

* `alta_frontera` (`SIG/subcuencas_modelo.geojson`, polígono `subcuenca_1_frontera`, Decisión 018:
  "Aporte hasta frontera Brasil/Argentina") queda **enteramente dentro de Brasil**: bounding box
  lon -53,25 a -49,28, lat -28,77 a -26,34 (Río Grande do Sul / Santa Catarina), verificado leyendo
  el GeoJSON directamente. No toca territorio argentino ni uruguayo — el punto de predicción
  (`ana_74100000`, Iraí) está justo en el punto donde el río *llega* a ser frontera, aguas abajo de
  toda la sub-cuenca que sí está en Gold. Por eso no hace falta evaluar SMN (Argentina) ni INUMET
  (Uruguay) como fuente de temperatura para el alcance actual: no habría estaciones propias de esos
  países dentro de la sub-cuenca que aportan al target.
* Se confirmó igual que el SMN (`smn.gob.ar`) publica un dataset abierto de estaciones y
  temperaturas mín/máx diarias sin autenticación en el portal nacional de datos abiertos
  (`datos.gob.ar`, dataset "smn-listado-estaciones-meteorologicas-smn"), por si en el futuro se
  revierte la Decisión 018 y se reabren `intermedia_paso_libres` o `baja_salto_grande` — esas dos sí
  se extienden hacia el oeste/sur, cerca de o cruzando la frontera con Argentina (`baja_salto_grande`
  llega a lon -58,46, ya en la zona de Salto Grande/Concordia). No se investigó el endpoint en
  profundidad porque no aplica al alcance de hoy; queda como punto de partida documentado para
  cuando corresponda.
* INUMET (Uruguay) ni se evaluó: ninguna de las tres sub-cuencas de la cuenca alcanza latitudes
  uruguayas (todas por encima de lat -31,9).

### 9.4. GEFS Reforecast v12 (NOAA) — pronóstico retrospectivo 2000-2019

* Cierra el hueco 2000-01 → 2006-09 que TIGGE no cubre (`cf`/`pf` arrancan en 2006-10, ver 7.11):
  la Decisión 021 baja el piso del pronóstico a 2000 empalmando esta fuente con TIGGE en el
  solapamiento 2006-10 → 2019 (13 años).
* Estado: **Landing + Bronze implementados y verificados contra Databricks real (2026-08-24,
  Decisión 029)**. Pendiente: correr el backfill histórico completo (decisión de volumen/
  miembros abierta, ver Decisión 029) y las tareas de Silver/calibración de la Fase 4.

**Origen y acceso (verificado)**

* `NOAA’s Global Ensemble Forecast System Version 12: Reforecast Data Storage Information`
  (`https://noaa-gefs-retrospective.s3.amazonaws.com/Description_of_reforecast_data.pdf`), el
  documento oficial de NOAA/PSL para este dataset.
* Bucket S3 público **sin autenticación** (`noaa-gefs-retrospective`, acceso anónimo/`--no-sign-request`),
  igual de gratuito que TIGGE Open Data — no hay ninguna vía paga que evaluar aquí (a diferencia
  de la Investigación A de la Fase 4, que es sobre `fc`/ECMWF, no sobre GEFS).
* Existe también un espejo en `ftp://ftp.emc.ncep.noaa.gov` (`GEFSv12/reforecast`), pero NOAA
  recomienda AWS por ancho de banda — no se evalúa el FTP.

**Cobertura temporal y miembros (verificado)**

* Reforecasts retrospectivos **2000-01-01 a 2019-12-31**, una corrida diaria a las 00 UTC (no 4
  corridas/día como el operativo real-time).
* **5 miembros** la mayoría de los días: `c00` (control) + `p01`..`p04` (perturbados).
  **Una vez por semana** (no se confirmó todavía si es miércoles fijo — pendiente de verificar al
  implementar, leyendo los nombres de carpeta reales de un mes de muestra) se corre un ensemble
  de **11 miembros** (`c00`..`p10`).
* Horizonte: **+16 días** en la corrida diaria estándar de 5 miembros; **+35 días** en la corrida
  semanal extendida de 11 miembros. **Cubre t+14 todos los días** (el horizonte máximo del
  dataset de tesis, ver roadmap §1), satisfaciendo el criterio de salida de la Investigación C
  de la Fase 4 sin necesidad de la corrida semanal extendida.

**Formato, grilla y estructura de directorios (verificado)**

* Formato **GRIB2** (no NetCDF como TIGGE/`cdsapi`) — mismo formato que `fc`/ECMWF Open Data,
  pero sin el crash de `cfgrib`/`eckit` de la Decisión 013 porque acá no hace falta decodificar
  in-process en Databricks serverless: la descarga corre en local (ver más abajo), igual que
  `fc` (Decisión 022).
* Grilla: **0,25° hasta el día +10**, cada 3 horas; **0,50° desde el día +10 en adelante**, cada
  6 horas. Convención de longitud **0 a 359,75°E** (equivalente a TIGGE, no a la convención
  -180/180 del resto del proyecto — requiere `normalize_longitude()`, igual que `common_ecmwf.py`).
  El t+14 relevante para el dataset cae en el tramo de 0,50°/6h, no en el de 0,25°/3h — resolución
  más gruesa que TIGGE en ese horizonte, pero utilizable (no descarta el horizonte, sólo lo
  densifica menos).
* Directorios (**verificado con un listado real del bucket, 2026-08-24, corrige/completa al
  documento oficial que no menciona este nivel**):
  `GEFSv12/reforecast/{yyyy}/{yyyymmdd00}/{miembro}/Days:1-10/{variable}_{yyyymmddhh}_{miembro}.grib2`
  y `.../Days:10-16/{variable}_{yyyymmddhh}_{miembro}.grib2` — dos archivos por variable+fecha+miembro,
  uno para el tramo de 0,25°/3h (días 1-10) y otro para el tramo de 0,50°/6h (días 10-16). Cada
  archivo trae además un `.grib2.idx` (índice de mensajes GRIB2, unos pocos KB) al lado.
* Variable de precipitación: **`apcp_sfc`** — precipitación total en kg/m² (≡ mm, sin conversión,
  igual unidad que `tp_mm` de TIGGE). **Gotcha de diseño, no asumido, confirmado en la tabla de
  variables del documento oficial:** a diferencia de `tp` de TIGGE (acumulado desde el inicio de
  la corrida), `apcp_sfc` es la suma **del bloque de 3h o 6h más reciente únicamente** (steps
  síncopicos 00/06/12/18 UTC acumulan las últimas 6h; 03/09/15/21 UTC acumulan las últimas 3h) —
  es decir, viene **incremental por ventana**, no acumulado corrida-a-fecha. Para producir una
  serie comparable a `tp_mm` de `cf`/`pf` (acumulado desde el inicio de la corrida, que es lo que
  consume Silver hoy) hay que sumar los incrementos sucesivos al aplanar, no copiar el valor tal
  cual. Esto se implementa en Silver o en el aplanado de Landing, a definir al implementar
  (mismo principio de "regla de negocio en Silver" de la Decisión 011, pero conviene resolverlo
  antes de escribir a JSON para no duplicar la lógica de acumulación en dos capas).

**Volumen y dimensionamiento (medido contra el bucket real, 2026-08-24)**

* Tamaño real de `apcp_sfc` para un día/miembro (`2018010100`, `c00`, medido con un listado S3
  real, no una descarga completa): `Days:1-10/` = 25.426.815 bytes (~24,3 MiB, grilla global
  0,25°, 80 pasos de 3h), `Days:10-16/` = 2.415.105 bytes (~2,3 MiB, grilla global 0,50°, pasos de
  6h) → **~26,5 MiB por día/miembro, grilla global sin recortar**.
* Con 5 miembros/día (la mayoría de los días) y ~26,5 MiB/miembro: **~132,5 MiB/día** de `apcp_sfc`
  en crudo, global. Sobre el rango completo que hace falta para la Decisión 021 (2000-01 a 2019-12,
  no sólo el hueco 2000-2006: el solapamiento 2006-2019 también hace falta para calibrar contra
  TIGGE) — **~20 años × 132,5 MiB/día ≈ 950 GB** si se descargara el archivo global completo sin
  recortar. Insostenible para bajar entero (compárese con TIGGE, que sí soporta recorte
  server-side vía el parámetro `area` de `cdsapi`, ver 7.2).
* **Cada archivo trae un `.grib2.idx` al lado** (JSON-lines con offset+longitud de cada mensaje
  GRIB2 dentro del archivo) — confirmado en el listado real del bucket. Esto habilita HTTP Range
  requests: se puede leer sólo los mensajes/pasos de tiempo que interesan sin bajar el archivo
  completo, patrón usado por herramientas como `herbie`/`kerchunk` sobre este mismo dataset. **No
  resuelve el recorte espacial** (el índice es por mensaje/step, no por sub-región de la grilla
  dentro de un mensaje) — igual hay que decodificar cada mensaje descargado y recortar al bounding
  box de la cuenca del lado del cliente, mismo patrón que `fc`/ECMWF Open Data (Decisión 013/022).
* Implica: el diseño de la descarga debe usar el `.idx` para bajar sólo los mensajes de `apcp_sfc`
  necesarios (no aplica acá porque el archivo ya es mono-variable, así que el `.idx` ahorra poco
  para esta variable puntual) y, más importante, **evaluar reducir cobertura antes de implementar**
  — por ejemplo bajar sólo `c00`+`p01` en vez de los 5 miembros, o preferir el bounding box exacto
  de la cuenca en vez de la grilla global vía una librería que soporte recorte remoto
  (`xarray`+`kerchunk` con index HTTP, a evaluar) — antes de comprometerse a los ~950 GB del cálculo
  ingenuo. Pendiente de decidir al implementar, no bloqueante para el resto de la Fase 4.

**Notebooks y rutas (implementado, Decisión 029)**

* Landing local en `notebooks_local/gefs_reforecast/` (mismo patrón de estado resumible + lock
  compartido que `ana_historic_backfill`/`inmet_backfill`): `common_gefs.py` (descarga, recorte,
  acumulación, empalme de tramos), `download_gefs_backfill.py` (backfill resumible por día,
  detecta miembros reales vía S3 en vez de asumir 5 fijos), `sync_to_databricks.py` (sube sólo
  el JSON recortado, nunca el `.grib2` crudo).
* DDL: `weather.raw.gefs_volume` y `weather.bronze.gefs_reforecast`, agregados a
  `notebooks/04_Silver/DDL_Silver_Gold.ipynb`.
* Bronze: `notebooks/02_Bronze/ETL_Bronze_GEFS.ipynb`, mismo patrón que `ETL_Bronze_ECMWF_CF.ipynb`
  (`member` string en vez de `number` int como parte de la clave de `MERGE`).
* `databricks.yml`: `ETL_Bronze_GEFS` corre en paralelo a la cadena de Silver dentro de
  `silver_gold_initial_load_v0` y `silver_gold_daily_incremental` (depende sólo de
  `DDL_Silver_Gold`/`Check_Bronze_Freshness` — GEFS todavía no tiene consumidor en Silver/Gold).
* Silver de GEFS (recorte al polígono real + calibración contra TIGGE) queda pendiente, tareas
  separadas de la Fase 4.

---

### 9.5. Pronóstico numérico de Brasil (CPTEC/INPE, INMET, ONS) — evaluado, no ingestado

* Investigación del 2026-08-26 (Decisión 032), motivada por la pregunta de si Brasil tiene un
  sistema de pronóstico numérico propio y gratuito con archivo histórico. **Sí lo tiene** (CPTEC/INPE),
  es abierto y sin registro, pero **ningún producto brasileño cubre el período 2000-2019** que
  necesita el dataset (Decisión 021): el archivo más largo arranca en 2020-07. Se documenta acá
  como fuente candidata para una comparación de habilidad, no como reemplazo de TIGGE/GEFS.
* Todo lo que sigue está **verificado contra los servidores reales el 2026-08-26** (listados,
  cabeceras HTTP y descargas parciales), no contra documentación.

**Acceso**

* Servidor real: `https://dataserver.cptec.inpe.br/dataserver_modelos/…` (HTTP abierto, sin
  registro, acepta `Range`). Las URLs históricas `ftp.cptec.inpe.br/modelos/tempo/…` redirigen
  (301) ahí, salvo BAM y los productos observados (MERGE/SAMeT), que siguen en `ftp.cptec.inpe.br`.
* WRF y Eta 8 km publican un `.inv` estilo `wgrib2` por archivo: con `Range` se baja sólo el
  mensaje de precipitación (`APCP`) — **verificado**: 874 KB en vez de 204 MB por paso horario del WRF.

**Modelos y archivo disponible (listado real)**

| Modelo | Resolución / dominio | Corridas / horizonte | Formato, tamaño | Archivo |
| --- | --- | --- | --- | --- |
| WRF 7 km (CPT-WRF, IC/BC FV3GFS) | 0,07°, 57,9°S–17,7°N, 90,7°W–19,4°W | 00Z, +180 h horario, 89 vars | GRIB2 ~204 MB/paso (+ `.inv`) | 2023-01-01 → hoy |
| Eta 8 km | 0,08°, Sudamérica | 00Z y 12Z, +264 h horario, 46 vars | GRIB2 ~99 MB/paso (+ `.inv`) | 2021-07 → hoy |
| Eta 40 km (+ variante `ons_40km`) | 0,4°, 83°W–25,8°W, 50,2°S–12,2°N | 00Z, +264 h horario, 64 vars | GRIB1 12 MB/paso | 2020-07-16 → hoy |
| BAM 20 km global (TQ0666L064) | 0,18° | 00Z, +264 h cada 6 h, 35 vars | GRIB2 ~99 MB/paso | recortes `pos`/`singleLevel` 2024-08 → hoy; `brutos` sólo 1 día |
| MONAN 10 km global (pre-operativo, base MPAS, supercomputador Jaci) | 0,1°, 18 niveles | 00Z +264 h / 12Z +120 h, cada 3 h | NetCDF **4,3 GB/paso** | 6 días de prueba 2024-04/05; continuo 2025-10-01 → hoy |
| Ensemble BAM (OENSMB09, 14+1 miembros) | 1° | +15 d | — | terminó 2020-04; CPTEC dejó de aportar a TIGGE ~2010 |

* `APCP` del WRF viene **acumulado desde el inicio de la corrida** (como `tp` de TIGGE); el del Eta
  8 km es **incremento horario** (como GEFS, gotcha de §9.4). Todos los dominios contienen la cuenca.
* Patrones de URL: `…/wrf/ams_07km/brutos/YYYY/MM/DD/00/WRF_cpt_07KM_YYYYMMDD00_YYYYMMDDHH.grib2`,
  `…/eta/ams_08km/brutos/YYYY/MM/DD/{00,12}/Eta_ams_08km_YYYYMMDDHH_YYYYMMDDHH.grib2`,
  `…/eta/ams_40km/brutos/YYYY/MM/DD/00/eta_40km_YYYYMMDD00+YYYYMMDDHH.grb`,
  `https://ftp.cptec.inpe.br/modelos/tempo/BAM/TQ0666L064/recortes/pos/YYYY/MM/DD/00/GPOSNMC…P.grib2`,
  `…/monan/10km/brutos/YYYY/MM/DD/{00,12}/MONAN_DIAG_G_POS_GFS_….nc`.

**Lo que no existe (verificado)**

* Ningún *reforecast* ni historia previa a 2020-07; ningún ensemble brasileño operativo público hoy.
* INMET (COSMO 7 km / 2,8 km): el aviso de 2021 prometía GRIB en `ftp://ftp.inmet.gov.br/cosmo` con
  3 meses de retención; el FTP **rechaza el login anónimo (`530`)** al 2026-08-26. Sólo imágenes en
  `vime.inmet.gov.br`. Contacto: `cgmn@inmet.gov.br`.
* ONS usa Eta 40 km + GEFS + ECMWF por cuenca en SINtegre (registro de agente del sector); el portal
  de datos abiertos sólo tiene precipitación observada discontinuada.
* No hay política de retención publicada para el dataserver: lo listado es lo que había ese día.

**Estado:** evaluado, **no ingestado** (Decisión 032). Si se reabre, la opción con historia útil es
Eta 40 km (2020→, ~3 GB/día entero) o WRF 7 km (2023→, sólo `APCP` por byte-range ≈ 160 MB/día) como
`forecast_source` adicional para comparar habilidad en `alta_frontera` — material de tesis, no reemplazo.

### 9.6. MERGE (CPTEC/INPE) — precipitación diaria observada en grilla

* Producto operativo de CPTEC/INPE que combina la estimación satelital **GPM-IMERG V07B** con
  pluviómetros (INMET, CEMADEN, ANA, PCDs, centros regionales) mediante el método de Rozante et al.
  (2010, 2020, 2024). Es **observación** (análisis), no pronóstico: no colisiona con la Decisión 021
  (que descarta ERA5 sólo *como pronóstico*). Ingestado por la Decisión 033.
* Estado: **Landing local + Landing diario en Databricks + Bronze + Silver + Gold implementados**
  (2026-08-26, Fase 9 del roadmap). Evaluación del archivo completo en `docs/cptec_obs_evaluation.md`.

**Origen y acceso (verificado 2026-08-26)**

* Diario: `https://ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/DAILY/{AAAA}/{MM}/MERGE_CPTEC_{AAAAMMDD}.grib2`
  (~360-520 KB). HTTP abierto, sin registro; conviene `User-Agent` de navegador como con INMET.
* Horario (no ingestado): `…/MERGE/GPM/HOURLY/{AAAA}/{MM}/{DD}/MERGE_CPTEC_{AAAAMMDDHH}.grib2`, desde 2009.
* Tarball de toda la base 1998-2024 (`…/DAILY/MERGE_NEW_1998_2024.tar.gz`, 4,1 GB, 2025-05-22) — no se
  usa: los archivos diarios individuales son la misma base y siguen el mismo patrón que el job diario.
* Documentación: `…/MERGE/GPM/MERGE_READ-ME.pdf` (2025-05-28), `Rozante_et.al.2010.pdf`,
  `Rozante_et.al.2020.pdf`, `Rozante.2024.pdf` (comparación IMERG V06B/V07B).

**Cobertura espacial**

* Grilla regular **0,1°**, 1001 × 924 puntos, lon −120,05 → −19,95 (servida en convención 0-360:
  239,95 → 339,95, requiere `normalize_longitude()`), lat −60,05 → 32,25. Cubre toda la cuenca.
* Recorte en Landing al bounding box de las 3 sub-cuencas (`compute_download_area()` con grilla 0,1° y
  1 celda de margen: N −26,1 / O −58,6 / S −32,0 / E −49,1) → **5.605 puntos por día**, sin NaN.
* Puntos por sub-cuenca (unión espacial de centros de celda, `grid_subcuenca.json`): `alta_frontera`
  566, `intermedia_paso_libres` 1.187, `baja_salto_grande` 482.
* Densidad de pluviómetros (`NEST`) en `alta_frontera` el 2026-08-25: 143 de 566 puntos con al menos
  un pluviómetro, 199 pluviómetros en total. Serie por año en `docs/cptec_obs_evaluation.md`.

**Cobertura temporal, ventana y latencia**

* Archivo diario desde **1998-01-02** hasta el día anterior, sin huecos detectados (conteo por año en
  `docs/cptec_obs_evaluation.md`).
* **Ventana diaria: acumulado de 12Z del día anterior a 12Z del día** (Rozante 2024; verificado
  sumando los horarios del 2026-07-22, día con 29 mm de media en la cuenca: correlación 0,95 contra
  la suma 13Z(D-1)→12Z(D) y 0,62 contra el día calendario UTC). El GRIB lleva `dataTime=1200`.
  **No coincide con el día de las estaciones ANA** (`rainfall_daily` agrupa por fecha de la medición):
  Gold publica ambas medidas y deja el desfase declarado en el diccionario de columnas.
* **Latencia: el archivo del día D aparece ~02:40 UTC de D+1** (medido 2026-08-21 → 26: 02:38-02:40
  UTC todos los días), consistente con IMERG *Late* (14 h tras 12Z). Llega antes del job diario de
  las 03:40 Montevideo (06:40 UTC) y de Gold (04:30).
* **Regeneración (importante para el diseño):** CPTEC reescribe el mes completo **en los primeros días
  del mes siguiente** (medido: 2026-07-15 → 2026-08-01; 2026-06-01 → 2026-07-01; 2026-04-01 → 2026-05-04;
  2026-01-01 → 2026-02-02; 2025-06-01 → 2025-07-01), presumiblemente con los pluviómetros completos.
  Además **toda la base fue reconstruida el 2025-05-04/06** (nueva base V07B). No se observó una
  tercera versión (IMERG *Final*, ~3,5 meses) — un archivo de 2026-04 seguía con fecha 2026-05-04 en
  agosto. Por eso: el registro guarda `source_last_modified`, Bronze actualiza cuando llega una
  versión más nueva y el job diario re-baja los últimos 45 días; Silver marca `es_preliminar`.

**Formato (verificado con ecCodes)**

* GRIB2, `centre=255`, grilla `regular_ll`, empaquetado **`grid_complex_spatial_differencing`**
  (template 5.3, 12 bits) con *missing value management* (sin bitmap): los faltantes vienen como
  `missingValue=9999`, hay que reemplazarlos explícitamente (bug encontrado en el test: sin esto todos
  los puntos parecían tener pluviómetro).
* **Dos mensajes por archivo:** el primero es la precipitación en kg/m² ≡ mm (CPTEC lo etiqueta como
  `rdp`, «Precipitation from radar», disciplina 0 / categoría 15 / parámetro 5); el segundo es **NEST**,
  la cantidad de pluviómetros por punto de grilla, mal etiquetado como `prmsl`. Se identifican por
  orden, no por nombre.
* En local se decodifica con ecCodes (`decode_merge_eccodes`); en Databricks serverless con
  **`pygrib`** (verificado en este workspace el 2026-08-26, `run 496772049564049`), porque
  `cfgrib`/`eccodes` abortan el kernel (Decisión 013).

**Notebooks, rutas y tablas**

* Landing local (histórico): `notebooks_local/cptec_obs/` — `common_cptec.py` (descarga, decodificación,
  recorte, aplanado vectorizado a Parquet), `download_cptec_obs.py` (backfill resumible, procesos en
  paralelo, lock compartido), `build_grid_subcuenca.py` (catálogo punto → sub-cuenca con geopandas),
  `sync_to_databricks.py` (sube Parquet por archivo o en ZIP a `staging/`), `evaluate_cptec_obs.py`
  (agregados locales + reporte).
* Landing diario en Databricks: `notebooks/00_Landing/CPTEC/Daily_CPTEC_Obs.ipynb` — baja D-1 y la
  ventana de 45 días, compara `Last-Modified` con el Parquet ya landeado y re-escribe sólo lo que cambió.
* Volume: `weather.raw.cptec_volume/merge/daily/MERGE_AAAA_MM_DD.parquet` (**Parquet, no JSON**: un
  archivo por día, ~12 KB recortado; ~130 MB para todo el archivo), `staging/` (ZIP del backfill local),
  `catalogo/grid_subcuenca.json`.
* Bronze: `weather.bronze.merge_precip_grid` (`ETL_Bronze_CPTEC_Obs.ipynb`, MERGE idempotente por
  `(fecha, latitude, longitude)` con `whenMatchedUpdateAll` si `source_last_modified` es más nuevo;
  `CLUSTER BY (fecha)`; descomprime `staging/` antes de leer).
* Silver: `weather.silver.precip_grid_daily` (`ETL_Silver_CPTEC_Grid_Daily.ipynb`): por `(fecha,
  subcuenca, fuente='merge')` media areal, máximo, puntos, `cobertura_pct`, `puntos_con_pluviometro`,
  `pluviometros`, `source_last_modified`, `es_preliminar` (= el archivo no fue tocado después de su
  publicación inicial de D+1, `source_last_modified < fecha + 2 días`; la regeneración mensual llega
  siempre después). Asignación por `weather.silver.grid_subcuenca` (`grilla='merge_0p1'`).
* Gold (`alta_frontera`): `lluvia_merge_alta_frontera_mm`, `_max_mm`, `_acum_3d_mm`, `_acum_7d_mm`,
  `_pluviometros`, `_cobertura_pct`, `_es_preliminar`.
* Jobs: `CPTEC_Obs_Daily_Incremental` (03:40 Montevideo: DDL → Landing → Bronze → Silver);
  `Silver_Gold_Initial_Load_v0` y `Silver_Gold_Daily_Incremental` incluyen `ETL_Silver_CPTEC_Grid_Daily`
  antes de Gold. **No entra en `Check_Bronze_Freshness`**: un corte del servidor de CPTEC no debe
  frenar Gold (la fila queda en `NULL` y `es_preliminar`/cobertura lo declaran).

**Campos clave (Bronze)**

* `fecha`: día D de la ventana 12Z(D-1)→12Z(D). `latitude`/`longitude`: centro de celda, −180/180,
  redondeado a 3 decimales (clave estable para el join con `grid_subcuenca`).
* `prec_mm`: precipitación acumulada (kg/m² ≡ mm). `nest`: pluviómetros en el punto (0 si ninguno).
* `source_file`, `source_last_modified` (Last-Modified HTTP, UTC), `source_api`
  (`cptec_merge_gpm_daily`), `extracted_at`, `ingestion_date`, `loaded_at`, `updated_at`.

**Limitaciones conocidas**

* La ventana 12Z-12Z desfasa el dato ~12 h respecto del día calendario de las estaciones; para
  acumulados de 3/7 días es irrelevante, para el día puntual hay que tenerlo presente al modelar.
* Los valores de los últimos ~30 días son preliminares hasta la regeneración mensual; en operación
  la inferencia siempre usa la versión preliminar (es la única que existe a D+1).
* Dependencia de un servidor externo sin SLA (`500`/`ECONNRESET` esporádicos observados): la descarga
  reintenta con backoff y el resto del pipeline no se bloquea si un día falta.

### 9.7. SAMeT (CPTEC/INPE) — temperatura diaria observada en grilla

* *South American Mapping of Temperature*: TMAX, TMIN y TMED diarias sobre Sudamérica combinando
  observaciones (SYNOP/GTS, METAR, PCDs, centros regionales, con control de calidad de CPTEC) con
  **ERA5 corregido por gradiente vertical de temperatura** (*lapse rate* estimado por región y
  estación del año; Rozante et al. 2021). Complemento en grilla de las estaciones INMET (§9.3).
  Ingestado por la Decisión 033; estado igual que MERGE (§9.6).

**Origen y acceso (verificado 2026-08-26)**

* `https://ftp.cptec.inpe.br/modelos/tempo/SAMeT/DAILY/{TMED|TMAX|TMIN}/{AAAA}/{MM}/SAMeT_CPTEC_{VAR}_{AAAAMMDD}.nc`
  (~1,7-1,8 MB cada uno, tres archivos por día). Climatología 2000-2020 en `…/SAMeT/CLIMATOLOGY/`.
* Documentación: `…/SAMeT/Read-me.pdf`, `…/SAMeT/Rozante_et_al_2021.pdf`.

**Cobertura espacial**

* Grilla regular **0,05°** (~5 km), 1001 × 1381 puntos, lon −83 → −33, lat −56 → 13. NetCDF4 (zlib),
  variables `tmed|tmax|tmin` y `nobs` (observaciones usadas por punto), `_FillValue = −9,99e8`,
  `time = minutes since AAAA-MM-DD 00:00`.
* Recorte en Landing (grilla 0,05°, 1 celda de margen: N −26,15 / O −58,55 / S −31,95 / E −49,2) →
  20.792 puntos, de los cuales **20.278 con dato**: los 514 NaN son océano en la esquina SE
  (lon −52 → −49,3, lat −31,85 → −29). **Las tres sub-cuencas quedan 100% cubiertas**: 2.269 /
  4.749 / 1.922 puntos.
* Observaciones dentro de `alta_frontera`: pocas (`nobs` = 8 el 2026-08-25, de 2.269 puntos) — el campo
  está sostenido sobre todo por ERA5 corregido; en los puntos con estación reproduce la estación
  (MAE 0,15 °C contra INMET, ver abajo).

**Cobertura temporal, ventana y latencia**

* Archivo diario desde **2000-01-01** hasta el día anterior (conteo por año en `docs/cptec_obs_evaluation.md`).
* **Ventana diaria: día calendario UTC (00Z-23Z)**, la misma que `temperature_daily`. Verificado
  contra INMET horario (Bronze) en 7 estaciones de `alta_frontera`, 2026-04-13 → 17: con la ventana
  00-23 UTC el error SAMeT − INMET es 0,15 °C (TMAX), 0,15 °C (TMED) y 0,22 °C (TMIN); con ventanas
  12Z-12Z sube a 1-2,6 °C.
* **Latencia:** TMED y TMAX del día D se publican ~03:02-03:08 UTC de D+1; **TMIN de D ya está a las
  ~17:06 UTC del mismo D** (la mínima ocurre de madrugada; el resto del día se completa con pronóstico).
  Las tres llegan antes del job de las 06:40 UTC.
* **Regeneración:** el READ-ME lo dice explícitamente — el producto diario se genera con
  observaciones + pronóstico numérico y **se regenera cuando llega ERA5** (retraso de 5 días);
  medido: reescritura a los **7 días** (TMED/TMAX 03:03 UTC de D+7, TMIN 17:08 UTC de D+7:
  2026-08-01 → 08-08, 06-01 → 06-08, 01-01 → 01-08). Toda la base se regeneró el 2022-06-01.
  Mismo mecanismo que MERGE: `source_last_modified`, re-descarga de 14 días en el job diario,
  `es_preliminar` (= modificado antes de D+7).

**Notebooks, rutas y tablas**

* Mismos scripts locales y mismo notebook de Landing que MERGE (§9.6): las tres variables se bajan y se
  aplanan juntas en un registro por punto (`SAMET_AAAA_MM_DD.parquet`, ~340 KB/día, ~3,3 GB en total).
* Volume: `weather.raw.cptec_volume/samet/daily/`. Bronze: `weather.bronze.samet_temp_grid`
  (`tmed_c`, `tmax_c`, `tmin_c`, `nobs_tmed`, `nobs_tmax`, `nobs_tmin`, mismos metadatos que MERGE).
* Silver: `weather.silver.temp_grid_daily` por `(fecha, subcuenca, fuente='samet')`: `temp_media_c`,
  `temp_max_c`, `temp_min_c` (**medias areales** de tmed/tmax/tmin), `temp_max_abs_c`/`temp_min_abs_c`
  (extremos de la grilla), `puntos_grilla`, `cobertura_pct`, `nobs_total`, `source_last_modified`,
  `es_preliminar`. `grid_subcuenca` con `grilla='samet_0p05'`.
* Gold (`alta_frontera`): `temp_samet_alta_frontera_media_c`, `_max_c`, `_min_c`, `_cobertura_pct`,
  `_es_preliminar`. Conviven con `temp_media_c`/`temp_min_c`/`temp_max_c` de INMET; no las reemplazan.

**Limitaciones conocidas**

* No es una observación pura: fuera de las estaciones es ERA5 corregido, y en los primeros 7 días es
  ERA5 + pronóstico. Para entrenar es una serie homogénea; para inferir a D+1 es la versión preliminar.
* La media areal de máximas/mínimas no es comparable con el `min`/`max` entre estaciones que publica
  el agregado INMET (extremos de la red): son definiciones distintas, no un sesgo.
* `nobs` dentro de la cuenca es bajo (una decena de estaciones); la calidad local depende de ERA5.

---

## 10. Reglas mínimas que debe cumplir una nueva fuente

Antes de incorporar una nueva fuente al pipeline, debe documentarse:

1. URL/endpoint de origen y método de autenticación.
2. Cobertura temporal y espacial mínima.
3. Frecuencia nativa y plan de agregación a diaria.
4. Tabla Bronze destino y clave lógica.
5. Reglas de deduplicación.
6. Notebook Landing y notebook Bronze.
7. Estado y limitaciones.

Toda fuente nueva implica una entrada en este documento antes de ejecutar el primer job.
