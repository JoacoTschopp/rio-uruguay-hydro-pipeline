# Plan de trabajo de los manuscritos

Versión 2026-09-16. Es una **propuesta**. Todo lo marcado **[AUTOR]** lo decide Joaquín; la estructura, el encuadre y el contenido no se cierran sin su revisión.

## 1. Entregables

| # | Documento | Carpeta | Estado |
| --- | --- | --- | --- |
| 1 | Plan de tesis | `plan-de-tesis/` | Esqueleto que compila. La estructura es provisoria hasta tener el reglamento. |
| 2 | Tesis de Maestría | `tesis/` | Esqueleto que compila. Sigue los capítulos del TFI validado, con "Área de estudio y datos" como capítulo aparte. |

## 2. Punto de partida (inventario de ramas del 2026-09-16)

### 2.1 Material y dónde está

| Material | Rama / lugar | Madurez para escribir |
| --- | --- | --- |
| Formato validado (TFI 2025: `.tex`, PDF, imágenes) | `feature/rio-search`; copiado a `referencia/` | Listo |
| Borradores de proyecto y tesis (enfoque BiLSTM) | `feature/rio-search`; copiados a `referencia/` | Superados: solo antecedente de redacción |
| Biblioteca: 15 referencias verificadas con `rol`, 5 notas | `research/` (`main-predic`) | Base del marco teórico, incompleta |
| Biblioteca de la UI: 3 referencias, notas vacías | `feature/rio-search:rio_search/research/` | Otro esquema (ver §6) |
| Fuentes, capas, contrato y calidad del dataset | `docs/` (`main-predic`) | Borrador avanzado, con partes desactualizadas |
| Protocolo de búsqueda, G-RAL y modulador de régimen | `docs/protocolo_busqueda_modelos.md`, `docs/funcion_ganancia_regimen.html`, `docs/referencia_funcion_y_dataset.html` | Borrador avanzado |
| Catálogo de celdas y ledger | `rio_search/experiments/matrix.yaml`, `rio_search/results/` | Parcial |
| Resultados de la campaña `d303` y `dm.py` | `feature/fase-estrategias` (sin mergear a `main-predic`) | Parcial |
| Capas SIG: sub-cuencas y estaciones ANA | `SIG/` | Listas para el mapa del área |
| Proyecto QGIS (DEM, acumulación de flujo, cuencas) | Fuera del repo: `proyectos_maestria/TESIS/QGIS-CUENCA/` | A confirmar [AUTOR] |
| TP1 de Tesis II (objetivos, equipo de dirección) y TPs de Tesis I | Fuera del repo: `proyectos_maestria/Latex_Project/Backup_download_Overleef/` | A confirmar [AUTOR] |

### 2.2 Cómo formula hoy el repo el problema

- **Objetivo del modelado**, según `docs/protocolo_busqueda_modelos.md` §1: predecir el caudal en `ana_74100000` (Iraí), en t+1…t+7 y t+14, con `weather.gold.training_dataset_v0`. No se busca "el mejor modelo" sino **la metodología** que mejor pronostica bajo una métrica asimétrica por régimen, y dejar escrito por qué.
- **Alcance**: sub-cuenca `alta_frontera`, datos diarios desde 2000 y un solo target, el caudal.
- **Aporte candidato**: G-RAL, un expectil sobre log-caudal cuyo τ(t) fija el estado de la cuenca. El propio `funcion_ganancia_regimen.html` §09 advierte que antes de llamarlo "novedoso" hace falta una búsqueda bibliográfica sistemática.
- **No hay pregunta de investigación ni hipótesis escritas.** Es lo primero que hay que redactar, y lo decide el autor.
- **Hay formulaciones viejas que contradicen la actual** y no deben filtrarse al texto:
  - `README.md` raíz: temperaturas de ciudades de Brasil y modelo estrella del bootcamp;
  - `docs/dataset_definition.md`: target nivel, dos puntos de predicción;
  - los borradores BiLSTM.

### 2.3 Lectura preliminar de resultados (VAL, campaña `d303-a6262712`)

Sirve para planificar. **No se cita** hasta que cierre la campaña.

- **Ancla** (MLP con pérdida G-RAL, B0.06): 0,4948 ± 0,0098, con 5 semillas. Mejora el RMSE de la persistencia en 7,6 %.
- **Expectil con τ constante** (B1.06): 0,4871, **empata** con el ancla. Todavía no se distingue del ruido el aporte de que τ varíe día a día.
- **Diebold-Mariano** (B11.03, pérdida ψτ):
  - el ancla le gana a `mse` (p = 0,034) y a `expectile_raw` (p = 0,0003);
  - `mse_log` le gana al ancla (p = 0,021);
  - contra persistencia no hay diferencia significativa (p = 0,16).
- **Modulador** (B8.05): con pronóstico ECMWF real rinde casi igual que con el oráculo, y los dos rinden mejor que con solo lluvia antecedente.
- **Walk-forward** (B6.02): no hay ganador entre ventana expandible y deslizante.

**Consecuencia para la tesis:** la narrativa depende de cómo cierre la búsqueda. El texto tiene que poder sostener un resultado neutro o negativo sobre el modulador, que también es un hallazgo. El encuadre lo decide el autor.

## 3. Reglas de trabajo

1. **Carpeta propia.** Esta rama escribe solo en `manuscritos/`. Puede sumar entradas nuevas a `research/`, con acuerdo del autor. Nunca borra ni modifica nada de otras carpetas o ramas.
2. **Trazabilidad.** Cada número del texto remite a una campaña, una celda y un commit. Cada figura o tabla generada lleva su fuente en la primera línea.
3. **VAL y TEST.** Hasta la celda B11.02 se reporta solo VAL. Hay que declarar que TEST ya se miró antes del protocolo (`funcion_ganancia_regimen.html` §08).
4. **Un solo snapshot.** Los resultados citados salen de una sola campaña cerrada. Lo que solo existe en `d299` (B1, B2, B8.01–03, B9) se vuelve a correr o se presenta como histórico.
5. **Glosario antes de la metodología.** Los términos se fijan una vez [AUTOR]. Por ejemplo: "modulador de régimen" y no "portón"; G-RAL es un error que se minimiza, no una "ganancia".
6. **Sin "Decisión NNN" en el texto** (ver §6.2).
7. **Ciclo de revisión.** Yo redacto un borrador, el autor lo revisa y después se integra. Ningún capítulo se da por cerrado sin revisión. Los hitos pasan por el director.
8. **Citas con respaldo.** Cada cita tiene `verificado: true` en el catálogo. Lo que se afirma de un paper sale de su lectura (PDF en `research/documents/` y nota), no de memoria.

## 4. Fases

### F0: Montaje. Hecha el 2026-09-16

**Qué se hizo:**
- la estructura de `manuscritos/`;
- `tesisuba.cls`, derivada del TFI validado;
- la bibliografía generada desde `research/catalog/`;
- el script de compilación;
- el material de referencia traído de `feature/rio-search`.

**Verificado:**
- los dos PDF compilan con `latexmk` desde PowerShell;
- un documento de prueba resolvió 5 citas APA, con acentos en autores y títulos, sin citas indefinidas;
- la portada con etapa, director y codirector entra en una hoja.

### F1: Insumos y encuadre. **Parcialmente destrabada el 2026-09-18**

Resuelto por los documentos que dejó el autor en `info-institucional/`:

- **Estructura y forma:** los instructivos y, sobre todo, el plan de tesis aprobado que está en `info-institucional/plan-tesis/Ejemplos/`. De ahí sale la estructura de F2.
- **Director:** Gustavo Denicolay Pacheco, el mismo que dirigió el plan de ejemplo.
- **Destinatario de la nota de elevación:** el director académico de la maestría.

**Encuadre, fijado por el autor el 2026-09-18.** Es la decisión que más ordena el trabajo, y conviene no perderla:

> *"Yo no busco un modelo/metodología que responda a múltiples cuencas, yo busco implementar el modelo óptimo para esta cuenca. Y para demostrar que es igual o mejor, o de hecho que un método/modelo es el óptimo y el que más se ajusta a la cuenca en estudio, es necesario implementar propuestas actuales y ver cómo performan en esta cuenca."*

Consecuencias, que ya están aplicadas en el plan:

- El núcleo del trabajo es una **comparación sistemática sobre una sola cuenca**, no la propuesta de un método nuevo. Lo que se defiende es *cuál* rinde mejor acá y con qué evidencia.
- La objeción de `kratzert-2024-nunca-una-sola-cuenca` **se responde midiéndola, no argumentándola**: el modelo preentrenado sobre un conjunto regional y ajustado localmente entra como un candidato más.
- La **pérdida asimétrica deja de ser el aporte central** y pasa a ser una hipótesis que se pone a prueba sobre el método ganador (objetivo específico 6). Si se confirma, el aporte es doble; si no, el trabajo igual responde su pregunta. **Esto hay que validarlo con el director.**
- Lo que hace defendible la comparación es evaluar con forzantes **pronosticadas**, no observadas, porque es lo único que hay en operación.

Título provisorio, en la dirección que dio el autor: *"Método de proyección del caudal de la cuenca alta del río Uruguay en territorio de Brasil"*. El autor avisó que no lo tiene cerrado.

Sigue pendiente del autor:

- Grado académico, filiación y correo del director, y los datos completos del codirector.
- Fechas (elevación del plan, objetivo de la tesis, ritmo de revisión).
- Cierre del título y validación del encuadre con el director.

**Cierre:** encuadre, objetivos y título aprobados por el autor y por la dirección.

### F2: Plan de tesis

Estructura calcada del plan aprobado de `info-institucional/plan-tesis/Ejemplos/`, que son 4 capítulos en ~10 páginas. **El plan es corto: no es una versión reducida de la tesis.**

0. **Dirección de la tesis:** bloque administrativo con grado académico, filiación y correo del director y del codirector. No está en el ejemplo, pero lo pide el punto 2.b del instructivo.
1. **Introducción:** 1.1 descripción del problema y motivación, 1.2 trabajos previos (el estado del arte, §5), 1.3 objetivos.
2. **Materiales y Métodos:** 2.1 base técnica (pérdidas asimétricas), 2.2 métodos, que es donde el ejemplo enuncia su hipótesis, y 2.3 datos.
3. **Experimentos preliminares y resultados:** la campaña `d303-a6262712`, con una tabla chica y los experimentos siguientes. El ejemplo hace exactamente eso.
4. **Tiempo estimado de trabajo:** una tabla de etapa / tarea / duración. Sin fechas de calendario.

El ejemplo **no** lleva resumen ni palabras clave, así que el plan tampoco.

Aparte del documento, la presentación pide dos notas (modelos en `info-institucional/plan-tesis/`, ejemplos firmados en `Ejemplos/`): la del estudiante elevando el plan, y la de aval del director y del codirector. Se suben en PDF al formulario de la secretaría, junto con los CV.

**Cierre:** compila sin avisos, todas las citas verificadas, revisión del autor y versión para el director.

### F3: Tesis, capítulos que no dependen de resultados

- **Cap. 3, Área de estudio y datos.** Necesita números de calidad de Gold posteriores a la eliminación del nivel del target (ver §6.4).
- **Cap. 2, Marco teórico y antecedentes.**

**Cierre:** revisión del autor, capítulo por capítulo.

### F4: Tesis, metodología

**Depende de:** el protocolo congelado y el glosario.

**Cierre:** revisión del autor.

### F5: Tesis, resultados y discusión

**Depende de:** el cierre de la búsqueda (§6.1). Las figuras se generan con scripts en `herramientas/`, a partir del ledger y los JSON de la campaña cerrada.

**Cierre:** cada número coincide con su fuente, y revisión del autor.

### F6: Conclusiones, resumen, anexos y revisión integral

**Chequeos:**
- 0 referencias y 0 citas indefinidas;
- todas las citas verificadas;
- glosario consistente;
- números coincidentes con sus fuentes;
- formato según el reglamento.

**Cierre:** versión para el director y, después, para la entrega.

## 5. Bibliografía

El catálogo pasó de 15 a 71 entradas el 2026-09-18, con dos relevamientos pedidos por el autor: **modelos documentados y probados en la industria** y **funciones de ganancia y pérdida documentadas**. De las 71, hay **69 con el DOI resuelto y los metadatos confirmados campo por campo contra Crossref**; las 2 restantes son literatura gris sin DOI y están marcadas `verificado: false`, que es lo que dispara el aviso de `exportar_bib.py`.

### 5.1 Lo que el relevamiento dejó en claro

- **No hay trabajo publicado de pronóstico de caudal del Río Uruguay con aprendizaje automático a 1–10 días.** Lo más cercano es `mattiuzi-2021-m5-uruguai`, que predice **nivel** a 3 días. El hueco existe y está delimitado.
- El piso a superar es medible: `fan-2017-uruguai-operacional` reporta 2–3 días útiles de anticipación con MGB-IPH en el alto Uruguay.
- **Ya hay un sistema de aprendizaje automático operando sobre la cuenca:** el de `nearing-2024-global-extreme-floods`, que además **no usa una pérdida simétrica** sino la verosimilitud de una laplaciana asimétrica. Es el antecedente más incómodo y más importante: la idea de asimetría ya está en producción.
- El antecedente más cercano al aporte es `dahal-2026-ensemble-diverse-loss-functions`, que ya entrena con pérdidas expectílicas, aunque con τ fijo y sin modular por régimen.
- Hay un resultado teórico que **acota lo que se puede prometer**: `brehmer-strokorb-2019-tail-properties` prueba que las propiedades de cola no son elicitables.
- Y una objeción previsible: `kratzert-2024-nunca-una-sola-cuenca`. **Con el encuadre del 2026-09-18 deja de ser una amenaza y pasa a ser un experimento** (ver §4, F1): el modelo preentrenado regionalmente y ajustado localmente es uno de los candidatos a implementar, y gana o pierde midiéndolo sobre esta cuenca.

### 5.2 Lo que todavía falta (**a buscar y verificar**)

- **LSTM, origen:** Hochreiter y Schmidhuber (1997).
- **Comparación de pronósticos:** Diebold y Mariano (1995); Harvey, Leybourne y Newbold (1997), por la corrección HLN que usa B11.03.
- **Validación en series temporales:** Bergmeir y Benítez (2012), o equivalente.
- **Pronóstico numérico:** TIGGE, Bougeault et al. (2010); GEFS Reforecast v12, Hamill et al. (2022).
- **Productos observacionales de CPTEC:** MERGE, Rozante et al. (2010), y SAMeT.
- **Operación de embalses en cascada** en la cuenca. El autor y el codirector pueden sumar referencias [AUTOR].
- Confirmar contra la fuente las dos entradas de literatura gris brasileña (`mattiuzi-2021`, `mattiuzi-2023`).

## 6. Dependencias con otros frentes y hallazgos

Estos frentes no son de esta rama. Se reportan acá y el autor decide.

### 6.1 Lo que bloquea capítulos

| Necesidad | Frente | Bloquea |
| --- | --- | --- |
| Cierre de la búsqueda: B11.01 (walk-forward del campeón) y B11.02 (TEST único) | Modelado (`feature/fase-estrategias`) | F5 |
| Predicciones guardadas (brecha G-05), para hidrogramas | Modelado | Figuras de F5 |
| Merge de `feature/fase-estrategias` a `main-predic` | Autor | Traer resultados sin copiarlos a mano |
| Reporte de calidad de Gold actualizado (el actual es anterior a sacar el nivel del target) | Dataset | Cap. 3 |
| Esquema único de biblioteca entre `research/` y la UI | Autor / Rio_Search | Usar la UI para la bibliografía |

### 6.2 Numeración de decisiones duplicada

Las Decisiones 039–051 de `docs/decisions.md` tienen **otro contenido** en `main-predic` que en `feature/rio-search`. Por ejemplo, la 043 es "la fuga se verifica en entrenamiento" en una rama y "cierre de la Fase 3 BiLSTM" en la otra. En la de `main-predic` no existe la 041.

### 6.3 La UI de Rio_Search no puede leer `research/`

La UI está en `feature/rio-search`. Lee `rio_search/research/catalog/` y exige el campo `type`. Los 15 YAML de `research/catalog/` usan `tipo` (`yaml_catalog.py::_from_dict` → `KeyError`), así que el listado fallaría entero.

Además, al guardar desde la UI se reescribiría el YAML sin `doi`, `volume`, `pages`, `verificado` ni `rol`, y la nota perdería las secciones que no conoce.

`research/README.md` dice que la app "lee de acá sin cambios", y no es así.

### 6.4 Documentos desactualizados que no conviene citar tal cual

- `README.md` raíz;
- `docs/dataset_definition.md`;
- `docs/roadmap.md` (corte 2026-08-24);
- `docs/gold_quality_report.md` (es anterior a sacar el nivel de Gold);
- `docs/README.md`;
- el resumen de `rio_search/experiments/matrix.yaml`.

### 6.5 Terminología en transición

"Portón" nombra dos cosas: el filtro de calidad de lluvia y temperatura, y el nombre anterior del modulador. En el código siguen `gate.py` y `--gate-rain`.

### 6.6 A verificar en modelado antes de citar

- El *skill* de B9.01 y B9.03 (0,398) es anómalo frente al resto (~0,07).
- La nota de B6.04 habla de 5 y 15 años, pero solo se corrió 5.
- El percentil del modulador se calcula sobre la serie completa, así que no sería estrictamente causal.

Los tres salen del inventario automático de ramas. No los verifiqué contra el código.

## 7. Qué necesito del autor

### Para arrancar (F1)

1. ~~**Reglamento o guía de la carrera**~~ — **resuelto el 2026-09-18** con lo que el autor dejó en `info-institucional/`. Lo que se aprendió de ahí:
   - **Secciones y extensión:** no hay reglamento que las fije. La referencia es el plan aprobado de `Ejemplos/`: 4 capítulos, ~10 páginas de cuerpo.
   - **Formato:** tampoco está reglamentado. Se conserva el del TFI validado del autor. Hay modelo de carátula (`2-Caratula-PLAN de tesis.docx`), que la portada ahora replica.
   - **Abstract en inglés:** no se pide en el plan.
   - **Estilo de citas:** no está reglamentado. El plan de ejemplo usa citas numéricas; el TFI validado del autor usa APA. **Se mantiene APA**, que es lo que el autor ya presentó y le aceptaron. Conviene confirmarlo con el director igual.
   - **Modo de entrega:** formulario online de la secretaría de la MDM, todo en PDF: nota del estudiante, plan, nota de aval del director y del codirector, y los CV de ambos. El instructivo avisa que un error de forma retrasa el trámite en el Consejo Directivo.
   - **Título:** "escrito sin mayúsculas" salvo nombres propios, y el instructivo remarca que aunque sea provisorio arrastra a las instancias siguientes.
2. **Datos de portada** (queda pendiente lo que no salió de los documentos):
   - título provisorio: hoy dice "Método de proyección del caudal de la cuenca alta del río Uruguay en territorio de Brasil", que es la dirección que dio el autor el 2026-09-18. Él mismo avisó que no lo tiene cerrado, **así que hay que cerrarlo con el director**;
   - nombre exacto (el TFI dice "Sebastian", sin tilde);
   - ~~director~~: **Gustavo Denicolay Pacheco**. Falta su grado académico, filiación institucional y correo, que el instructivo pide dentro del plan;
   - codirector: nombre, grado académico, filiación y correo;
   - lugar de trabajo, si corresponde.
3. **Fechas:** entrega del plan de tesis, fecha objetivo de la tesis y ritmo de revisión con el director.
4. **Encuadre:**
   - la pregunta de investigación;
   - si G-RAL es el aporte central o un componente;
   - si el pipeline de datos (medallion) es un capítulo o un anexo.

### Para avanzar

5. **PDFs de los papers** en `research/documents/` (fuera de git), para escribir notas con lectura real. También la bibliografía que sugieran el director y el codirector. El ejemplo de **plan** aprobado ya llegó; falta, si se consigue, una **tesis** aprobada de la carrera, que es la referencia para F3–F6.
6. **Permiso para traer material de fuera del repo:**
   - el TP1 de Tesis II y los TPs de Tesis I (respaldo de Overleaf);
   - mapas exportados del proyecto QGIS.
7. **Biblioteca y UI:** confirmar `research/` como biblioteca única. Decidir si se adapta la UI de Rio_Search a ese esquema y quién lo hace (no es alcance de esta rama).
8. **Dónde se compila:** solo local (MiKTeX) o también Overleaf. En Overleaf no funciona el `BIBINPUTS` compartido y habría que cambiar cómo se ubica el `.bib`.
9. **Git:** autorización para commitear en `feature/tesis-latex` y para pushear a `origin`.
