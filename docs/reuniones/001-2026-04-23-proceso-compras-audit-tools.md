# Reunión 001 — 2026-04-23 — Proceso de Compras en Audit Tools (reunión de arranque)

**Documentado el:** 2026-07-22 11:02
**Participantes:** Mónica López (experta en costos), Óscar Pineda (desarrollo), Héctor Saucedo (jefe de Óscar)
**Contexto:** Primera reunión del proyecto. Mónica explica de punta a punta el proceso
manual de auditoría de costos que se busca automatizar. Es la reunión que define el
alcance original de la Etapa A.

> Marcas de tiempo entre corchetes = minuto de la grabación original.

---

## Resumen en 5 líneas

1. Soriana paga a proveedores contra notas de entrada; el costo de su sistema (SAP) no
   siempre coincide con el que el proveedor facturó por CFDI/EDI.
2. **Audit Tools** ya produce un Excel de compras por proveedor **con el cruce contra
   factura electrónica ya hecho** — el cruce lo calculó Data Services, no Audit Tools.
3. El cruce **no es del 100%**: falla cuando el código de barras del proveedor no coincide
   con el del cliente, o cuando falta la factura. Esos huecos el auditor los rellena **a mano**.
4. Las dos fuentes para rellenar son: **listas de precios que llegan por correo** y el
   portal **CPA Vision / CFDI Visión**.
5. Todo el proceso —bajar, detectar faltantes, complementar, recalcular, armar el
   entregable— **es 100% manual hoy, a base de copiar y pegar**. Eso es lo que hay que automatizar.

## Decisiones y alcance acordado

| # | Decisión | Detalle |
|---|---|---|
| 1 | El archivo de compras debe ser **editable** | El auditor rellena a mano las columnas de auditoría donde no hubo cruce |
| 2 | Debe haber un botón **"Recalcular"** | Recalcula costo auditoría, impuesto auditoría, debió pagar y diferencia con los datos nuevos |
| 3 | Debe haber un botón **"Generar archivo de salida"** | Produce el entregable al proveedor (consolidado + detalle) |
| 4 | El recálculo va **antes** de generar la salida | Flujo: bajar compras → detectar faltantes → complementar → recalcular → generar salida |
| 5 | Mónica comparte insumos | Archivo de salida de ejemplo, criterios de cálculo de costo/impuesto auditoría, y cómo complementar campos vacíos |
| 6 | Óscar pide las tablas SQL | Mónica ofrece mostrar en qué tablas de SQL viene la información ya cruzada [9:03] |

## Reglas de negocio establecidas

### R1 — Se toma la mejor condición (el mejor costo) [0:16]
Se compara el costo facturado por el proveedor contra el que el cliente tiene en su
sistema y **se toma la mejor condición**: el mejor costo y el impuesto correcto.

### R2 — Si el sistema del cliente trae impuesto en cero, gana la tasa del proveedor [0:16]
> "Si el sistema del cliente trae el impuesto en cero y la factura del proveedor trae una
> tasa, se deja el impuesto del proveedor."

### R3 — El cruce falla por código de barras [1:40]
La información no se cruza al 100% porque **el código de barras no coincide** entre lo
facturado por el proveedor y lo registrado por el cliente. Es la causa principal de
campos EDI vacíos.

### R4 — Origen de las diferencias [13:23]
Una diferencia detectada puede deberse a tres causas:
- **Faltante de mercancía**
- **Diferencial de costo**
- **Impuestos** — ejemplo dado: el **IEPS en vinos puede llegar al 53%**. Si el cliente lo
  tiene registrado pero el proveedor no, se deja en cero y eso genera diferencia.

> ⚠️ Esto conecta directo con el riesgo conocido de que la fórmula de Excel tiene el IVA
> clavado en `0.16` (ver LOGICA_NEGOCIO.md §8.2). Con IEPS de 53% ese atajo está mal.

### R5 — Estructura del entregable al proveedor [7:35] [10:07]
El archivo que se entrega al proveedor tiene **3 pestañas**:
1. **Total de la diferencia**
2. **Consolidado a nivel factura** (por pedido/factura)
3. **Detalle** de todos los artículos que conforman cada factura

Lleva **menos campos** que el archivo de compras de Audit Tools: solo los necesarios para
que el proveedor pueda validar la diferencia.

**Validación de consistencia** [10:52]: el "debió pagar" del consolidado debe cuadrar con
la suma del detalle. Ejemplo mostrado: nota de entrada con diferencia de $51,000, "debió
pagar" de **$1,279,707** sumado, idéntico en ambas pestañas.

### R6 — Dos fuentes para rellenar los huecos [6:16] [18:52]
Cuando los campos de factura electrónica quedan en blanco:
1. **Correos con listas de precios** (los auditores los buscan en Gmail)
2. **CPA Vision / CFDI Visión** — portal conectado con el cliente de donde se exportan a
   Excel las facturas que sube el proveedor

## Campos y columnas mencionados

### Campos que trae el Excel de compras de Audit Tools [2:02]

| Campo | Origen | Significado |
|---|---|---|
| Orden de compra | SAP | |
| Número de recepción | SAP | Nota de entrada |
| Fechas | SAP | |
| Cantidad facturada EDI | CFDI | Del cruce con factura electrónica |
| Factor de empaque EDI | CFDI | |
| Costo bruto EDI | CFDI | |
| Costo EDI | CFDI | Costo unitario facturado por el proveedor |
| IEPS EDI | CFDI | |
| IVA EDI | CFDI | |
| Total factura EDI | CFDI | |
| **Costo OUT** | calculado | Cálculo preliminar del mejor costo |
| **IVA OUT** | calculado | |
| **IEPS OUT** | calculado | |
| **Debió pagar NE** | calculado | Lo que el cliente debió pagar, a nivel nota de entrada |
| **DIF detalle NE** | calculado | Diferencia preliminar: pagado − debió pagar |

### Campos del detalle del entregable [12:00]

Descripción del artículo · Código · Material · **Costo unitario pagado** (del sistema) ·
**Costo unitario correcto** (el mejor costo derivado del cruce con factura electrónica)

### Estructura del CFDI en CPA Vision [22:51]

Código de barras · Descripción del artículo · Cantidad facturada · Precio unitario ·
Total factura

## Hallazgo clave — dónde vive la lógica de cálculo [14:56] [17:17]

Óscar preguntó **en qué columna está la fórmula que compara el costo del sistema contra el
de la factura electrónica y toma el menor**.

Respuesta de Mónica: esa fórmula está en la **tabla de compras**, en los campos
**`costo OUT`, `IVA OUT`, `IEPS OUT`**, y fueron generados **originalmente por el equipo de
Data Services**. **Audit Tools solo filtra información ya calculada**, no la calcula.

Mónica ofreció **buscar el criterio exacto** usado para generarlos.

> 📌 Esto explica por qué en el proyecto actual toda la lógica de joins vive en SQL Server
> (`dbo.F_COMPRAS`) y no en Python: se heredó de Data Services.

## Sobre CPA Vision — origen de la Etapa B [20:59] [27:56]

- Mónica demostró el portal en vivo (dos cuentas: una suya y una de Héctor), entrando a
  "Tienda Soriana" para buscar XML.
- Descargó una factura **por UUID**, con **dificultades técnicas para exportar a Excel**
  (conflicto de formatos XML/XLS).
- El portal sirve para dos cosas: **revisar facturas específicas** y hacer **descargas masivas**.

**Óscar preguntó si se puede automatizar la descarga.** Respuesta de Mónica: **sí se
pueden programar descargas, pero con limitaciones importantes:**

1. Las descargas programadas **entran en una cola visible para el cliente** — a diferencia
   de las consultas manuales, que se ven al instante.
2. **El tiempo varía** según el volumen del proveedor y el rango de fechas/facturas solicitado.

> 📌 Aquí nace la Etapa B del proyecto. Las dos limitaciones se confirmaron en la práctica:
> hoy el promedio real es de ~1.5 h por proveedor con picos de 7–8 h, y el `max_wait_minutes`
> se tuvo que subir de 90 a 420. Ver [ESTADO_ACTUAL.md](../ESTADO_ACTUAL.md).

## Ejemplos numéricos citados

| Caso | Cifra |
|---|---|
| Proveedor demo | "Aiseda", rango 2020–2024 [2:02] |
| Diferencia de ejemplo | **$27,636** (pagado $44,556 − debió pagar) [3:10] |
| Nota de entrada del entregable | diferencia **$51,000**, debió pagar **$1,279,707** [10:52] |
| IEPS máximo mencionado | **53%** en vinos [13:23] |

## Compromisos

- [x] Mónica: compartir el archivo de salida de ejemplo
- [ ] Mónica: compartir **el criterio exacto** de cálculo de `costo OUT` / `IVA OUT` / `IEPS OUT` (Data Services)
- [ ] Mónica: compartir cómo complementar los campos vacíos
- [ ] Mónica: mostrar las tablas SQL con la información ya cruzada
- [x] Óscar: empezar a trabajar con las tablas de compras
- [ ] Agendar seguimiento (se propuso para el día siguiente)

## Temas fuera de alcance mencionados

- Los **"40 procesos"** pendientes de organizar, junto con la información recopilada de un
  formulario — tema de otra reunión futura [32:50].

## Dudas abiertas al cierre de esta reunión

1. **¿Cuál es el criterio exacto de `costo OUT`?** — Mónica quedó de buscarlo. En el código
   actual está implementado como "si hay EDI y `ctonto_edi < ctouni`, toma el del EDI"
   (LOGICA_NEGOCIO.md §3), pero **falta confirmar que ese es el criterio original de Data Services**.
2. **¿Cómo se trata el IEPS?** R2 dice que si el cliente trae cero gana el proveedor, pero
   R4 describe el caso inverso (cliente lo tiene, proveedor no → se deja en cero). Falta
   precisar la regla completa.
3. **¿La clasificación de la diferencia** (faltante / diferencial de costo / impuestos) la
   hace el auditor a mano o se puede derivar? Esto es el antecedente directo del pendiente
   `dif costos` / `sin diferencia` / `sobrepago` / `faltante`.

## Citas textuales relevantes

> [17:17] Mónica: esa fórmula está en la tabla de compras, en los campos "costo OUT",
> "IVA OUT" e "IEPS OUT", generados originalmente por el equipo de **Data Services**;
> Audit Tools **solo filtra** esa información ya calculada.

> [32:00] Mónica: actualmente **todo el proceso** —bajar compras, identificar información
> faltante, complementar, recalcular y generar el archivo final— **se hace completamente de
> forma manual, copiando y pegando** campos seleccionados a otro archivo.
