# 🔑 Mapeo del cruce CPA Vision → Compras

> **Especificación del cruce.** Documento operativo del objetivo de la semana.
>
> **Fuentes:** reunión 004 (2026-06-09) con Luis Martínez
> ([nota](reuniones/004-2026-06-09-mapeo-columnas-cruce.md)) **+ capturas de pantalla del
> archivo real** aportadas por Óscar el 2026-07-22, que traen los **nombres reales de las
> columnas** y las **fórmulas literales de Excel**.
>
> **Última actualización:** 2026-07-22 11:50
> **Archivo de ejemplo de las capturas:** proveedor **137 - SPECTRUM BRANDS**

---

## 1. Llave del cruce — `ID_CRUCE`

```
número de proveedor  +  número de factura  +  código de barra
```

Óscar marcó en rojo **`ID_CRUCE`** sobre la columna del código de barras en ambos archivos
(capturas [40:47] y [41:30]):

| Parte de la llave | Compras | CPA Vision |
|---|---|---|
| **código de barra** 🔴 | **`Y` — `codbarra`** | **`AK` — `noIdentificacion`** |
| número de factura | **`R` — `invnbr`** | **`P` — `Folio`** |
| número de proveedor | **`B` — `vndnbr`** | del contexto de la descarga (un RFC por solicitud) |

> ⚠️ **Ojo: compras tiene DOS columnas de código.** `Y = codbarra` y `Z = upc`.
> **La llave es `codbarra` (Y)**, no `upc`.

### 1.1 🔴 `invnbr` NO se puede cruzar directo contra `Folio` — requiere normalizar

**Verificado el 2026-07-22** sobre `outputs/Compras_383612_ALCEDA S. A. DE C. V.xlsx`
(~3,000 valores de `invnbr`):

| Patrón (`9` = dígito) | Filas | Ejemplo |
|---|---|---|
| `FN-99999` | **2,688** | `FN-21226` |
| `FN99999` | 168 | `FN21226` |
| `FN-999999` | 70 | |
| `FN-9999999` | 33 | |
| `-999999` | 9 | sin serie |
| `99999` | 7 | folio pelón |
| `REM-9999-9999999` | 4 | formato distinto |

**Qué es `invnbr`:** el **número de factura del proveedor**, tal como quedó capturado en el
sistema — **con su serie incluida**. La serie cambia según el proveedor:
`FN-21226` (Alceda), `EXT-13163`, `TSO-10735`, `REM-…`

**El formato es inconsistente incluso dentro del mismo proveedor.** Ejemplo real visto por
Óscar en el filtro de Excel: conviven **`EXT-13163`** y **`EXT13338`** — misma serie, uno con
guion y otro sin él. Lo mismo con `TSO-11748` frente a variantes sin guion.

En CPA Vision los datos vienen **limpios y separados**:
`O (Serie)` = `FMZ`, `P (Folio)` = `64171398`, `N (SerieFolio)` = `FMZ64171398`.

> ⚠️ **Un `JOIN` directo `invnbr = Folio` no encontraría prácticamente nada.**

**Estrategia propuesta (a validar con datos al implementar):**

1. Normalizar ambos lados: `UPPER()` y quitar todo lo que no sea alfanumérico.
   `FN-21226` → `FN21226` ; CPA `SerieFolio` → `FN21226` → **match**
2. Si no hay match, reintentar contra **solo la parte numérica** vs. `Folio`.
   `-21226` → `21226` = `Folio` → match
3. Medir la **tasa de cruce** de cada estrategia y reportarla antes de dar el cruce por bueno.

El riesgo del paso 2 es un falso positivo entre series distintas; se acota porque el cruce ya
va restringido por **RFC + código de barras**.

> ⚠️ **C17 sigue vigente:** en las capturas `noIdentificacion` se ve como **`7.50102E+12`**.
> Al leer los CSV en Python hay que forzar esa columna a texto.

## 0. ⛔ REGLA DE ALCANCE (Óscar, 2026-07-22)

> **Las únicas columnas que se tocan son las del bloque `BT`–`CD`** (§2), las marcadas con las
> bandas de color.
>
> **Todo lo demás del archivo de compras se deja EXACTAMENTE como está.**
> Si una columna no aparece marcada ahí, **no se modifica y no hay que buscarle origen.**

Esto aplica en particular a `facdecto` (AM), `fact_desct` (BQ), `ctouni` (AN), `can_rec` (AJ)
y todas las demás: **son de solo lectura para este proceso.**

**Archivo de referencia:** `Compras_137_SPECTRUM BRANDS DE MEXICO SA DE CV.xlsm`

## 2. Bloque de columnas EDI en el archivo de compras (BT → CD)

Las capturas muestran **tres bandas de color** sobre las columnas, que indican **el origen de
cada dato**:

| Banda | Color | Significado |
|---|---|---|
| **CPA VISION** | 🟡 amarillo | Se copia tal cual del archivo de CPA Vision |
| **Compras** | 🟢 verde | Ya existe en el archivo de compras |
| **Cálculos** | 🟠 naranja | Se deriva con fórmula |

### Tabla completa

| Col | Campo | Etiqueta visible | Origen | Cómo se obtiene |
|---|---|---|---|---|
| **BT** | `canfac_edi` | Cantidad | 🟡 **CPA Vision** | Columna `Cantidad` |
| **BU** | `factem_edi` | fact_empaq | 🟢 **Compras** | **Ya está en compras.** No viene de CPA Vision |
| **BV** | `ctobto_edi` | ctonto*factemp | 🟠 **Cálculo** | `= ctonto_edi × factem_edi` |
| **BW** | `ctonto_edi` | Valor unitario | 🟡 **CPA Vision** | Columna `Valor Unitaria` |
| **BX** | `impart_edi` | Importe concepto | 🟠 **Cálculo** | `= ctobto_edi × canfac_edi × (1 + poriva_edi)` |
| **BY** | `prieps_edi` | IEPS | 🟡 **CPA Vision** | Porcentaje de IEPS |
| **BZ** | `imieps_edi` | ieps_totfactura | 🟡 **CPA Vision** | Columna `U` (IEPS) — **copiar, no calcular** (§4.0.2.1) |
| **CA** | `poriva_edi` | IVA | 🟡 **CPA Vision** | Porcentaje de IVA |
| **CB** | `impiva_edi` | iva_totfactura | 🟡 **CPA Vision** | Columna `S` (IVA) — **copiar, no calcular** (§4.0.2.1) |
| **CC** | `totfactura` | Total | 🟡 **CPA Vision** | Total de la factura |
| **CD** | `uuid` | UUID | 🟡 **CPA Vision** | Folio fiscal |

### ¿Dato o fórmula? (verificado en las capturas)

| Campo | Contenido de la celda |
|---|---|
| `prieps_edi` (BY) | **valor** — `0` en BY8 [36:55]. Es dato, no fórmula |
| `poriva_edi` (CA) | **valor** — `0.16` en CA10 [37:25]. Es dato, no fórmula |
| `imieps_edi` (BZ) | **fórmula** |
| `impiva_edi` (CB) | **fórmula** |
| `ctobto_edi` (BV) | **fórmula** |
| `impart_edi` (BX) | **fórmula** |

Confirma las bandas de color: **los porcentajes se copian de CPA Vision; los importes se calculan.**

### Resumen por origen

- **Se copian de CPA Vision (6):** `canfac_edi` · `ctonto_edi` · `prieps_edi` · `poriva_edi` ·
  `totfactura` · `uuid`
- **Ya está en compras (1):** `factem_edi`
- **Se calculan (4):** `ctobto_edi` · `impart_edi` · `imieps_edi` · `impiva_edi`

> ⚠️ **Corrección respecto a la nota de la reunión 004:** ahí se registró que `impart_edi`
> se tomaba del `importe concepto` de CPA Vision. **Las capturas muestran que NO: es una
> celda con fórmula.** La etiqueta "Importe concepto" solo indica a qué concepto corresponde.
> Ver §5.

## 2.0 Columnas del archivo de compras (capturas [39:17] y [40:47])

Encabezados en la **fila 6**, datos desde la **fila 7**.

| Col | Campo | Notas |
|---|---|---|
| `A` | `cnpj` | RFC del proveedor |
| **`B`** | **`vndnbr`** | **Número de proveedor — parte de la llave** |
| `C` | `vndname` | `SPECTRUM BRANDS…` |
| `D` | `concaten` | Llave de agrupación sin prefijo |
| `E` | `dptnbr` | Departamento |
| `F` | `ponbr` | Orden de compra |
| `G` | `podt` | Fecha de la orden |
| `H`–`K` | `tip_po`, `ctg_po`, `postatus`, `po_org` | |
| `L` | `rcvnbr` | **Nota de entrada** (entra en el `folio`) |
| `M` | `rcvdt` | Fecha de recepción |
| `N` | `strnbr` | **Tienda** (entra en el `folio`) |
| `O` / `P` | `year`, `month` | |
| **`R`** | **`invnbr`** | **Número de factura — parte de la llave** |
| `S` | `invdt` | Fecha de factura |
| `T`–`W` | `division`, `nombre_division`, `po_group`, `po_groupdescrip` | |
| `X` | `cltstyle` | |
| **`Y`** | **`codbarra`** | 🔴 **`ID_CRUCE` — el código de barras** |
| `Z` | `upc` | ⚠️ **NO es la llave** |
| `AA`–`AC` | `grupoarticulo`, `gpoartdesc2`, `itmdesc` | Descripción del artículo |
| `AD` / `AE` | `poitmcspck`, `poitmsz` | |
| **`AF`** | **`fact_empaq`** | 🟢 **Origen de `factem_edi`** — ver §2.0.1 |
| `AG`–`AI` | `poqty`, `rcvqty`, `invqty` | Cantidades pedida / recibida / facturada |
| `AJ` | `can_rec` | **Cantidad recibida** — entra en `imp_aud` |
| `AK` / `AL` | `poitmgrscst`, `poitmnetcst` | Costo bruto / neto de la orden |
| `AM` | `facdecto` | ⚠️ **¿Factor de descuento?** — ver C10 |
| **`AN`** | **`ctouni`** | **Costo unitario del sistema — el que se compara contra `ctonto_edi`** |
| `AO` | `ctontol` | |
| `AY` / `AZ` | `ieps_t007s`, `iva_t007s` | **Tasas SAP** (fallback cuando no hay EDI) |
| `BQ` | `fact_desct` | ⚠️ **¿Descuento de catálogo?** — ver C10 |
| `BR` | `tipo_marca` | `Comercial` |
| `BS` | `cod_tipo_mvto` | `101` |
| `BT`–`CD` | **bloque EDI** | ver §2 |
| `CE` / `CF` | `cto_aud`, `iva_aud` | Columnas de auditoría |

### 2.0.0 `concaten` — fórmula confirmada [42:03]

```excel
D23  =CONCATENATE(N23,L23)      →  concaten = strnbr + rcvnbr
```

Es decir **tienda + nota de entrada**, sin prefijo ni ceros de relleno. Confirma la
composición del `folio` descrita en LOGICA_NEGOCIO.md §2.

### 2.0.1 ✅ C11 resuelto — de dónde sale `factem_edi`

**`factem_edi` (BU) se alimenta de `fact_empaq` (AF)**, que **ya existe en el propio archivo
de compras**. Confirmado en [39:17] (`AF6 = fact_empaq`) y por Óscar el 2026-07-22.

Por eso `factem_edi` está marcada en **verde** (origen: Compras) y no en amarillo.
**No hay que buscarla en CPA Vision.**

## 2.1 Estructura del libro de compras (de las capturas)

**Hojas del libro:** `impaud` · `dpagar` · `Sheet3` · **`Compras`** · `Compra_Neta x Mes` ·
`Analisis de Costos`

> 📌 `impaud` es la **hoja auxiliar del VLOOKUP** con el límite duro de 4,779 filas
> (LOGICA_NEGOCIO.md §8.1), y `dpagar` la del "debió pagar".

**Layout de la hoja `Compras`:**
- **Fila 6** = encabezados de campo (`cnpj`, `vndnbr`, …)
- **Fila 5** = etiquetas descriptivas (`Cantidad`, `Valor unitario`, …)
- **Filas 1–4** = título, logo Soriana, nombre del proveedor y celdas de trabajo
- **Datos desde la fila 7**

**Columnas de contexto:** `A cnpj` · `B vndnbr` · `C vndname` · `D concaten` · `E dptnbr` ·
`F ponbr` · `G podt` · `BS cod_tipo_mvto`

**Inmediatamente después del bloque EDI:** `CE cto_aud` · `CF iva_aud` — las columnas de
auditoría que consumen todo lo anterior.

## 3. Fórmulas literales de Excel (de las capturas)

Capturadas del video de la reunión 004, minutos **33:19 – 38:44**:

```excel
BV7 (ctobto_edi)  =+BW7*BU7                → ctonto_edi × factem_edi          [37:43]
BX7 (impart_edi)  =+(BV7*BT7)*(1+CA7)      → ctobto_edi × canfac_edi × (1+IVA)
BZ7 (imieps_edi)  =+(CC7/(1+BY7))*BY7      → totfactura ÷ (1+prieps) × prieps [36:11] ✅
CB7 (impiva_edi)  =+(CC7/1.16)*0.16        → totfactura ÷ 1.16 × 0.16         [34:40] 🔴
```

### 🔑 Las dos fórmulas de impuesto deben ser iguales — ✅ CONFIRMADO POR ÓSCAR

| | Fórmula tal como está | Tasa |
|---|---|---|
| `imieps_edi` (IEPS) | `=+(CC7/(1+BY7))*BY7` | ✅ **dinámica** — lee `prieps_edi` |
| `impiva_edi` (IVA) | `=+(CC7/1.16)*0.16` | 🔴 **quemada** |

**Aclaración de Óscar (2026-07-22):**

> *"Pongo 0.16 y 1.16 porque el `poriva_edi` es 0.16, pero donde saldría otra cantidad de
> porcentaje entonces se cambiaría. **La fórmula sería más cercana o igual a la de IEPS.**"*
>
> *"Así mismo igualito sería en `poriva_edi` para calcular la columna `impiva_edi`."*

**El `1.16 / 0.16` era circunstancial, no intencional.** El criterio correcto y definitivo es:

```excel
CB7 (impiva_edi)  =+(CC7/(1+CA7))*CA7      ← usar poriva_edi, igual que el IEPS
BZ7 (imieps_edi)  =+(CC7/(1+BY7))*BY7      ← ya está bien
```

En Python:
```python
imp = totfactura / (1 + tasa) * tasa      # tasa = poriva_edi o prieps_edi
```

### ⚠️ Ambos importes van sobre el TOTAL DE LA FACTURA, no por artículo

Óscar lo subrayó: *"ya ese IVA no lo toma por artículo sino por total factura"*.
En la captura [34:43] `impiva_edi` da **5,198.08**, coherente con `totfactura = 37,686.08`.

`impiva_edi` e `imieps_edi` **son fórmulas calculadas en compras**, no valores copiados de
CPA Vision. Esto es lo que genera C14.

### ✅ Validación del IEPS (cierra C15)

En **[36:55]** Óscar puso manualmente `prieps_edi (BY7) = 0.08` **solo para probar la
fórmula**, y el resultado en pantalla fue **`2791.56148`**.

**Verificado el 2026-07-22:** `37686.08 ÷ 1.08 × 0.08 = 2791.5614814814…` ✅

> ⚠️ **El `0.08` es un valor de prueba tecleado por Óscar, NO un dato real del proveedor.**
> SPECTRUM BRANDS trae `prieps_edi = 0` en todas las filas. La fórmula queda validada; **sigue
> sin haber un proveedor real con IEPS** en los datos vistos.

### Impacto de la tasa quemada (fila 7, `totfactura = 37,686.08`)

| Tasa real | Fórmula dinámica | Fórmula quemada | Error |
|---|---|---|---|
| 16% | 5,198.08 | 5,198.08 | 0.00 |
| **8%** | 2,791.56 | 5,198.08 | **+2,406.52** |
| **0%** | 0.00 | 5,198.08 | **+5,198.08** |

Con IVA de 16% no se nota. Con 8% (frontera) o 0% (alimentos) **inventa impuesto que no existe**.

### ✅ Verificación aritmética (2026-07-22)

Se validaron las **9 filas con datos** de las capturas contra las 3 fórmulas.
**Las 9 cuadran exactamente en las 3.**

| canfac | factem | ctobto | ctonto | impart | poriva | impiva | totfactura |
|---|---|---|---|---|---|---|---|
| 1 | 4 | 1108 | 277 | 1285.28 | 0.16 | 5198.08 | 37686.08 |
| 27 | 2 | 452 | 226 | 14156.64 | 0.16 | 30618.56 | 221984.56 |
| 42 | 2 | 478 | 239 | 23288.16 | 0.16 | 14085.28 | 102118.28 |
| 28 | 1 | 355 | 355 | 11530.40 | 0.16 | 11866.88 | 86034.88 |
| 4 | 2 | 452 | 226 | 2097.28 | 0.16 | 4969.76 | 36030.76 |
| 9 | 1 | 323 | 323 | 3372.12 | 0.16 | 642.40 | 4657.40 |
| 2 | 1 | 355 | 355 | 823.60 | 0.16 | 708.80 | 5138.80 |
| 107 | 1 | 355 | 355 | 44062.60 | 0.16 | 39924.00 | 289449.00 |
| 4 | 4 | 876 | 219 | 4064.64 | 0.16 | 1417.92 | 10279.92 |

> ⚠️ **Una de las capturas muestra `=+(BW7*BU7)*(1+CA7)`** — es decir
> `ctonto × factem × (1+IVA)`, **sin multiplicar por `canfac_edi`**. Esa variante **solo
> coincide en filas donde `canfac_edi = 1`**; en la fila 2 daría `524.32` en vez de
> `14156.64`. **Parece una fórmula a medio escribir durante la sesión. La correcta es la de
> `BV*BT`.**

## 4. Estructura del archivo de CPA Vision

### 4.0 🔑 El archivo tiene DOS bloques de impuestos, a dos niveles distintos

Captura del minuto **[10:03]** (proveedor **Lala**, 2025, 21 filas). Esto es lo que faltaba
para entender el archivo:

| Bloque | Columnas | Nivel | Contenido |
|---|---|---|---|
| **A — Comprobante** | `S` IVA · `T` ISR · `U` IEPS · `V` TASA IVA · `W` TASA ISR · `X` TASA IEPS | **Factura completa** | Importes y tasas del CFDI entero |
| **B — Concepto** | `AO` Base · `AP` Importe Imp · `AQ` Impuesto · `AR` Tasa o cuota | **Renglón** | Impuesto de cada artículo |

**Los valores del bloque A se repiten en todas las filas de la misma factura**, igual que
`Total`. Ejemplo verificado: el folio `64177184` ocupa **9 filas**, todas con
`Subtotal = Total = 1500.84`.

> 📌 **Esto explica R22.** El equipo tomó las tasas del **bloque A (nivel comprobante)**, por
> eso el impuesto "se calcula a nivel de factura completa, no por artículo". Es coherente con
> lo que dijo Luis — no era un error suyo, es la estructura del archivo.

### 4.0.1 Convención de las anotaciones de Óscar

> 🟣 **Los rótulos en morado son anotaciones de Óscar con el nombre del campo DESTINO en la
> base de compras.** Los nombres en negro (`IVA`, `IEPS`, `TASA IVA`…) son los **encabezados
> originales del archivo de CPA Vision**.
>
> Es decir: **morado = a dónde va · negro = de dónde viene.**

### 🔴 CORRECCIÓN (2026-07-22) — el mapeo de tasas estaba invertido

Óscar revisó un proveedor **con IVA de 16%** y confirmó:

> *"La columna de `IVA` tiene valor de **pesos** y la de `TASA IVA` tiene valor **porcentual**."*

Evidencia: en esa captura, las filas con `TASA IVA = 0.16` traen en `IVA` montos como
`38.43`, `101.65`, `677.67`, `813.20`; las filas con `TASA IVA = 0` traen `IVA = 0`.

**Mapeo correcto:**

| CPA Vision | Contenido | → Compras |
|---|---|---|
| **`V` — TASA IVA** | **porcentaje** (`0.16`) | **`poriva_edi`** ✅ |
| **`X` — TASA IEPS** | **porcentaje** | **`prieps_edi`** ✅ |
| `S` — IVA | **importe en pesos** | *(ver §4.0.2)* |
| `U` — IEPS | **importe en pesos** | *(ver §4.0.2)* |
| `Z` — UUID | | `uuid` |
| `AF` — Cantidad | | `canfac_edi` |
| `AH` — Valor Unitario | | `ctonto_edi` |
| `Y` — Total | | `totfactura` |

> ❌ **Queda invalidado** lo dicho en la reunión 004 [9:58] (*"columnas S y U"*) y las
> anotaciones moradas sobre `S` y `U` de la captura [11:28]. **Eran las columnas de importe,
> no las de tasa.**

> **Si no se hubiera detectado:** `poriva_edi` se habría llenado con pesos, e
> `impart_edi = ctobto × canfac × (1 + poriva_edi)` habría multiplicado por `(1 + 38.43)`
> en lugar de por `1.16`.

> ✅ La etiqueta `imieps_edi` sobre `V` de la captura [11:28] estaba a medio pegar
> (*"Select destination and press ENTER or choose Paste"*), no era un mapeo.

### 4.0.1.1 Las 3 columnas marcadas en amarillo en compras [13:26]

En la hoja `Compras` quedaron resaltadas en amarillo **`prieps_edi` (BY)**, **`poriva_edi`
(CA)** y **`uuid` (CD)** — las que la reunión 004 [12:35] identificó como *"por IEPS, por IVA
y UUID"*, es decir **las que había que poblar desde CPA Vision**.

### 4.0.2 💡 Los importes de impuesto SÍ vienen en CPA Vision

**Confirmado el 2026-07-22:** `S (IVA)` y `U (IEPS)` **traen el importe en pesos**.

En la reunión 004 [11:13] se concluyó que *"el importe de esos impuestos no viene
directamente en CPA Vision, así que solo se llenaría el porcentaje"*, y de ahí nacieron las
fórmulas `totfactura ÷ (1+tasa) × tasa`. **Esa premisa era incorrecta.**

Por lo tanto **`impiva_edi` e `imieps_edi` se podrían copiar** de `S` y `U` en vez de
calcularlos. Ventajas:

1. **Elimina C13** — no hay tasa que quemar ni que parametrizar.
2. **Es el dato del CFDI**, no una reconstrucción.
3. **Evita un posible error de fórmula en el IEPS** — ver §4.0.3.

> ⚠️ **Es una propuesta, no un cambio hecho.** Cambia lo definido con Luis en la reunión 004,
> así que **lo decide Óscar** (y en su caso se valida con Luis). Ver C19.

### 4.0.2.1 🔴 DOBLE VALIDACIÓN CONTRA 66M DE FILAS REALES (2026-07-22)

Óscar propuso **calcular las fórmulas candidatas y compararlas contra el importe en pesos que
declara el CFDI**. Se hizo sobre el dataset Parquet completo con DuckDB.
Script reproducible: [`scripts/validar_formulas_impuesto.py`](../scripts/validar_formulas_impuesto.py)

#### Resultado 1 — qué son realmente las columnas `IVA` (S) e `IEPS` (U)

| Filas con IVA 16% (8,692,170) | Coincidencias |
|---|---|
| `IVA` = **`Importe Impuesto` (AP)** | **8,692,170 — 100.00%** ✅ |
| `IVA` = `Base × tasa` | 8,690,896 — 99.99% |
| `IVA` = `Total ÷ (1+t) × t` | 77,682 — **0.9%** ❌ |

| Filas con IEPS 8% (13,167,869) | Coincidencias |
|---|---|
| `IEPS` = **`Importe Impuesto` (AP)** | **13,167,869 — 100.00%** ✅ |
| `IEPS` = `Base × tasa` | 13,166,509 — 99.99% |
| `IEPS` = `Total ÷ (1+t) × t` | 573,894 — **4.4%** ❌ |

> **`S` y `U` NO son valores de comprobante: son el importe del impuesto DEL RENGLÓN**,
> idénticos a `Importe Impuesto`. Cada fila trae **un solo tipo de impuesto**
> (verificado: **0 filas** tienen IVA e IEPS distintos de cero a la vez).

#### Resultado 2 — la fórmula `Total ÷ 1.16 × 0.16` falla en la mayoría de las facturas

| Tipo de factura | Facturas | % que cuadra | Error promedio |
|---|---|---|---|
| Tasas **mezcladas** | **401,981 (55%)** | **1.3%** ❌ | **+$1,565.86** |
| Tasa **única** | 334,815 (45%) | 89.0% | −$364.06 |

**Causa:** la mayoría de las facturas de Soriana **mezclan artículos gravados y a tasa 0**
(alimentos). Dividir el `Total` completo entre `1.16` asume que **todo** está gravado.

**Ejemplo real** (UUID `d0597acb-…`, 65 renglones):

```
IVA real del CFDI            $     60.47
Total ÷ 1.16 × 0.16          $  5,003.33      ← 83 veces más
```

#### Conclusión

**Copiar `S` y `U` es lo correcto**, no calcularlos. El CFDI ya trae el importe exacto por
renglón, y sumarlo por factura da el total verdadero.

Esto **cierra C13, C19 y C20** y **cambia la naturaleza de C14**: como el dato es por renglón,
**sí se puede sumar** sin duplicar.

### 4.0.3 ⚠️ La fórmula del IEPS puede estar sobrestimando

**Solo aplica si una factura trae IVA e IEPS al mismo tiempo.**

En un CFDI mexicano el IEPS grava el subtotal, y el IVA grava (subtotal + IEPS):

```
Total = (Subtotal + Subtotal×ieps) × (1 + iva) = Subtotal × (1+ieps) × (1+iva)
```

Con eso:

| Fórmula | Resultado | ¿Correcto? |
|---|---|---|
| `Total ÷ (1+iva) × iva` | `Subtotal × (1+ieps) × iva` | ✅ sí — la base del IVA incluye el IEPS |
| `Total ÷ (1+ieps) × ieps` | `Subtotal × (1+iva) × ieps` | ❌ **inflado por `(1+iva)`** |

El IEPS real es `Subtotal × ieps`. La fórmula lo **sobrestima en un 16%** cuando además hay IVA.

> **No se ha podido verificar con datos**: no hay ninguna factura con IEPS real en lo revisado
> (C15), y la prueba de Óscar con `0.08` se hizo sobre una fila **sin IVA efectivo**, donde el
> problema no aparece.
>
> **Si se copian `S` y `U` (§4.0.2), este riesgo desaparece por completo.**

### 4.1 Columnas del archivo (captura [10:03], proveedor Lala)

| Col | Nombre | Ejemplo |
|---|---|---|
| `I` | UsoCFDI | `G01` |
| `J` | Exportacion | `1` |
| `K` | Estatus | `Vigente` |
| `L` | Fecha Emision | `10/15/2025` |
| `M` | Fecha de C… | |
| `N` | SerieFolio | `FMZ64171…` |
| `O` | Serie | `FMZ` |
| **`P`** | **Folio** | `64171398` → **número de factura, parte de la llave del cruce** |
| `Q` | Subtotal | `282.24` |
| `R` | Descuento | `0` |
| `S` | IVA | `0` ⚠️ ¿importe o tasa? |
| `T` | ISR | `0` |
| `U` | IEPS | `0` ⚠️ ¿importe o tasa? |
| `V` | TASA IVA | `0` |
| `W` | TASA ISR | `0` |
| `X` | TASA IEPS | `0` |
| **`Y`** | **Total** | `282.24` → `totfactura` |
| **`Z`** | **UUID** | `a7280d1f-…` → `uuid` |
| `AA` | Forma de pago | `99` |
| `AB` | Metodo de pago | `PPD` |
| `AC` | Tipo comprobante | `ingreso` |
| `AD` | Unidad | `Pieza` |
| `AE` | Clave Unidad | `H87` |
| **`AF`** | **Cantidad** | `24` → `canfac_edi` |
| `AG` | Descripcion | `Yog Lala 100 Beb Fresa-Coco 220 g` |
| **`AH`** | **Valor Unitario** | `11.76` → `ctonto_edi` |

### 4.2 Detalle de columnas del bloque de concepto

Columnas reales (captura del 2026-07-22):

| Col | Nombre | Ejemplo | Mapeo / notas |
|---|---|---|---|
| `W` | TASA ISR | `0` | |
| `X` | TASA IEPS | `0` | ¿→ `prieps_edi`? ver ⚠️ abajo |
| **`Y`** | **Total** | `1386.18` | **→ `totfactura`** (confirmado por Óscar) |
| **`Z`** | **UUID** | `00038509-…` | **→ `uuid`** |
| `AA` | Forma de pago | `99` | |
| `AB` | Método de pago | `PPD` | |
| `AC` | Tipo comprobante | `ingreso` | Coincide con el filtro "Ingreso" de la descarga |
| `AD` | Unidad | `Pieza` | 📌 **Aquí se ve si es pieza / caja / kilo** (R15) |
| `AE` | Clave Unidad | `H87` | Clave SAT de unidad |
| **`AF`** | **Cantidad** | `1`, `5`, `8`, `12` | **→ `canfac_edi`** |
| `AG` | Descripcion | `Salchicha Viena Lala Plenia 288gr` | |
| **`AH`** | **Valor Unitario** | `27.30`, `26.37` | **→ `ctonto_edi`** |
| **`AI`** | **Importe concepto** | `27.30`, `210.96` | **= Cantidad × Valor Unitario** (verificado) |
| `AJ` | Descuento | `0` | ⚠️ ver §6 |
| **`AK`** | **noIdentificacion** | `7.50102E+12` | **Código de barras — llave del cruce** ⚠️ ver abajo |
| `AL` | Clave SAT | `50112005` | Clave de producto SAT |
| `AM` | ObjetoImp | `2` | `02` = sí objeto de impuesto |
| `AN` | Descripcion | `Carne pro…`, `Productos…` | |
| `AO` | Base | `27.30`, `210.96` | Base gravable = importe |
| `AP` | Importe Imp | `0` | **Importe del impuesto** |
| `AQ` | Impuesto | `2` | `002` = IVA, `003` = IEPS |
| `AR` | Tasa o cuota | `0` | **La tasa real del renglón** |
| `AS` | TipoFactor | `Tasa` | |
| `AT` | Emisor | `COMERCIA…` | |
| `AU…` | Receptor | `TIEN…` | |

> ⚠️ **Discrepancia con la reunión 004.** Ahí se dijo que las tasas estaban en las columnas
> **`S` y `U`**. En esta captura las tasas aparecen en **`X` (TASA IEPS)** y en el bloque de
> impuestos **`AP`–`AS`** (`Importe Imp`, `Impuesto`, `Tasa o cuota`). **Hay que confirmar de
> cuál columna se toma `poriva_edi` y `prieps_edi`** — probablemente del bloque `AQ`+`AR`
> (tipo de impuesto + su tasa), que es el que sigue la estructura del CFDI.

> ⚠️ **`noIdentificacion` se ve como `7.50102E+12` (notación científica).** Excel lo está
> truncando visualmente. **Al leerlo en Python hay que forzarlo a texto**, o se pierden
> dígitos del código de barras y el cruce falla.

### 4.1 🔴 El `Total` (Y) se REPITE en cada renglón de la factura

En la captura, las **7 filas** de la factura traen **el mismo `Total` = `1386.18`**.
Es el total del comprobante, repetido a nivel concepto.

**Verificado el 2026-07-22:**

| Cantidad | Valor Unitario | Importe concepto |
|---|---|---|
| 1 | 27.30 | 27.30 |
| 5 | 14.00 | 70.00 |
| 8 | 26.37 | 210.96 |
| 12 | 33.93 | 407.16 |
| 6 | 39.95 | 239.70 |
| 5 | 72.10 | 360.50 |
| 6 | 11.76 | 70.56 |
| | **SUMA** | **1,386.18** = `Total` ✅ |

> Es la misma factura de $1,386.18 con 7 registros que se revisó en la reunión 004 [24:56].

**⚠️ Matiz importante:** esta identidad `Σ importe concepto = Total` **se cumple aquí porque
la factura tiene tasa 0** (`Importe Imp = 0`, `Tasa o cuota = 0` — son alimentos: salchicha,
yogur). **En una factura con IVA 16%, `Total` sería `Σ importe concepto × 1.16`.**
No asumir la identidad como general.

## 5. 🔴 El `Importe` de CPA Vision NO es el `impart_edi` de compras

Verificado con las capturas:

```
CPA Vision:  Importe      = Valor Unitaria × Cantidad          (SIN impuesto)
Compras:     impart_edi   = ctobto_edi × canfac_edi × (1+IVA)  (CON IVA, y con factor de empaque)
```

**Son dos cosas distintas.** El `Importe` de CPA Vision **no se copia** a `impart_edi`; este
último se recalcula. Tenerlo claro al implementar el cruce, porque los nombres se parecen.

> 📌 Esto además da una **vía de validación**: si `ctonto_edi × canfac_edi` no coincide con el
> `Importe` de CPA Vision, es señal de que **el valor unitario venía por caja** y hay que
> dividir (ver §7).

## 6. ⚠️ CPA Vision SÍ trae una columna `Descuento`

En las capturas aparece la columna **`Descuento`** (en los ejemplos, todos en `0`).

Esto es potencialmente **el enganche del "descuento de catálogo"** que Luis mencionó en la
reunión 003 (hueco C10) y que hasta ahora no tenía origen identificado.
**Falta confirmar con Luis o Mónica si es el mismo concepto** y si debe restarse del
`ctonto_edi` antes de calcular.

## 7. Regla del valor unitario por caja

Confirmado en las reuniones 003 y 004: el `Valor Unitaria` de CPA Vision **a veces viene por
caja completa, no por unidad**. Cuando es así hay que **dividir entre la cantidad**.

Ejemplo de la reunión: `$282 ÷ 24 = $11.75`.

**Factor de empaque** = cantidad de unidades dentro de una caja o paquete
(caja de 4 yogures → factor = 4).

## 8. 🔴 Pendientes que hay que resolver ANTES de implementar

| # | Pendiente | Por qué importa |
|---|---|---|
| **C13** | ✅ **CERRADO — superado por §4.0.2.1.** Ya no hay tasa que parametrizar: el importe **se copia** de `S`/`U`. | — |
| **C14** | ✅ **RESUELTO por §4.0.2.1.** Las columnas `S`/`U` de CPA Vision son **por renglón**, no por factura. Al copiarlas, `SUM` por factura da el total correcto y **no hay duplicación**. | Solo aplicaba si se seguía calculando sobre `totfactura`. |
| **C10** | ⚪ **FUERA DE ALCANCE.** El descuento de catálogo vive en columnas que **no están marcadas** (`facdecto` AM, `fact_desct` BQ). Por la regla de alcance (§0) **no se tocan**. Óscar lo confirmó el 2026-07-22. | — |
| **C11** | ✅ **CERRADO.** `factem_edi` (BU) sale de **`fact_empaq` (AF)**, que ya está en el archivo de compras. No viene de CPA Vision. | — |
| **C15** | ✅ **CERRADO con datos reales.** El Parquet **sí trae IEPS**: 13,167,869 filas al 8%, 22,293 al 26.5%, 20,186 al 53% y 993 al 30%. | — |
| **C9** | ✅ **CERRADO — la premisa era falsa.** Luis dijo que la hoja de CPA Vision *"solo baja proveedores con tasa 16% u 8%, no los de vinos/licores (53%, 30%, 26.5%)"*. **Las tres tasas especiales SÍ están en el Parquet.** | Los vinos y licores **sí se descargan**. No hace falta vía alterna. |
| **C20** | ✅ **CERRADO — superado.** Al copiar `S`/`U` no se reconstruye nada, así que el sesgo del IEPS no aplica. | — |
| **C16** | ✅ **CERRADO y CORREGIDO.** El porcentaje sale de **`V (TASA IVA)` → `poriva_edi`** y **`X (TASA IEPS)` → `prieps_edi`**. **NO** de `S`/`U`, que son importes. | — |
| **C18** | ✅ **CERRADO — y el mapeo estaba invertido.** Óscar verificó en un proveedor con IVA 16%: `IVA` trae pesos, `TASA IVA` trae el porcentaje. | Corregido en §4.0.1. |
| **C19** | 🟢 **REABIERTO — decisión de Óscar.** Los importes **sí vienen** (`S`, `U`). Copiarlos en vez de calcularlos eliminaría C13 y el riesgo de §4.0.3. Cambia lo acordado con Luis en la reunión 004. | Simplifica el cruce y usa el dato del CFDI en vez de reconstruirlo. |
| **C20** | **La fórmula del IEPS sobrestima si hay IVA e IEPS en la misma factura** (§4.0.3): `Total ÷ (1+ieps) × ieps` da `Subtotal × (1+iva) × ieps`, inflado por `(1+iva)`. | Sin verificar por falta de facturas con IEPS (C15). **Desaparece si se adopta C19.** |
| **C17** | **`noIdentificacion` se muestra como `7.50102E+12`.** | Si se lee como número **se pierden dígitos del código de barras y el cruce no encuentra nada**. Forzar a texto. |

## 9. Estrategia de ejecución acordada [reunión 004, 56:09]

> **Primero descargar toda la información de los ~1,000 proveedores y almacenarla en una base
> de datos SQL. Después hacer los cruces con compras.**
>
> **Revierte** la "opción 2" de la reunión 002 (generar compras primero y cruzar en paralelo).

## 10. Planeación por volumen

Archivo con **el conteo de registros por proveedor**: **"AP-LI", pestaña "LI 2025"**, en la
**carpeta de Mónica** (Luis compartió la ruta).

| Proveedor | Registros |
|---|---|
| Sigma Alimentos | **12,000,000** |
| Lala / comercializadora de lácteos | **8,000,000** (6.7 M en Audit Tools) |
| Lactex | **8,000,000** |
| Bepensa | 341,000 |

- La diferencia con Audit Tools se explica porque **Audit Tools solo cuenta compras**,
  mientras el archivo **incluye devoluciones**.
- **~12 proveedores** superan **1,700,000** registros; de **"Genopa/Genapro"** hacia abajo el
  volumen cae mucho.
- **~15–20 proveedores grandes concentran ~20 horas** de descarga.

## 11. Campos que quedan sin cruce (acuerdo explícito)

Acuerdo de la reunión 004 [30:33]: se puede avanzar con lo que sí se logra llenar y **dejar
vacío lo demás**, porque **el análisis principal se basa en el `costo neto EDI`
(`ctonto_edi`) contra el costo del sistema (`ctouni`)**.
