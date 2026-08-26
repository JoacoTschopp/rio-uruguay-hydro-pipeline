# Evaluación local de MERGE y SAMeT (CPTEC/INPE)

Generado por `notebooks_local/cptec_obs/evaluate_cptec_obs.py` el 2026-08-26, a partir del archivo completo descargado en local (`output_parquet/`) y de `grid_subcuenca.json`. Los agregados por sub-cuenca replican la regla de `ETL_Silver_CPTEC_Grid_Daily.ipynb` (media areal de los puntos de grilla dentro del polígono). Contexto y decisiones: `docs/data_sources.md` §9.6/§9.7 y Decisión 033.

## 1. Cobertura temporal

### MERGE (precipitación, desde 1998-01-02)

| Año | Días esperados | Días con dato (MERGE) | Faltantes |
| --- | --- | --- | --- |
| 1998 | 364 | 364 | 0 |
| 1999 | 365 | 365 | 0 |
| 2000 | 366 | 366 | 0 |
| 2001 | 365 | 365 | 0 |
| 2002 | 365 | 365 | 0 |
| 2003 | 365 | 365 | 0 |
| 2004 | 366 | 366 | 0 |
| 2005 | 365 | 365 | 0 |
| 2006 | 365 | 365 | 0 |
| 2007 | 365 | 365 | 0 |
| 2008 | 366 | 366 | 0 |
| 2009 | 365 | 365 | 0 |
| 2010 | 365 | 365 | 0 |
| 2011 | 365 | 365 | 0 |
| 2012 | 366 | 366 | 0 |
| 2013 | 365 | 365 | 0 |
| 2014 | 365 | 365 | 0 |
| 2015 | 365 | 365 | 0 |
| 2016 | 366 | 366 | 0 |
| 2017 | 365 | 365 | 0 |
| 2018 | 365 | 365 | 0 |
| 2019 | 365 | 365 | 0 |
| 2020 | 366 | 366 | 0 |
| 2021 | 365 | 365 | 0 |
| 2022 | 365 | 365 | 0 |
| 2023 | 365 | 365 | 0 |
| 2024 | 366 | 366 | 0 |
| 2025 | 365 | 365 | 0 |
| 2026 | 237 | 237 | 0 |

Total de días faltantes 1998-01-02 → 2026-08-25: **0**

### SAMeT (temperatura, desde 2000-01-01)

| Año | Días esperados | Días con dato (SAMeT) | Faltantes |
| --- | --- | --- | --- |
| 2000 | 366 | 366 | 0 |
| 2001 | 365 | 365 | 0 |
| 2002 | 365 | 365 | 0 |
| 2003 | 365 | 365 | 0 |
| 2004 | 366 | 366 | 0 |
| 2005 | 365 | 365 | 0 |
| 2006 | 365 | 365 | 0 |
| 2007 | 365 | 365 | 0 |
| 2008 | 366 | 366 | 0 |
| 2009 | 365 | 365 | 0 |
| 2010 | 365 | 365 | 0 |
| 2011 | 365 | 365 | 0 |
| 2012 | 366 | 366 | 0 |
| 2013 | 365 | 365 | 0 |
| 2014 | 365 | 365 | 0 |
| 2015 | 365 | 365 | 0 |
| 2016 | 366 | 366 | 0 |
| 2017 | 365 | 365 | 0 |
| 2018 | 365 | 365 | 0 |
| 2019 | 365 | 365 | 0 |
| 2020 | 366 | 366 | 0 |
| 2021 | 365 | 365 | 0 |
| 2022 | 365 | 365 | 0 |
| 2023 | 365 | 365 | 0 |
| 2024 | 366 | 366 | 0 |
| 2025 | 365 | 365 | 0 |
| 2026 | 237 | 237 | 0 |

Total de días faltantes 2000-01-01 → 2026-08-25: **0**

## 2. Densidad de observaciones dentro de `alta_frontera`

MERGE: `pluviometros` = suma de NEST (pluviómetros por punto de grilla) sobre los puntos de la sub-cuenca, promedio diario del año; `puntos_con_pluviometro` = puntos de grilla con al menos un pluviómetro (de 566 puntos de 0,1°). SAMeT: `nobs_tmed` = observaciones de temperatura usadas por día (de 2.269 puntos de 0,05°).

| Año | lluvia_anual_mm | pluviometros_prom_dia | puntos_con_pluviometro_prom | cobertura_pct_min |
| --- | --- | --- | --- | --- |
| 1998 | 2221.0 | 57.6 | 53.9 | 1.0 |
| 1999 | 1402.9 | 53.3 | 51.4 | 1.0 |
| 2000 | 1770.2 | 53.7 | 50.2 | 1.0 |
| 2001 | 1823.7 | 77.5 | 59.8 | 1.0 |
| 2002 | 1835.9 | 69.0 | 65.7 | 1.0 |
| 2003 | 1460.8 | 73.5 | 69.8 | 1.0 |
| 2004 | 1368.2 | 72.4 | 68.2 | 1.0 |
| 2005 | 1784.1 | 75.0 | 70.4 | 1.0 |
| 2006 | 1277.2 | 74.2 | 70.1 | 1.0 |
| 2007 | 1728.1 | 65.2 | 61.1 | 1.0 |
| 2008 | 1469.9 | 88.4 | 79.8 | 1.0 |
| 2009 | 1776.0 | 60.6 | 57.7 | 1.0 |
| 2010 | 1790.7 | 76.0 | 72.0 | 1.0 |
| 2011 | 1937.7 | 81.3 | 76.2 | 1.0 |
| 2012 | 1279.3 | 83.5 | 76.5 | 1.0 |
| 2013 | 1768.8 | 86.6 | 75.9 | 1.0 |
| 2014 | 2060.3 | 95.5 | 82.4 | 1.0 |
| 2015 | 2115.6 | 121.4 | 99.7 | 1.0 |
| 2016 | 1618.9 | 141.7 | 115.8 | 1.0 |
| 2017 | 1595.3 | 134.7 | 111.0 | 1.0 |
| 2018 | 1529.1 | 136.1 | 110.5 | 1.0 |
| 2019 | 1467.3 | 132.7 | 110.0 | 1.0 |
| 2020 | 1267.9 | 135.0 | 113.5 | 1.0 |
| 2021 | 1236.0 | 143.5 | 119.2 | 1.0 |
| 2022 | 1773.3 | 154.1 | 119.5 | 1.0 |
| 2023 | 2059.8 | 156.4 | 119.8 | 1.0 |
| 2024 | 1659.0 | 97.6 | 82.4 | 1.0 |
| 2025 | 1345.6 | 139.6 | 108.0 | 1.0 |
| 2026 | 878.3 | 166.1 | 124.3 | 1.0 |

| Año | tmed_anual_c | tmax_anual_c | tmin_anual_c | nobs_tmed_prom_dia | cobertura_pct_min |
| --- | --- | --- | --- | --- | --- |
| 2000 | 16.5 | 22.7 | 12.2 | 5.9 | 1.0 |
| 2001 | 17.6 | 23.6 | 13.6 | 3.5 | 1.0 |
| 2002 | 17.3 | 23.3 | 13.6 | 4.9 | 1.0 |
| 2003 | 16.8 | 23.4 | 12.5 | 4.7 | 1.0 |
| 2004 | 16.5 | 22.9 | 12.2 | 4.6 | 1.0 |
| 2005 | 17.0 | 23.4 | 12.8 | 5.2 | 1.0 |
| 2006 | 17.1 | 23.8 | 12.8 | 5.7 | 1.0 |
| 2007 | 17.1 | 23.3 | 12.9 | 5.9 | 1.0 |
| 2008 | 16.5 | 22.6 | 12.1 | 6.0 | 1.0 |
| 2009 | 16.9 | 23.0 | 12.5 | 8.7 | 1.0 |
| 2010 | 16.6 | 22.4 | 12.5 | 11.4 | 1.0 |
| 2011 | 16.4 | 22.3 | 12.3 | 14.8 | 1.0 |
| 2012 | 17.4 | 23.6 | 13.0 | 13.0 | 1.0 |
| 2013 | 16.3 | 22.2 | 12.1 | 14.8 | 1.0 |
| 2014 | 17.3 | 23.1 | 13.3 | 13.6 | 1.0 |
| 2015 | 17.4 | 23.1 | 13.7 | 15.9 | 1.0 |
| 2016 | 16.5 | 22.4 | 12.4 | 15.8 | 1.0 |
| 2017 | 17.3 | 23.4 | 13.2 | 12.8 | 1.0 |
| 2018 | 16.9 | 22.9 | 12.9 | 11.8 | 1.0 |
| 2019 | 17.6 | 23.5 | 13.5 | 10.5 | 1.0 |
| 2020 | 17.1 | 23.6 | 12.5 | 10.1 | 1.0 |
| 2021 | 16.8 | 22.8 | 12.5 | 7.9 | 1.0 |
| 2022 | 16.5 | 22.1 | 12.5 | 9.3 | 1.0 |
| 2023 | 17.4 | 22.9 | 13.6 | 19.6 | 1.0 |
| 2024 | 17.8 | 23.2 | 14.0 | 23.1 | 1.0 |
| 2025 | 17.0 | 22.4 | 13.0 | 14.4 | 1.0 |
| 2026 | 16.8 | 22.1 | 12.9 | 7.4 | 1.0 |

## 3. Climatología mensual (`alta_frontera`, todo el período)

| Mes | Lluvia media mensual MERGE (mm) | Tmed SAMeT (°C) | Tmax SAMeT (°C) | Tmin SAMeT (°C) |
| --- | --- | --- | --- | --- |
| 01 | 153 | 21.1 | 27.1 | 16.9 |
| 02 | 131 | 21.0 | 27.0 | 16.8 |
| 03 | 119 | 20.0 | 26.2 | 15.9 |
| 04 | 117 | 17.5 | 23.5 | 13.5 |
| 05 | 134 | 13.9 | 19.5 | 10.2 |
| 06 | 136 | 12.7 | 18.1 | 9.0 |
| 07 | 126 | 12.3 | 18.3 | 8.2 |
| 08 | 107 | 13.8 | 20.3 | 9.4 |
| 09 | 158 | 15.4 | 21.4 | 11.1 |
| 10 | 201 | 17.3 | 23.1 | 13.1 |
| 11 | 131 | 18.8 | 25.0 | 14.2 |
| 12 | 141 | 20.5 | 26.6 | 16.0 |
| **Año** | **1653** | 17.0 | 23.0 | 12.9 |

## 4. Comparación contra los agregados por estación del snapshot de Gold

**Lluvia — `alta_frontera`** (9698 días en común, 2000-01-01 → 2026-08-23). Media diaria estaciones ANA (suma/estaciones): 5.34 mm; MERGE media areal: 4.49 mm.

| Desfase MERGE vs estaciones | Correlación diaria | Correlación mensual |
| --- | --- | --- |
| MERGE(D+1) vs estaciones(D) | 0.425 | 0.883 |
| sin desfase (mismo día) | 0.895 | 0.898 |
| MERGE(D-1) vs estaciones(D) | 0.246 | 0.885 |

| Año | Lluvia anual estaciones (mm) | Lluvia anual MERGE (mm) | Cociente MERGE/estaciones |
| --- | --- | --- | --- |
| 2000 | 1928 | 1770 | 0.92 |
| 2001 | 1968 | 1824 | 0.93 |
| 2002 | 1955 | 1836 | 0.94 |
| 2003 | 1582 | 1461 | 0.92 |
| 2004 | 1548 | 1368 | 0.88 |
| 2005 | 1956 | 1784 | 0.91 |
| 2006 | 1411 | 1277 | 0.91 |
| 2007 | 1968 | 1728 | 0.88 |
| 2008 | 1686 | 1470 | 0.87 |
| 2009 | 2064 | 1776 | 0.86 |
| 2010 | 2042 | 1791 | 0.88 |
| 2011 | 2209 | 1938 | 0.88 |
| 2012 | 1498 | 1279 | 0.85 |
| 2013 | 1987 | 1769 | 0.89 |
| 2014 | 2294 | 2060 | 0.90 |
| 2015 | 2322 | 2116 | 0.91 |
| 2016 | 1757 | 1619 | 0.92 |
| 2017 | 1823 | 1595 | 0.88 |
| 2018 | 1684 | 1529 | 0.91 |
| 2019 | 1663 | 1467 | 0.88 |
| 2020 | 1445 | 1268 | 0.88 |
| 2021 | 1346 | 1236 | 0.92 |
| 2022 | 2091 | 1773 | 0.85 |
| 2023 | 2905 | 2060 | 0.71 |
| 2024 | 3422 | 1659 | 0.48 |
| 2025 | 2335 | 1346 | 0.58 |

_Nota: el cociente cae de ~0,9 (2000-2022) a 0,71/0,48/0,58 en 2023-2025. No es un artefacto de cobertura de estaciones (`lluvia_agregado_alta_frontera_cobertura_pct` sube de 0,13 a 0,20 en el mismo período, no baja): el promedio por estación normalizado por conteo también se dispara. Abre la pregunta de si alguna estación ANA nueva tiene un error de unidades/coma decimal en 2023-2025 — pendiente de investigar en la Fase 3, no bloquea esta fase._

**Temperatura — `alta_frontera`** (7184 días en común, 2006-11-27 → 2026-07-31; estaciones INMET vs SAMeT media areal).

| Variable | Media estaciones (°C) | Media SAMeT (°C) | Sesgo SAMeT−estaciones | Correlación diaria |
| --- | --- | --- | --- | --- |
| media | 17.06 | 17.01 | -0.05 | 0.991 |
| máxima | 24.88 | 22.90 | -1.98 | 0.971 |
| mínima | 10.07 | 12.90 | +2.83 | 0.951 |

_Nota: el agregado por estaciones usa `min`/`max` entre estaciones para mínima/máxima (extremos de la red) mientras que SAMeT es la media areal de la mínima/máxima de cada punto; el sesgo de esas dos filas es en parte diferencia de definición, no error._

## 5. Estado de revisión de los archivos (regeneración de CPTEC)

* **MERGE** (regenerado en los primeros días del mes siguiente): `source_last_modified` − `fecha` en los últimos 60 días: mínimo 1 días, mediana 3 días, máximo 31 días. Fecha de modificación más antigua en todo el archivo: 2025-05-03; más reciente: 2026-08-26.
* **SAMeT** (regenerado ~7 días después con ERA5): `source_last_modified` − `fecha` en los últimos 60 días: mínimo 1 días, mediana 7 días, máximo 7 días. Fecha de modificación más antigua en todo el archivo: 2022-06-01; más reciente: 2026-08-26.
