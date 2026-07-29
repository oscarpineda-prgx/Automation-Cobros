# Reunión 004 — 2026-06-09 — Revisión Proyecto Costos / Mapeo de columnas del cruce

**Documentado el:** 2026-07-22 11:35
**Participantes:** Óscar Pineda, Luis Martínez
**Duración:** 59m 27s
**Contexto:** **La reunión más importante del proyecto.** Se mapea campo por campo qué
columna de CPA Vision alimenta qué columna del archivo de compras, y se validan las
fórmulas con ejemplos numéricos en vivo.

> 📄 **El mapeo completo vive en su propio documento:**
> [MAPEO_CRUCE_CPA_COMPRAS.md](../MAPEO_CRUCE_CPA_COMPRAS.md)
> Esta nota conserva el contexto, las decisiones y los datos de planeación.

---

## Resumen en 5 líneas

1. Se completó **el mapeo de los 11 campos EDI** que hay que llenar en compras. Óscar lo
   confirmó al cierre: *"logró completar el mapeo de todos"* [39:54].
2. **`costo bruto` y `factor empaque` NO vienen de CPA Vision** → el factor se toma de
   compras y el costo bruto se deriva.
3. Los **importes** de IVA/IEPS **no vienen** en CPA Vision: solo el **porcentaje**. El
   importe se calcula **a nivel factura completa**, no por artículo.
4. **Cambio de estrategia:** primero **descargar todo a SQL**, después cruzar. Revierte la
   decisión de la reunión 002.
5. Aparece el archivo **"AP-LI" / pestaña "LI 2025"** con el **conteo de registros por
   proveedor** — insumo para planear la descarga por volumen.

## Decisiones tomadas

| # | Decisión | Detalle |
|---|---|---|
| 1 | **Descargar todo primero, cruzar después** | Almacenar los ~1,000 proveedores en SQL y luego hacer los cruces. **Revierte la "opción 2" de la reunión 002.** [56:09] |
| 2 | Avanzar con campos incompletos | Se puede dejar vacío lo que no se logra llenar; **el análisis principal se basa en `costo neto EDI` vs. costo del sistema** [30:33] |
| 3 | Solo se llena el porcentaje de impuesto | El importe no viene en CPA Vision; se deriva [11:13] |
| 4 | Segmentar la descarga por volumen | Usando el archivo "AP-LI" en vez de estimar a ciegas [44:52] |
| 5 | Lotes de 50 | Óscar planea pasar la lista de ~1,000 proveedores en lotes de 50 en 50 [55:02] |

## Hallazgos de negocio

### Definición de "factor de empaque" [17:19]
**La cantidad de unidades dentro de una caja o paquete.** Ejemplo: una caja de yogures que
contiene 4 unidades individuales → factor empaque = **4**.

### El valor unitario puede venir por caja [14:46]
Confirmación de lo visto en la reunión 003: el `valor unitario` de CPA Vision **a veces
viene por caja completa**, y hay que **dividirlo entre la cantidad** para obtener el
unitario real. Ejemplo: `$282 ÷ 24 = $11.75`.

### 🔴 El importe de impuesto se calcula a NIVEL FACTURA [33:20]
```
IMP IVA EDI = total factura ÷ 1.16 × 0.16
```
Luis fue explícito: **a nivel de factura completa, no por artículo individual.**
Mismo criterio para IEPS con su tasa (`÷ 1.08 × 0.08` en el ejemplo).

> 📌 **Esto merece atención.** El `imp_aud` que hoy calcula `calculations.py` opera
> **por renglón**. Aquí se define un cálculo **por factura**. Son dos niveles distintos.
> Ver hueco C14.

### Un proveedor sin impuestos
El proveedor grande usado en la demo ("comercializadora de lácteos y derivados") **no maneja
impuestos** [2:14] — por eso parte de la validación de tasas se hizo con otros ejemplos.

## Datos de volumen y planeación [44:52]

**Archivo clave descubierto:** **"AP-LI", pestaña "LI 2025"**, en la **carpeta de Mónica**.
Contiene **el conteo de registros por proveedor**. Luis compartió la ruta con Óscar.

| Proveedor | Registros |
|---|---|
| Sigma Alimentos | **12,000,000** |
| Lala / comercializadora de lácteos | **8,000,000** (6.7 M en Audit Tools) |
| Lactex | **8,000,000** |
| Bepensa | 341,000 |

**Discrepancia explicada** [48:55]: la diferencia de ~2 millones entre el archivo y Audit
Tools se debe a que **Audit Tools solo cuenta compras**, mientras que este archivo
**probablemente incluye también devoluciones**.

- **~12 proveedores** con más de **1,700,000** registros.
- De **"Genopa/Genapro"** hacia abajo, el volumen es mucho menor.
- **~15–20 proveedores grandes concentran ~20 horas** de descarga [57:23].

### Tiempos medidos
| Caso | Tiempo |
|---|---|
| Proveedor grande, **solo 2025** | **~1 hora** [0:05] |
| Estimación del histórico completo | **~7 días** [1:32] |
| Estimación del proceso completo (~1,000 proveedores) | **~20 horas**, principalmente por la **cola de CPA Vision**, no por el programa [56:09] |

### Tamaño del archivo de salida [0:05]
Descarga de **un solo proveedor, solo 2025**: **~500 MB**, dividida en **6 archivos CSV** por
el volumen. **800,000 filas × 53 columnas.**

### Hipótesis de agrupación [42:45] [48:55]
Luis propone agrupar **~10 proveedores pequeños que sumen 1–2 millones de registros** en
**una sola solicitud**. Estimación: tardaría lo mismo que Lala solo (~1 h), pero procesando
varios a la vez.

> ⚠️ **No probada.** Hoy el scraper procesa de uno en uno.

## Demo del sistema [52:04]

Óscar mostró el scraper funcionando de punta a punta:
- Permite **configurar cuántos proveedores procesar por lote** (demo con 3)
- Solicita las **credenciales de CPA Vision** (usuario de Héctor)
- Inicia sesión, selecciona botones, **cierra pestañas auxiliares y ventanas de "solicitud en
  progreso"** sin intervención manual
- Selecciona **"Recibidos" → "Vigentes" → año (2025) → RFC** y presiona **"Crear solicitud"**
- Al terminar un lote, **refresca "Solicitudes"** hasta ver el link de descarga y continúa
  con el siguiente lote

Demo hecha con "Lala" solo para ilustrar; luego cancelada.

## Compromisos

- [ ] **Óscar:** conseguir/usar el archivo **"AP-LI" / "LI 2025"** de la carpeta de Mónica
- [ ] **Óscar:** descargar toda la información y luego hacer el cruce con compras
- [ ] **Óscar:** dar seguimiento del avance a Luis y a Mónica
- [ ] Evaluar la agrupación de proveedores pequeños en una sola solicitud

## Dudas abiertas al cierre

1. **¿El importe de impuesto a nivel factura es consistente con el cálculo por renglón**
   que hace el código hoy? → C14
2. **¿Las fórmulas deben usar la tasa real** en vez de `1.16` / `1.08` literales? → C13
3. **¿Funciona la agrupación** de varios proveedores pequeños en una solicitud? (no probado)
4. **¿El descuento de catálogo** (reunión 003) afecta el `costo neto EDI`? No se mencionó
   en esta sesión. → C10

## Citas clave

> [2:14] Luis enumera los campos que Mónica pidió llenar: **cantidad facturada EDI, factor
> empaque EDI, costo bruto EDI, costo neto EDI, importe por artículo EDI, IEPS EDI, impuesto
> IEPS EDI, IVA EDI, impuesto IVA EDI, total factura y UUID**.

> [33:20] El **IMP IVA EDI se calcula a nivel de factura completa, no por artículo
> individual** (total factura ÷ 1.16 × 0.16).

> [56:09] Óscar: la estrategia más viable es **primero descargar toda la información de los
> ~1,000 proveedores y almacenarla en una base de datos SQL, y después hacer los cruces**
> con compras.
