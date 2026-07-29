# Reunión 002 — 2026-04-29 — Seguimiento y paso a paso de CPA Vision

**Documentado el:** 2026-07-22 11:10
**Participantes:** Óscar Pineda, Mónica López, Héctor Saucedo
**Duración:** 1h 19m
**Contexto:** Óscar presenta el primer borrador funcional de la GUI. Se define el paso a
paso exacto de la descarga en CPA Vision (el insumo que originó `cpa_vision.py`) y se
levanta una restricción organizacional importante sobre la integración con Audit Tools.

---

## Resumen en 5 líneas

1. Óscar demuestra la GUI en 3 botones: **Generar Compras → Recalcular compras editadas →
   Generar validación de condiciones**. Mónica y Héctor lo validan conceptualmente.
2. **Restricción nueva y fuerte:** la vicepresidencia y Antonio pidieron que **todo quede
   integrado dentro de Audit Tools**. Hay que hablar con Armando.
3. Se confirma que son **4 columnas de auditoría** las que se actualizan, y que **el cruce
   con CPA Vision es por proveedor + factura + código de barras**.
4. Se documenta el **paso a paso manual completo** de la descarga en CPA Vision → esto es
   la especificación literal del scraper.
5. Escala real del problema: **400–500 proveedores al mes**, y CPA Vision entrega **un CSV
   comprimido por mes**, no un archivo consolidado.

## Decisiones tomadas

| # | Decisión | Detalle |
|---|---|---|
| 1 | **Opción 2 del flujo** | Generar primero compras y **luego** recalcular con la info de CPA Vision descargada **en paralelo**. Mónica se inclinó por esta sobre "descargar todo antes". |
| 2 | Óscar replica la consulta SQL en Python | En vez de automatizar clics en Audit Tools. Más simple y veloz. |
| 3 | Procesamiento por bloques | Héctor propone bloques/rankings (ej. proveedores 1–10) para descargar y generar validaciones en paralelo, sin esperar la lista completa. |
| 4 | **La métrica del bloque es tiempo, no cantidad** | El volumen de facturas varía muchísimo entre una tienda y una bodega/CEDI. |
| 5 | Excepción por timeout | Si pasan ~10 min sin respuesta de CPA Vision, alertar al auditor. |
| 6 | Reparto de trabajo | Héctor gestiona con Armando y Antonio (integración); Óscar avanza con Selenium/CPA Vision. |

## ⚠️ Restricción organizacional — integración con Audit Tools [7:40]

Héctor: **el acuerdo con Antonio y lo solicitado por la vicepresidencia es que todo quede
integrado dentro de Audit Tools.**

Postura de Óscar [10:06]: integrarlo directamente dentro de Audit Tools (que es **Access**)
lo ve complicado, pero **podría agregarse como procedimiento adicional**. No sabe si Audit
Tools permite integrar Python. Propone reunión con **Armando**.

> 📌 **Estado hoy:** el proyecto quedó como herramienta Python independiente con GUI Tkinter.
> **Esta restricción nunca se resolvió en esta reunión.** Verificar en reuniones posteriores
> si se cerró con Armando.

## Hallazgo técnico — cómo extrae Audit Tools [10:06]

Óscar descubrió que **Audit Tools extrae la información ejecutando una función de SQL
Server** contra la base de datos **"Soriana Projects"**, pasando **proveedor y rango de
fechas** como parámetros.

> 📌 Esto es exactamente lo que hoy es `dbo.F_COMPRAS(proveedor, fecha_ini, fecha_fin)` en
> `ATL20AF2222SQ19 / SORIANA_PROJECTS`. Confirma la decisión de arquitectura.

## Reglas de negocio confirmadas o nuevas

### R7 — Son 4 las columnas de auditoría que se actualizan [5:42]
**Costo Auditoría · IVA Auditoría · IEPS Auditoría · Impuesto**
(confirmado por Mónica; había sido indicado previamente por correo).

### R8 — Los campos "EDI" son el insumo, las 4 de auditoría son el resultado [25:23]
Los campos que terminan en **`EDI`** (costo EDI, factor de empaque EDI, etc.) son **los que
se extraen de CPA Vision / factura electrónica**. A partir de ellos se calculan las 4
columnas de auditoría, comparando **mejor costo e impuesto correcto**.

### R9 — 🔑 Llave del cruce CPA Vision ↔ compras [1:03:19]
> **número de proveedor + número de factura + código de barra**

Y los campos de tasa del archivo de CPA Vision corresponden a **`IVA EDI`** e **`IEPS EDI`**
en el archivo de compras.

> 📌 **Esta es la regla más importante de la reunión.** Es la especificación del puente
> Etapa A ↔ Etapa B que sigue sin implementarse.

### R10 — Hoja "Pendientes EDI" [3:10]
Óscar definió una segunda hoja con la misma información, donde se completan los datos
faltantes (manualmente o vía CPA Vision). Mónica lo valida.

### R11 — Tercera fuente cuando CPA Vision no tiene el dato [1:07:04]
A veces la información **no está en CPA Vision**; entonces los auditores la buscan en
**listas de precios de P-Mail (correo)** y actualizan **manualmente el costo auditoría**.

### R12 — Validar que el pago coincida con recepción y factura [1:12:29]
Mónica: se debe validar que **el pago coincida con la recepción y la factura**, por
**problemas históricos de pagos de facturas cruzadas en Soriana**.

> 📌 Esto conecta con el hueco C5 (`paynetamt` con `max` en vez de `sum`). Si históricamente
> hubo pagos cruzados, el supuesto de "un solo pago por folio" es frágil.

### R13 — El flujo ideal del auditor, en palabras de Mónica [1:12:29]
1. Ver las compras con **el mayor % posible de información ya poblada**.
2. **Corroborar** las diferencias preliminares detectadas.
3. Cuando estén seguros de que la diferencia es correcta, **generar el archivo de salida
   con un botón**, en el formato exacto que se envía al proveedor, **sin acomodar campos
   manualmente**.

## 📋 Paso a paso manual de descarga en CPA Vision [58:17]

**Especificación literal del scraper.** Demo hecha con la cuenta de Héctor.

1. Entrar a la sección **"Descargas"**
2. Seleccionar **rango de fechas** (año / meses)
3. Ingresar el **RFC del proveedor** — viene de la **columna A** del archivo maestro
4. Marcar **"todos los emitidos"** y **"todos los recibidos"**
5. Seleccionar tipo: **"hoja de cálculo con detalle de conceptos y tasas"**
6. Marcar **"Tienda Soriana"**
7. Presionar **"Solicitar descarga"** → se genera un **ID de solicitud**
   (ejemplo de nombre usado: *"conciliación única vez"*)
8. El archivo queda en la carpeta **Descargas** del sistema
9. El **status** se consulta en la sección **"Solicitudes"**

### Formato de salida de CPA Vision [1:17:19]
**CPA Vision genera un CSV comprimido POR MES**, no un archivo único consolidado.
Mónica no estaba 100% familiarizada con el detalle y ofreció confirmar por correo si existe
opción de descarga consolidada.

### Columnas del archivo de CPA Vision [1:03:19]
| Columna | Significado |
|---|---|
| Código de barra | Identificación del artículo |
| Valor unitario | |
| Tasa de impuesto | → mapea a `IVA EDI` / `IEPS EDI` |
| Cantidad facturada | |
| Total de factura | |

## Restricciones operativas de CPA Vision [28:50]

- **Alerta por volumen:** en una ocasión **sistemas les alertó** por un volumen de descarga
  grande. Descargando **proveedor por proveedor con diferencia de minutos** no ha habido problema.
- **Cuenta compartida:** varios auditores usan **la misma cuenta simultáneamente**.
- **Cola del sistema:** el tiempo depende de la cola. En una prueba tardó **~1 minuto para
  4 meses** de datos. Óscar estimó 30 s – 1 min si responde rápido.
- **No se controla la página externa** [39:07]: Óscar aclaró que con Selenium se puede
  automatizar, pero **no se puede controlar la velocidad ni las caídas** del sitio externo.

> 📌 La estimación de "30 seg – 1 min" resultó **muy optimista**. El promedio real hoy es de
> **~1.5 h por proveedor con picos de 7–8 h**. Ver [ESTADO_ACTUAL.md](../ESTADO_ACTUAL.md).

## Escala y capacidad

| Dato | Valor |
|---|---|
| Planeación mensual de proveedores | **400–500** [46:26] |
| Tamaño de bloque propuesto | **50–100 a la vez** |
| Almacenamiento | **30 GB libres de 1.27 TB usados** [53:43] |
| Límite por solicitud | **~100 MB** |
| Demo: proveedor 885, 2020-01-01 a 2025-01-01 | **33,975 líneas** [13:50] |

> 📌 Las 33,975 líneas del proveedor 885 son exactamente el archivo sobre el que se midió
> después el límite del VLOOKUP (4,775 folios únicos contra un tope de 4,777).
> Ver LOGICA_NEGOCIO.md §8.1.

**Optimización acordada** [46:26]: preparar la descarga por bloques **según fechas ya
definidas por proveedor**, evitando **descargar periodos ya revisados**.

**Idea de Óscar** [51:57]: procesar proveedor por proveedor **en cadena** — mientras uno se
descarga, empezar a generar el archivo de validación del anterior. Sugiere también evaluar
**un servidor corriendo permanentemente**.

## Pendientes de infraestructura [53:43]

Héctor da seguimiento a:
- **Más capacidad de procesamiento / servidor** — con **Víctor** y **Simón Matcal**
  ("Mascal"). El contacto anterior era **Fabio, que ya no está en la compañía**.
- **Más espacio de almacenamiento.**

## Nota técnica — Selenium vs. acceso directo [43:08]

Se discutió que **Selenium toma control visual de la pantalla** mientras ejecuta, lo que es
**tiempo muerto para el auditor**. Óscar mencionó otra alternativa: **acceder directamente
al código/fuente en vez de simular clics**, y quedó de investigarla.

> 📌 **Resuelto en la implementación:** hoy se usa **Playwright con msedge**, no Selenium,
> lo que permite modo headless y evita el bloqueo de pantalla.

## Compromisos

- [ ] **Héctor:** gestionar con **Armando** (integración técnica en Audit Tools) y **Antonio**
- [ ] **Héctor:** seguimiento de servidor/procesamiento (Víctor, Simón Matcal) y almacenamiento
- [ ] **Mónica:** enviar por correo un **ejemplo de info vacía y cómo se llenaría con CPA Vision**
- [ ] **Mónica:** confirmar por correo si CPA Vision tiene **descarga consolidada en un solo archivo**
- [x] **Óscar:** avanzar en la automatización de CPA Vision
- [ ] **Óscar:** investigar alternativa a Selenium (acceso directo al fuente)
- [ ] Reunión de seguimiento a inicios de la semana siguiente

## Dudas abiertas al cierre

1. **¿Se integra en Audit Tools o queda aparte?** — sin resolver, depende de Armando.
2. **¿Existe descarga consolidada en CPA Vision?** — Mónica quedó de confirmar.
3. **¿Cómo se maneja la cuenta compartida** si varios auditores y el bot descargan a la vez?

## Citas y momentos clave

> [7:40] Héctor: el acuerdo con Antonio y lo solicitado por la **vicepresidencia** es que
> **todo quede integrado dentro de Audit Tools**.

> [1:03:19] Mónica: el cruce con el archivo de compras se hace por **número de proveedor +
> número de factura + código de barra**.

> [1:17:19] Óscar descubre que **CPA Vision genera un archivo CSV comprimido por mes**, no
> un archivo único consolidado.

**Incidente:** [17:40–22:59] el proceso se colgó por **sobrecarga de la máquina de Óscar**;
hubo pausa técnica de ~5 minutos para reiniciar. Antecedente del pendiente de servidor.
