# Rendimiento del exportador de Compras

> **Última actualización:** 2026-07-23
> **Archivos:** [`automation_costos/excel_exporter.py`](../automation_costos/excel_exporter.py),
> [`automation_costos/calculations.py`](../automation_costos/calculations.py)

---

## 1. El problema original

El exportador escribía el Compras con **fórmulas vivas de Excel** y **estilo por celda**.
Con 105 columnas, un proveedor grande generaba decenas de millones de celdas con estilo y
más de un millón de fórmulas. Medido: **30,000 filas tardaban >90 s**, y ni siquiera
completaba 134k. Extrapolado a 5 años (~700k filas) era inviable.

Además tenía dos defectos de fondo:
- El `VLOOKUP` de `dpagar` estaba topado a **4,779 folios** (daba `#N/A` en silencio arriba).
- Un Excel con >1M de fórmulas y `fullCalcOnLoad` **congela Excel al abrirlo**.

## 2. Qué se cambió (decisión de Óscar, 2026-07-23: "valores en Python")

1. **Valores, no fórmulas.** Las 10 columnas que eran fórmulas de Excel se calculan en
   Python (`apply_display_formula_values`), replicando las fórmulas originales pero sin el
   tope del VLOOKUP (`dpagar` = suma de `impaud` por `concaten`, con groupby).
2. **Motor xlsxwriter en modo `constant_memory`.** Serializa las filas en streaming;
   `wb.save()` de openpyxl era el cuello (51 s solo para guardar 30k filas).
3. **Sin estilo por celda en los datos.** Solo el encabezado lleva formato; los datos van
   como valores. El resaltado EDI/auditoría se queda en la fila de encabezados.
4. **Menos trabajo en `prepare_compras_dataframe`.** Ya no repite `normalize_date_columns`
   + `add_derived_base_columns` (corrían dos veces).

## 3. Resultado medido

| Caso | Antes | Ahora |
|---|---|---|
| Nestlé, 1 mes (10,731 filas) | — | **SQL 4 s + Excel 22 s** ✅ |
| 30,000 filas (sintético) | >90 s (sin terminar) | ~53 s |
| Abrir el archivo en Excel | se congela con proveedores grandes | instantáneo (sin fórmulas) |
| Límite de folios (VLOOKUP) | 4,779 | **sin límite** |

**El archivo ahora es correcto y abre bien.** Para proveedores normales (miles a ~50k
filas) el tiempo es razonable.

## 4. 🔴 Lo que SIGUE sin resolver — proveedores enormes

Un Compras de 5 años de Nestlé/Pepsico son **~700k filas × 105 columnas = ~73 millones de
celdas**. Aun con xlsxwriter, escribir eso son **~20 minutos** y produce un `.xlsx` de
cientos de MB que **nadie puede trabajar a mano**.

**El cuello ya no es el motor, es la magnitud del artefacto.** Escribir celda por celda
(cualquier librería) es O(celdas), y 73M celdas es intrínsecamente lento.

### Reparto del tiempo (medido a 30k, extrapolable)
- `prepare` (recálculo + folios por fila): ~22 s / 30k → **el 40%**
- escritura xlsxwriter: ~30 s / 30k → **el 60%**

`prepare` es lento por los bucles por fila de `make_folio`/`clean_code` en
`add_derived_base_columns` — **vectorizables** (pendiente).

## 5. Recomendación pendiente de decidir con Óscar

El **entregable real es la Validación de Condiciones** (solo las diferencias: consolidado +
detalle), que es **chica**. El Compras gigante es un intermedio.

Opciones para proveedores enormes:
- **A.** No escribir el Compras gigante en Excel; trabajar en memoria (DataFrame) y escribir
  solo la Validación. Si se necesita el Compras de referencia, guardarlo en **Parquet/CSV**
  (segundos, sin límite).
- **B.** Escribir el Compras gigante igual, asumiendo minutos y archivos enormes.
- **C.** Segmentar el Compras por año (6 archivos manejables en vez de uno).

**Recomendación técnica:** A.

> ✅ **DECISIÓN de Óscar (2026-07-23): opción B.** Se escribe el Compras completo aunque
> tarde ~20 min, porque cubre todos los años y vale la pena. **La opción A queda anotada como
> alternativa futura** por si Óscar decide cambiar. No re-abrir el tema salvo que él lo pida.

## 6. 🟢 Resuelto el 2026-07-24 — el muro de memoria

Con la opción B en marcha, **Empacadora Celaya (73692, 1,244,498 renglones)** reventaba con
`numpy._core._exceptions._ArrayMemoryError` dentro de `prepare_compras_dataframe`.

### La causa

No era el tope de filas de Excel (eso ya lo cubría el partido en `Compras`, `Compras (2)`…).
Era que la cadena de preparación hacía **cinco copias completas encadenadas** del DataFrame:

```
prepare_compras_dataframe  →  df.copy()
  recalculate_dataframe    →  df.copy()
    add_derived_base_columns   →  df.copy()
    _recalculate_invoice_level →  df.copy()
apply_display_formula_values →  df.copy()
```

más **tres copias** dentro de la Validación, y arrastraba todas las columnas que
`F_COMPRAS` devuelve y que no salen en el Compras. Con 1.24M filas × 105 columnas de tipo
`object`, **cada copia son ~9 GB**.

### Qué se hizo

| Cambio | Archivo |
|---|---|
| Parámetro `en_sitio=True` en toda la cadena: una sola copia | `calculations.py` |
| Recorte de columnas sobrantes **antes** de calcular | `calculations.py` |
| `clean_code`, `make_folio` y `normalize_date_columns` vectorizados | `utils.py` |
| La Validación copia solo sus **31 columnas fuente**, no las 105 | `validation_exporter.py` |
| Prefiltro vectorizado de folios (antes recorría ~100k grupos en Python) | `validation_exporter.py` |
| Máscara de pendientes acumulada por columna | `calculations.py` |
| `fetch_compras` lee con `fetchmany` en lotes de 100k | `database.py` |
| **La Validación se genera ANTES del Compras** | `pipeline.py` |
| `use_zip64=True` — el `.xlsx` de Celaya rebasa el ZIP clásico | `excel_exporter.py` |

### Equivalencia verificada

Se re-corrió **Selecta (741)** completo con el código nuevo y se comparó contra la salida
del 2026-07-24 10:30:

- Compras: **idéntico celda a celda** (58,558 filas × 105 columnas, 0 diferencias).
- Validación: idéntica (Consolidado 188 filas, Detalle 1,119, todas las sumas iguales).
- Además se verificaron una a una las funciones vectorizadas contra las escalares.

> ⚠️ Única diferencia conocida de las funciones vectorizadas: un valor numérico ≤ 20000 en
> una columna de fecha (que no es una fecha en ningún caso real) conserva los nanosegundos
> en vez de truncar a microsegundos. Ambas versiones producen `1970-01-01`.

### Resultado en Celaya

Memoria **estable en 13.4 GB** durante toda la corrida (antes reventaba). El pipeline llega
al final. Reparto aproximado: SQL + cruce ~25 min, Validación ~2 min, escritura del Compras
~28 min.

## 6b. Hojas del Compras: una por año (2026-07-24)

El Compras ya no se parte por tope de filas sino **por año**, según `rcvdt`: `Compras 2020`,
`Compras 2021`, … Si un solo año rebasara el tope de Excel (>1,048,576 filas), ese año se
parte en `Compras 2020 (2)`, `(3)`…

- Es **solo presentación**: reordena en qué hoja cae cada renglón, no cambia ningún valor.
- Los renglones **sin fecha (NaT)** no van a una hoja aparte; heredan el año de su mismo
  grupo (nota de entrada → factura → vecino), así caen junto a los que les corresponden.
- Los dos lectores que releen el Compras (`recalculate.read_compras_workbook` y
  `cruce_cpa.leer_compras`) ahora leen **todas** las hojas `Compras*` y concatenan. Esto
  además corrigió un bug latente: antes leían solo la hoja `Compras` y perdían las de
  continuación. **No afectó a Selecta ni Celaya**, cuyos entregables se arman desde el
  DataFrame en memoria, no releyendo el archivo.

## 6c. Proveedores que no caben en memoria: pipeline por año (2026-07-26)

Algunos proveedores son de **10-12 millones de renglones** (Arca 11.5M, Pepsico 10.1M). El
DataFrame completo no cabe en 24 GB —Celaya (1.24M) ya usaba 13 GB— y `fetch_compras` moría
con `MemoryError` en el paso de traer de SQL, antes de calcular nada.

**Solución (sin tocar la función SQL `F_COMPRAS`):** procesar **por trimestres** y consolidar.
Módulo [`pipeline_streaming.py`](../automation_costos/pipeline_streaming.py):

1. **Por trimestre** se llama `F_COMPRAS(vendor, ini, fin)` (su firma normal), se cruza con
   CPA y se acumula **por folio y por factura**: suma de `imp_aud` (debió pagar), suma de
   `impaud` de display (dpagar) y máx del pagado. Se descartan los renglones.
2. Con eso se obtienen los totales **globales por folio/factura**, así los folios cuyos
   pedidos cruzan un trimestre/año salen exactos.
3. Se re-cruza cada trimestre, se le pegan los totales globales y se escribe
   `Compras_<base>_<año>-T<n>.xlsx` (uno por trimestre; ~24 por proveedor).
4. La **Validación es una sola**, armada solo con las filas de los folios con diferencia
   (reusa `write_validation_from_dataframe`).

**Por qué trimestre y no año:** un año de estos proveedores (1.6M compras + 2.9M conceptos
de CPA) todavía no cabe en los ~13 GB libres (medido: sube a 12 GB y muere). Un trimestre
(~400k) tiene pico de **~5.5 GB**, holgado. Además se quitaron dos derroches: `cruzar` con
`en_sitio=True` (no copia el año) y un `memory_limit` en DuckDB (que use disco para los
millones de conceptos de CPA en vez de reventar).

El despachador `generar_salida_proveedor` hace un `COUNT` barato (`database.contar_compras`)
y si supera `MAX_FILAS_EN_MEMORIA` (2.5M) usa este camino; si no, el normal (intacto).

**Verificado idéntico al camino normal:** Selecta 2020-2025 (58,558 filas, 0 columnas
difieren; Validación 188/1,119 igual) y Nestlé 2020-2021 (266,478 filas **con folios que
cruzan año**; 0 difieren; Validación 7,410/114,255 igual), más un test unitario de la suma
por folio que cruza año.

> Dato: los ~3.5M renglones "sin fecha" de estos proveedores son en realidad **sin nota de
> entrada** (`rcvnbr` nulo); no forman folios reales y se reparten por año según su `podt`.

## 7. Pendientes concretos

- [x] ~~Vectorizar `add_derived_base_columns` (folios/concaten)~~ — hecho el 2026-07-24.
- [x] ~~Decidir con Óscar el manejo de proveedores enormes~~ — opción B, y ya cabe en memoria.
- [ ] Confirmar que los **valores** del Compras coinciden con lo que daban las fórmulas de
      Excel (validación de negocio con un archivo chico revisado por Luis/Mónica).
- [ ] **Bajar el consumo con dtypes.** Los 13.4 GB son casi todos el DataFrame en `object`
      (~70 bytes por celda de texto). Pasar las columnas de texto a `category` o al dtype
      `str` de pandas 3 lo bajaría varias veces. No hizo falta para Celaya; hará falta si
      aparece un proveedor bastante más grande.
