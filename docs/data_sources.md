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
| Pronósticos (precip/temp)       | Pronóstico    | No ingestada       | —                               | Diaria/grilla     | Features futuras   |
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
* Landing histórica: `notebooks/00_Landing/ANA_Hidrico/Historic_ANA.ipynb`.
* Bronze diaria: `notebooks/02_Bronze/ETL_Bronze_ANA.ipynb`.
* Bronze histórica: `notebooks/02_Bronze/ETL_Bronze_ANA_Histo.ipynb`.

### 3.5. Rutas de almacenamiento

* Landing daily: `/Volumes/weather/raw/ana_volume/json/` (archivos `ANA_YYYY_MM_DD.json`).
* Landing histórico: `/Volumes/weather/raw/ana_volume/json/` (archivos `ANA_*.json`).

### 3.6. Job Databricks

* `All_Estacoes_ANA_Daily`: `Daily_ANA -> ETL_Bronze_ANA`. Ejecución serverless.

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

## 6. Fuentes candidatas no ingestadas

### 6.1. Pronósticos meteorológicos

* Variables: precipitación pronosticada, temperatura pronosticada.
* Resolución espacial sugerida: 0,25° x 0,25°.
* Estado: `No ingestada`.
* Riesgo: pronósticos históricos previos a los últimos meses pueden ser difíciles de obtener.
* Decisión pendiente: si se usan solo en modo incremental o si se integran al histórico (ver `decisions.md` Decisión 002).

### 6.2. Evaporación

* Variables: evaporación diaria, acumulada.
* Estado: `No ingestada`.
* Postergada para `training_dataset_v1`.

### 6.3. Lluvias y niveles Argentina

* Posibles proveedores: SNIH (Sistema Nacional de Información Hídrica), INA (Instituto Nacional del Agua).
* Estado: `No ingestada`.
* Importancia para el punto crítico Salto Grande.

### 6.4. Temperatura grandes ciudades Brasil

* Complemento o reemplazo de METAR aeropuertos.
* Posibles proveedores: INMET (Instituto Nacional de Meteorologia).
* Estado: `No ingestada`.

---

## 7. Reglas mínimas que debe cumplir una nueva fuente

Antes de incorporar una nueva fuente al pipeline, debe documentarse:

1. URL/endpoint de origen y método de autenticación.
2. Cobertura temporal y espacial mínima.
3. Frecuencia nativa y plan de agregación a diaria.
4. Tabla Bronze destino y clave lógica.
5. Reglas de deduplicación.
6. Notebook Landing y notebook Bronze.
7. Estado y limitaciones.

Toda fuente nueva implica una entrada en este documento antes de ejecutar el primer job.
