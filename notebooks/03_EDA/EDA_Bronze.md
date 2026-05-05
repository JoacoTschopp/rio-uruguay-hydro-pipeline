# 📊 EDA en capa Bronze

## 1. Objetivo

Se realiza un análisis exploratorio de datos (EDA) sobre las tablas en capa Bronze con el objetivo de:

* Evaluar la calidad de los datos antes de su transformación a Silver
* Detectar problemas de completitud, frecuencia y consistencia
* Definir criterios de selección de fuentes (especialmente estaciones de lluvia)
* Establecer reglas de agregación a nivel diario

Las tablas analizadas son:

* `weather.bronze.nivel_ana` → Nivel del río
* `weather.bronze.metar` → Temperaturas (aeropuertos)
* `weather.bronze.ana_rio_uruguai` → Lluvias

---

## 2. Cobertura temporal

### Nivel del río

* Rango: 1941-07-02 → 2026-03-16
* Alta cobertura histórica continua

### Temperatura (METAR)

* Rango: 1990-01-01 → 2026-03-16
* Buena cobertura temporal

### Lluvia (ANA)

* Rango: 1912-01-31 → 2026-03-16
* Cobertura aparente extensa, pero con muy baja densidad real

---

## 3. Frecuencia de medición

### Nivel del río

* Promedio: 1.14 registros/día

* Frecuencia dominante:

  * 1 registro/día (histórico)
  * 96–98 registros/día (≈ cada 15 min, datos recientes)

* Intervalos:

  * 1440 min (diario)
  * 15 min (alta frecuencia reciente)

👉 Existe mezcla de granularidades (histórico vs actual)

---

### Temperatura (METAR)

* Promedio: 83.7 registros/día

* Frecuencia dominante:

  * 96 registros/día (≈ cada 15 min)
  * variaciones entre 60–120 min

* Intervalos:

  * 60 min (principal)
  * presencia de duplicados (diff = 0)

👉 Frecuencia alta y relativamente consistente

---

### Lluvia (ANA)

* Promedio: 1662 registros/día (engañoso)

* Distribución:

  * mayoría de días con 1–3 registros
  * algunos días con miles de registros

* Intervalos:

  * predominan valores muy pequeños (0–3 min)

👉 Datos altamente irregulares y concentrados en pocos días

---

## 4. Datos faltantes (nivel diario)

### Nivel del río

* % faltantes: **1.24%**
* Cobertura adecuada para análisis temporal

---

### Temperatura

* % faltantes: **1.05%**
* Buena continuidad temporal

---

### Lluvia

* % faltantes: **99.78%**
* Solo 92 días con datos en todo el rango

👉 Dataset no usable directamente sin filtrado de estaciones

---

## 5. Análisis por estación (lluvia)

Estaciones objetivo evaluadas:

* 2751083
* 2751037
* 2752032
* 2751066
* 2753044

Resultado:

* Solo se encontró: **2752032**
* Total registros: 288

👉 El resto de estaciones no están presentes en la ingesta actual

---

## 6. Duplicados

### Lluvia

* Duplicados exactos: 0
* Claves duplicadas: 0

👉 Sin problemas de duplicación

---

### Nivel del río

* Duplicados exactos: 0
* Claves duplicadas: 60

Casos detectados:

* timestamps nulos
* duplicación en mediciones recientes

👉 Requiere tratamiento en Silver

---

### Temperatura (METAR)

* Duplicados exactos: 0
* Claves duplicadas: 1 (caso con NULL)

👉 Impacto mínimo

---

## 7. Outliers

### Nivel del río

* Q1: 160 | Q3: 270 | IQR: 110
* Rango válido: [-5, 435]
* Outliers: **6%**

Ejemplos:

* valores extremadamente altos (>1500)

👉 Probables eventos reales (crecidas)

---

### Lluvia

* No se pudo completar análisis por problemas de tipado (`string` con coma decimal)

👉 Requiere limpieza previa

---

### Temperatura

(No mostrado en resultados, pero esperado)

👉 Validar valores físicamente posibles en Silver

---

## 8. Problemas detectados

### 1. Inconsistencia de frecuencias

* Mezcla de datos diarios e intra-diarios
* Requiere normalización

---

### 2. Datos faltantes en lluvia

* Cobertura extremadamente baja
* Necesidad de selección de estaciones

---

### 3. Tipado incorrecto

* Variables numéricas almacenadas como `string`
* Problemas para análisis estadístico

---

### 4. Duplicados en nivel del río

* Casos puntuales pero relevantes

---

### 5. Outliers extremos

* Posibles eventos reales vs errores
* Requiere criterio de negocio

---

# 📌 Conclusiones y consideraciones para Silver

## 1. Normalización temporal obligatoria

Todos los datasets deben transformarse a **frecuencia diaria**, dado que:

* Las fuentes tienen distintas granularidades
* La hipótesis de análisis es diaria

---

## 2. Reglas de agregación por variable

* **Nivel del río**

  * media diaria
  * máximo diario (eventos extremos)

* **Temperatura**

  * promedio diario
  * mínimo / máximo diario

* **Lluvia**

  * acumulado diario

---

## 3. Selección de estaciones (crítico)

* No todas las estaciones son utilizables
* Se deben elegir aquellas con:

  * mayor completitud temporal
  * menor cantidad de faltantes

---

## 4. Tratamiento de calidad de datos

* Eliminar duplicados por clave lógica
* Convertir tipos (`string → double`)
* Filtrar valores físicamente imposibles (temperatura)

---

## 5. Manejo de outliers

* **No eliminar automáticamente**
* Diferenciar:

  * eventos reales (válidos)
  * errores de medición

---

## 6. Definición de calidad por día

Dado que hay alta variabilidad en frecuencia:

* No todos los días tienen la misma calidad
* Se debe considerar:

  * cantidad de registros por día
  * consistencia intra-día