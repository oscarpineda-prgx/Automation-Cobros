# Reunión 003 — Capacitación CPA Vision con Luis Martínez

**Documentado el:** 2026-07-22 11:20
**Participantes:** Óscar Pineda, Luis Martínez (experto en costos)
**Fecha exacta:** ⚠️ no consta en la transcripción. Posterior a la 002 (2026-04-29).
**Contexto:** Sesión práctica 1 a 1. Luis enseña el procedimiento **real** de descarga en
CPA Vision y el criterio de validación de costos e impuestos, factura por factura.

> ⚠️ Esta reunión **CORRIGE** el procedimiento de descarga que se había documentado en la
> reunión 002. Ver §"Corrección" abajo.

---

## Resumen en 5 líneas

1. **El procedimiento de descarga correcto es distinto al de la reunión 002**: en "Emitidos"
   **no se marca nada**; solo Recibidos + Vigentes + Ingreso + Tienda Soriana.
2. **Limitación crítica**: la hoja de cálculo que se descarga **solo trae proveedores con
   tasa 16% u 8%** — **NO los de vinos/licores** (53%, 30%, 26.5%).
3. Se confirma el criterio del costo: **`costo UNI` vs `costo neto EDI`**, y **cuando el EDI
   está vacío la fórmula toma `costo UNI` por defecto**.
4. Aparece un concepto nuevo no mencionado antes: el **descuento de catálogo**.
5. El archivo a subir lleva el **RFC en la primera celda, sin encabezado**. Luis y sus
   compañeros **solo han trabajado con un RFC a la vez**.

## 🔴 Corrección al procedimiento de descarga

| | Reunión 002 (Mónica) | **Reunión 003 (Luis) — CORRECTO** |
|---|---|---|
| Emitidos | "marcar todos los emitidos" | **NO se marca nada** |
| Recibidos | "marcar todos los recibidos" | **Recibidos + Vigentes + Ingreso** |
| Alcance | "Tienda Soriana" | **Tienda Soriana** (no "todas") ✅ igual |
| Tipo de archivo | "hoja de cálculo con detalle de conceptos y tasas" | **igual** ✅ |

Luis lo reiteró **tres veces** en la sesión [2:03], [4:37], [8:47], [9:03] — señal de que es
un punto donde la gente se equivoca.

### Procedimiento correcto y definitivo

1. Sección de descarga
2. **Emitidos: no marcar nada**
3. **Recibidos → Vigentes → Ingreso**
4. **Tienda Soriana** (no "todas")
5. Seleccionar el **rango de fechas**
6. Tipo: **"hoja de cálculo con detalle de conceptos y tasas"**
   > ⚠️ **NO** la de solo *"detalle de conceptos"* — **esa no trae el porcentaje de impuesto.**
7. Subir el archivo con el RFC
8. Solicitar descarga

### ✅ Verificado el 2026-07-22: `cpa_vision.py` YA implementa el procedimiento correcto

```python
_RECEIVED_CFDI_FILTERS = frozenset({"Vigentes", "Ingreso"})          # línea 35
_CPA_DOWNLOAD_FILE_OPTION = "Hoja de cálculo con detalle de conceptos y Tasas (.csv)"  # línea 36
_CPA_DOWNLOAD_EXTRA_OPTIONS = ("Generar acumulado",)                  # línea 37
```

Y en el flujo (líneas ~946–956): *"Limpiando periodos emitidos"* → *"Seleccionando periodos
recibidos"* → *"Limpiando RFC en emitidos"* → *"Llenando RFC en recibidos"*.

**El scraper limpia Emitidos y solo llena Recibidos con Vigentes + Ingreso — exactamente lo
que indicó Luis.** No hay que corregir nada aquí.

> 📌 **Dato adicional:** el scraper usa la opción **`"Generar acumulado"`**, que probablemente
> es la **descarga consolidada** que Mónica no sabía si existía (pendiente de la reunión 002).
> Aparentemente sí existe y ya se está usando.

### Formato del archivo a subir [4:59]
- Excel o CSV
- **RFC del proveedor en la primera celda**
- **SIN encabezado de columna**
- Luis y sus compañeros **solo han trabajado con un RFC a la vez**; nunca probaron varios.

## 🔴 Limitación crítica — las tasas especiales no bajan [2:03]

> Luis: normalmente esta hoja **solo baja proveedores con tasa de 16% u 8%**, **no los de
> vinos/licores** que manejan tasas especiales: **53%, 30%, 26.5%**.

> 📌 **Impacto directo.** En la reunión 001 Mónica había señalado el IEPS de vinos (53%) como
> una de las tres causas de diferencia. Esto significa que **la vía de CPA Vision no resuelve
> el caso de vinos y licores** — justo el caso de mayor impacto económico.
> **Falta definir cómo se atienden esos proveedores.** Ver hueco C9.

## Reglas de negocio

### R14 — Criterio del mejor costo, confirmado por Luis [15:35]
Se compara **`costo UNI`** (costo del sistema) contra **`costo neto EDI`** (de CPA Vision).
**Cuando el `costo neto EDI` está vacío, la fórmula toma el `costo UNI` como mejor costo por
defecto**, porque no hay con qué compararlo.

> 📌 Confirma parcialmente §3 y el hueco **C1**. Luis validó la mitad del criterio (qué pasa
> cuando el EDI está vacío). Lo que **sigue sin confirmarse explícitamente** es si con ambos
> valores presentes siempre gana el menor.

### R15 — Unidades: caja vs. pieza vs. kilo [20:56] [39:51]
A veces el costo del archivo de compras viene **por caja** y en CPA Vision **también por
caja** → no genera diferencia. **El problema ocurre cuando las unidades no coinciden.**

Identificar si los artículos se manejan **por caja, pieza o kilos** es una de las dos
dificultades principales del proceso (ejemplo dado: yogures de distintas presentaciones y
precios).

**La corrección es el factor de empaque**: ejemplo mostrado con `costo UNI = $99` y
`costo neto EDI = $297`, evaluando si **al dividir por el factor de empaque** el resultado
cambia (297 / 3 = 99).

### R16 — Descuento de catálogo [21:45] — ⚠️ CONCEPTO NUEVO
Antes de sacar el costo auditoría, Luis **primero confirma si el proveedor maneja un
"descuento de catálogo"**, revisando la columna correspondiente.

> El descuento de catálogo **se aplica después del pago de facturas**.

> 📌 **No aparece en ninguna de las reuniones anteriores ni en la lógica implementada.**
> Puede ser una corrección al costo que hoy no se está haciendo. Ver hueco C10.

### R17 — Columnas de trabajo de Luis [21:45]
| Columna | Para qué |
|---|---|
| `costo auditoría` | El resultado |
| `costo mío` / `costo neto mío` | Para **confirmar que coincide con lo que arroja su fórmula** (control) |
| `costo OUT` | **La comparación entre `costo UNI` y `costo neto EDI`** |

> 📌 Definición explícita de `costo OUT`, el campo cuyo criterio quedó pendiente desde la
> reunión 001.

### R18 — Regla del impuesto, CONFIRMADA [40:47] [43:21]
El campo de impuesto de CPA Vision sirve para **confirmar si el proveedor factura IVA/IEPS
y si el sistema interno no lo tiene registrado correctamente**.

Conceptos guía: **`IEPS T007`** e **`IVA T0007007`**.

**La regla:**
- Si el proveedor **sí factura** el impuesto (validado contra una factura de ejemplo) →
  **se debe actualizar/incluir en el sistema**.
- Si **no lo factura** → **se deja en cero**.
- Si en la factura **no aparece el porcentaje** → **no debería registrarse el impuesto**.

**Caso concreto validado** [46:16]: si en compras sale **0%** pero en CPA Vision y en la
factura sale **16%** → **se debe actualizar el archivo de compras con 16%**. Luis lo confirmó
expresamente.

> ✅ **Esto cierra el hueco C2.** La regla es simétrica y la fuente de verdad es **la factura**,
> no el sistema. Ver §10.

## Procedimiento para validar una factura específica [43:48]

Cuando hay que comprobar si un proveedor realmente factura un impuesto:

1. Clic en **"Tienda Soriana"**
2. Aparecen estatus (ej. *"no fue posible validar clave"*)
3. Clic en **"buscar XML"**
4. Ingresar el **RFC** o el **UUID** de la factura — **más directo con UUID**
5. Ingresar la **fecha de emisión**
6. El sistema arroja el **PDF de la factura**

El PDF muestra el desglose completo: **costo unitario/UNI (por caja o pieza) · cantidad
recibida · código de barras · subtotal**.

## Volumen y desempeño [35:00]

Luis identifica que **los proveedores muy grandes (>1,000,000 de filas) podrían ser difíciles
de procesar masivamente**, y sugiere **separar la descarga masiva por año y por volumen de
registros**.

| Proveedor | Registros |
|---|---|
| Danone | ~73,000 |
| Conagra (o similar) | ~800,000 — "grande pero manejable" |
| Umbral problemático | **>1,000,000** |

> 📌 La estrategia de partición Hive por `rfc=/year=/request_id=` que se implementó después
> responde exactamente a esta recomendación.

**Conclusión de la sesión** [39:51]: lo complicado es principalmente **(a) el tiempo de
procesamiento** y **(b) identificar si los artículos se manejan por caja, pieza o kilos**.

## Prueba de 2 RFC en paralelo — INCONCLUSA [28:35]

Óscar y Luis intentaron subir **2 archivos Excel simultáneamente** (Alceda + otro proveedor,
"IV Plastic" o similar) para validar si el sistema permite procesar 2 RFC a la vez.

**Resultado: ninguno de los dos procesos terminó de procesarse durante la sesión** [47:25].
**La pregunta quedó sin respuesta.**

## Notas operativas

- **Avisos del sistema** (cancelaciones, actualizaciones de datos, vigencia de links de
  descarga) **normalmente no representan problema; simplemente se cierran** [6:48].
- Problemas de acceso se resolvieron **eliminando cookies** [6:48].
- Luis no está seguro de si **descargar por año afecta el tiempo de espera** (había marcado
  5 años) [20:21].
- Las bases de prueba usadas fueron del proveedor **"Alceda"**, rango **2020–2024**.

## Compromisos

- [ ] **Luis:** preguntar a Mónica por el **"vendor master"** (lista completa de proveedores
      a extraer con sus años correspondientes). Luis **no tiene esa información**.
- [ ] **Mónica:** confirmar **qué columnas exactas del archivo de CPA Vision se cruzan con el
      archivo de compras** — seguía pendiente desde la reunión 002 [10:48]
      > 📌 Esto es lo que presumiblemente se resuelve en la **reunión 004**.
- [ ] Confirmar si CPA Vision acepta **varios RFC a la vez** (prueba inconclusa)

## Dudas abiertas al cierre

1. **¿Cómo se atienden los proveedores de vinos/licores** si la hoja de CPA Vision no trae
   sus tasas especiales? → C9
2. **¿El descuento de catálogo debe entrar en el cálculo automatizado?** → C10
3. **¿CPA Vision acepta múltiples RFC por solicitud?** → prueba inconclusa
4. **¿Descargar por año reduce el tiempo de espera?** → Luis no está seguro

## Citas clave

> [2:03] Luis: se debe descargar la opción **"hoja de cálculo con detalle de conceptos y
> tasas"**, no la de solo "detalle de conceptos", **ya que esta última no trae el porcentaje
> de impuesto**.

> [2:03] Luis: normalmente esta hoja **solo baja proveedores con tasa de 16% u 8%, no los de
> vinos/licores** que manejan tasas especiales (53%, 30%, 26.5%).

> [15:35] Luis: cuando el **costo neto EDI está vacío, la fórmula automáticamente toma el
> costo UNI** como el mejor costo por defecto, ya que no hay con qué compararlo.

> [43:21] Luis: si el proveedor factura el impuesto, **se debe actualizar/incluir en el
> sistema**; si no lo factura, **se deja en cero**.
