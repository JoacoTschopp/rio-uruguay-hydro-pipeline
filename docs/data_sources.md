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
* **No afecta caudal/nivel**: ese agregado depende de `weather.silver.river_discharge_daily`
  (acotado a estaciones con curva de aforo vigente), no de `estacion_subcuenca`.

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
* Estado: **Investigada contra la fuente real (2026-08-22), no ingestada todavía.** Documentado acá
  antes de escribir código (regla de la sección 10).

**Catálogo de estaciones (verificado)**

* Endpoint: `GET https://apitempo.inmet.gov.br/estacoes/T` (automáticas) / `.../estacoes/M`
  (manuales/convencionales). Sin autenticación, pero **requiere un header `User-Agent` de
  navegador**: con el `User-Agent` por defecto de `curl`/`requests` el servidor corta la conexión
  TLS (`Connection reset`) antes de responder; con un `User-Agent` de Chrome responde `200` normal.
* Devuelve JSON con 674 estaciones automáticas a nivel nacional: `CD_ESTACAO`, `DC_NOME`,
  `SG_ESTADO`, `VL_LATITUDE`, `VL_LONGITUDE`, `VL_ALTITUDE`, `DT_INICIO_OPERACAO`, `CD_SITUACAO`
  (`Operante`/`Pane`).
* Filtrando a un bounding box aproximado de la cuenca alta (lat -29,5 a -26,5, lon -54,5 a -49,5):
  **42 estaciones automáticas**, la mayoría operativas desde 2001-2019 (la más antigua, `A805`
  Santo Augusto, RS, desde 2001-12) más una decena nuevas abiertas entre 2025 y 2026.

**Histórico masivo (verificado, mecanismo recomendado para backfill)**

* `GET https://portal.inmet.gov.br/uploads/dadoshistoricos/{AAAA}.zip` — un ZIP por año calendario,
  **2000 a 2026 confirmados existentes** (HEAD 200 en ambos extremos probados). Sin autenticación,
  mismo requisito de `User-Agent` de navegador.
* Cada ZIP (~100 MB, probado con 2023: 107 MB, 567 archivos) trae **un CSV por estación,
  nacional** (todos los tipos), no sólo la cuenca — hay que filtrar client-side por los 42 códigos
  de estación de la cuenca. Confirmado: las 22 estaciones de la cuenca operativas en 2023 tienen su
  CSV en el ZIP de ese año.
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
* Alternativa para incrementalidad mientras no se identifique el endpoint vivo actual: re-descargar
  periódicamente el ZIP del año en curso (los headers `Last-Modified`/`ETag`/`Content-Length`
  permiten detectar con un `HEAD` si cambió antes de bajar los ~100 MB completos).

**Diseño pendiente (no implementado esta sesión)**

* Landing local (mismo patrón que `notebooks_local/ana_historic_backfill/`): descargar los ZIP
  2000-2026, extraer sólo los CSV de los 42 códigos de estación de la cuenca, subir al Volume.
* Tabla Bronze destino: `weather.bronze.inmet` (a definir DDL), clave lógica
  `(codigo_estacao, data_hora_medicao)`.
* Unificación con METAR en `weather.silver.temperature_daily`: agregación horaria → diaria
  (min/max/avg) igual que METAR, con columna de trazabilidad de origen por registro (`fuente`:
  `metar` | `inmet`) y regla de prioridad a definir (INMET más cercano al punto de predicción vs.
  METAR más estable/limpio).
* Investigar el endpoint vivo actual antes de comprometerse a la estrategia de re-descarga
  periódica del ZIP.

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
