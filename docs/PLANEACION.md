# Planeación de proveedores 2026

> Qué proveedores se trabajan, en qué orden y en qué periodo.
> **Última actualización:** 2026-07-23

---

## 1. El archivo maestro

**`Proveedores_planeacion_2026.xlsx`** (hoja `Lista Proveedores`) es **el master vigente**
desde 2026-07-23. Reemplaza a `vendor_master_fechas.xlsx`, que queda como **borrador
histórico** (986 RFC, solo `RFC` + `FECHAS`).

- **1,044 proveedores** de datos.
- **Encabezados en la fila 8**, datos desde la fila 9.
- Llave: **número de proveedor** (`col A`, `vndnbr`), **no RFC**.

### Columnas que gobiernan el trabajo

| Columna | Col | Qué significa |
|---|---|---|
| `Proveedor` | A | Número de proveedor (`vndnbr`) |
| `Nombre proveedor` | B | Razón social |
| `PENDIENTES 2020-2024` | K | `REVISAR 2020 - 2024` → se trabaja ese periodo · `TERMINADO` → no se toca |
| `PENDIENTES 2025` | L | `REVISAR 2025` → se trabaja 2025 · `TERMINADO` → no se toca |
| `Prioridad descarga Oscar` | X | `Prioridad` → va primero |
| `Total_Records` | C | Volumen (para estimar tiempo de descarga) |

## ✅ RESUELTO: las compras de 2025 están en OTRA base (2026-07-24)

Lo que parecía un bloqueo era una **base distinta**. `F_COMPRAS` existe en dos bases del
**mismo servidor** (`ATL20AF2222SQ19`), partidas por año:

| Base | Periodo |
|---|---|
| `SORIANA_PROJECTS` | compras **2020–2024** |
| `SORIANA_2025_PROJECTS` | compras **2025** |

`fetch_compras()` ahora **une las dos automáticamente**: si el periodo pedido cruza el límite
(p. ej. 2020–2025) hace **dos consultas** —cada una recortada a su rango de años— y concatena.
Si solo toca un rango, hace una sola. Es transparente para todos los proveedores; el auditor
no elige la base. Ver [database.py](../automation_cobros/database.py) (`FUENTES_COMPRAS`).

> ⚠️ **`SORIANA_2025_PROJECTS` también devuelve 2022-2024, pero esos años están
> INCOMPLETOS** (Óscar, 2026-07-24). De esa base se toma **solo 2025**; todo lo anterior
> sale de `SORIANA_PROJECTS`. **No ampliar los rangos de `FUENTES_COMPRAS`.**
> Ver [LOGICA_NEGOCIO.md](LOGICA_NEGOCIO.md) R25.

**Verificado el 2026-07-24 (Selecta 741):** solo-2024 = 6,949 filas; solo-2025 = 3,183 filas;
completo 2020–2025 = 58,558 filas (rango `rcvdt` 2020-01 → 2025-12).

**Consecuencia:** la parte **`REVISAR 2025`** de la planeación **ya se puede ejecutar** para
todos los proveedores.

> **Selecta (741):** su salida del 2026-07-23 cubría solo 2020-2024. Conviene **re-ejecutarla
> con el periodo completo 2020–2025** para incorporar el 2025. Igual para los otros urgentes
> cuya planeación pide 2025.

## 2. Reglas de periodo (definidas por Óscar, 2026-07-23)

- `REVISAR 2020 - 2024` en K → descargar y trabajar **2020–2024**.
- `REVISAR 2025` en L → descargar y trabajar **2025**.
- **Ambos a la vez** → periodo **completo 2020–2025**.
- `TERMINADO` en una columna → ese periodo **no se toca**.

**Estado actual del master:**
- Col K: 575 `TERMINADO`, 468 `REVISAR 2020-2024`
- Col L: 1,043 `REVISAR 2025` (casi todos)

## 3. Orden de trabajo

1. **URGENTE** — los 6 de abajo, se necesitan lo antes posible.
2. **Prioridad** — 59 proveedores marcados `Prioridad` en col X (58 en periodo completo).
3. **El resto** — según las columnas de pendientes.

## 4. 🔴 Los 6 proveedores URGENTES

Son los próximos a entregar. Estado de descarga verificado en el Parquet el 2026-07-23:

Estado de descarga verificado en el Parquet el 2026-07-23 (RFC resuelto desde SQL):

| Proveedor | Nombre | Periodo | ¿Descargado? | RFC |
|---|---|---|---|---|
| **76034** | COMERCIALIZADORA PEPSICO MEXICO | 2020–2025 | ✅ **Sí** | `CPM110719SG3` |
| **5462** | MARCAS NESTLÉ | 2020–2025 | ✅ **Sí** | `MNE0409226K9` |
| **391250** | DISTRIBUIDORA ARCA CONTINENTAL | 2020–2025 | ✅ **Sí** | `DJB850527F30` |
| **80622** | 3M MEXICO | solo 2025 | ✅ **Sí** | `TMM720509PYA` |
| **73692** | EMPACADORA CELAYA | 2020–2025 | ✅ **Sí** (2026-07-23) | `ECE830923MJ2` |
| **741** | SELECTA DEL CAMPO | 2020–2025 | ✅ **Sí** (2026-07-23) | `SCA060711FG6` |

> ✅ **LOS 6 URGENTES YA ESTÁN DESCARGADOS.** Celaya y Selecta se bajaron el 2026-07-23
> con los 6 años completos (verificado: Celaya 1,108,078 filas, Selecta 43,224 filas,
> rango 2020-01 a 2025-12, un solo request cada uno, sin duplicación).
>
> **Todos pueden pasar YA por compras → cruce → recálculo → validación.**

### Descargar los 2 pendientes

```bash
python main.py cpa-batch-vendors \
    --input urgentes_pendientes.xlsx \
    --user <usuario_cpa> --password <password_cpa> \
    --batch-size 2 \
    --download-dir outputs/cpa_vision \
    --parquet-dir outputs/cpa_vision/parquet \
    --browser-channel msedge
```

`FECHAS` acepta `2020-2025` (rango) o `2025` (un año). El lote descarga el ZIP y lo
convierte a Parquet en el mismo dataset.
>
> ⚠️ **Ojo con las duplicaciones de Pepsico y Nestlé:** `CPM110719SG3` y `MNE0409226K9`
> tienen dos `request_id` cada uno (2020-2025 + solo 2025), con filas duplicadas. Al cruzar
> hay que deduplicar por `request_id` o filtrar la partición solo-2025.
> Ver [ESTADO_ACTUAL.md](ESTADO_ACTUAL.md).

## 5. 🔑 El problema del RFC — y su solución

El master tiene **número de proveedor**, pero el Parquet de CPA Vision está indexado por
**RFC**. No hay una tabla directa número ↔ RFC.

**Solución adoptada:** no hace falta esa tabla. **El archivo de Compras ya trae el RFC en su
columna `cnpj` (col A).** Entonces:

```
número de proveedor  --(F_COMPRAS)-->  Compras.xlsx  --(cnpj)-->  RFC  -->  Parquet
```

Al generar el Compras de un proveedor, el RFC queda dentro del archivo. El cruce lo lee de
ahí; **el auditor nunca teclea el RFC**. Ver [CRUCE_IMPLEMENTACION.md](CRUCE_IMPLEMENTACION.md).

## 6. Cruce contra el master de descargas

De los **43 RFC ya en el Parquet**, varios corresponden a proveedores del master. La
correspondencia número ↔ RFC se va construyendo sola conforme se generan los Compras
(§5), así que **no se mantiene una lista manual**.
