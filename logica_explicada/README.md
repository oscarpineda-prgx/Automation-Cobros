# Lógica de la auditoría de costos — versión explicada

**Para:** Data Services · Audit Tools · Héctor Saucedo
**De:** Óscar Pineda — PRGX / Auditoría Soriana 2020-2024
**Fecha:** 2026-08-18

---

## Qué es esto

Los cuatro archivos de esta carpeta explican, paso a paso, **la lógica completa** con la que
se calcula lo que Soriana debió pagar a cada proveedor y la diferencia que se le reclama.

Están escritos para **leerse y replicarse** (en SQL Server o en la herramienta que ustedes
usen), no para ejecutarse. Son los mismos cálculos del sistema en producción, pero con:

- nombres de variables en español y descriptivos,
- comentarios que explican **por qué**, no solo qué,
- las optimizaciones de rendimiento **quitadas**, porque estorban para entender la regla,
- una nota **"En SQL Server"** en cada paso clave, con el equivalente aproximado.

## Léelos en este orden

| # | Archivo | Qué explica |
|---|---|---|
| **1** | [`01_cruce_cpa.py`](01_cruce_cpa.py) | Cómo se emparejan las compras de Soriana con las facturas electrónicas (CFDI) del proveedor, y qué columnas se llenan |
| **2** | [`02_calculo_auditado.py`](02_calculo_auditado.py) | **El corazón.** La regla del costo auditado, los impuestos y la diferencia por nota de entrada |
| **3** | [`03_ajustes_pagos.py`](03_ajustes_pagos.py) | Las devoluciones (MR8M / KG-14) que anulan o reducen diferencias ya detectadas |
| **4** | [`04_validacion_condiciones.py`](04_validacion_condiciones.py) | Qué entra al entregable final y cómo se arma |

El flujo completo es:

```
Compras de Soriana (SQL)  +  CFDI del proveedor (CPA Vision)
              │
              ▼
    1. CRUCE ─────────────► se llenan las columnas "EDI" (lo que el proveedor facturó)
              │
              ▼
    2. CÁLCULO ───────────► costo auditado → importe auditado → debió pagar → DIFERENCIA
              │
              ▼
    3. AJUSTES ───────────► se restan las devoluciones que el proveedor ya reintegró
              │
              ▼
    4. VALIDACIÓN ────────► el entregable: qué se reclama y por qué
```

## La idea en una frase

> Soriana pagó según el costo de **su sistema**. El proveedor facturó según **su CFDI**.
> Cuando el CFDI dice un costo **menor**, Soriana pagó de más, y esa diferencia se reclama.

## Advertencia importante

⚠️ **La fuente de verdad es el sistema en producción, no esta carpeta.** Estos archivos son
una reescritura didáctica. Si al replicar encuentran una diferencia entre lo que dice aquí y
lo que produce el sistema, **manda el sistema** — y por favor avísenme para corregir la
explicación.

Cada archivo indica al inicio a qué módulo real corresponde.

## Documentos que acompañan

| Documento | Para qué |
|---|---|
| `Guia_Columnas_Compras.pdf` | Qué significa cada columna del archivo de Compras y de dónde sale |
| `Guia_Validacion_Condiciones.pdf` | Cómo se lee el entregable final, hoja por hoja |

## Vocabulario mínimo

| Término | Qué es |
|---|---|
| **CFDI** | Factura electrónica del SAT. Es lo que el proveedor realmente facturó |
| **CPA Vision** | Portal del que se descargan los CFDI recibidos por Soriana |
| **Columnas EDI** | Las columnas del archivo de Compras que se llenan con datos del CFDI |
| **Nota de entrada** | El recibo de mercancía en tienda. Es la unidad a la que se reclama |
| **Folio** | Llave de agrupación: prefijo + tienda (4 díg.) + nota de entrada (8 díg.) |
| **Costo auditado** | El costo correcto según la auditoría (ver archivo 2) |
| **MR8M / KG-14** | Claves de devolución de pago del sistema de Soriana |

Cualquier duda, con gusto la resuelvo: Óscar Pineda.
