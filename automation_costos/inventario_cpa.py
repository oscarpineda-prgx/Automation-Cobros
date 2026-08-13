"""Inventario del acervo de CPA Vision: una fila por RFC descargado.

Es el archivo que se comparte con negocio para responder "¿qué tenemos bajado?". Antes se
armaba a mano cada vez; ahora se regenera solo al terminar cada lote de descarga
(`cpa_vision.request_vendor_master_batch`) y queda junto al dataset, en
`CPA_VISION_DIR/Inventario_CPA_Vision.xlsx`, que es la carpeta que consultan los auditores.

Se lee del Parquet, que es la fuente de verdad del proyecto: nunca de los CSV ni de las
métricas de lote (una descarga puede figurar como OK en las métricas y haber llegado vacía).

Deduplicación: un mismo RFC puede tener varias descargas con años que se solapan (p. ej.
una de 2020-2025 y otra de solo 2025). Contar todas inflaría los conceptos, así que por
cada (rfc, año) se toma un único `request_id`: el de mayor cobertura. Es exactamente el
mismo criterio que usa `cruce_cpa._CTE_ELEGIDO` para leer los datos.
"""

from __future__ import annotations

from pathlib import Path

import config

NOMBRE_ARCHIVO = "Inventario_CPA_Vision.xlsx"

COLUMNAS = [
    "RFC",
    "Proveedor (Emisor CFDI)",
    "Años descargados",
    "# Años",
    "Conceptos (renglones)",
    "Facturas (UUID)",
    "Primera emision",
    "Ultima emision",
]

_CONSULTA = """
WITH cobertura AS (
    SELECT rfc, request_id, COUNT(DISTINCT year) AS anios, COUNT(*) AS filas
    FROM read_parquet(?, hive_partitioning = 1)
    GROUP BY rfc, request_id
),
elegido AS (
    SELECT rfc, year, request_id FROM (
        SELECT d.rfc, d.year, d.request_id,
               ROW_NUMBER() OVER (
                   PARTITION BY d.rfc, d.year
                   ORDER BY c.anios DESC, c.filas DESC, d.request_id
               ) AS rn
        FROM (SELECT DISTINCT rfc, year, request_id
              FROM read_parquet(?, hive_partitioning = 1)) d
        JOIN cobertura c USING (rfc, request_id)
    ) WHERE rn = 1
)
SELECT
    p.rfc                                                        AS "RFC",
    max(p."Emisor")                                              AS "Proveedor (Emisor CFDI)",
    string_agg(DISTINCT CAST(p.year AS VARCHAR), ', ' ORDER BY CAST(p.year AS VARCHAR))
                                                                 AS "Años descargados",
    count(DISTINCT p.year)                                       AS "# Años",
    count(*)                                                     AS "Conceptos (renglones)",
    count(DISTINCT p."UUID")                                     AS "Facturas (UUID)",
    min(CAST(p."Fecha Emision" AS DATE))                         AS "Primera emision",
    max(CAST(p."Fecha Emision" AS DATE))                         AS "Ultima emision"
FROM read_parquet(?, hive_partitioning = 1) p
JOIN elegido e ON p.rfc = e.rfc AND p.year = e.year AND p.request_id = e.request_id
GROUP BY p.rfc
ORDER BY count(*) DESC
"""


def generar_inventario(
    parquet_root: Path | str | None = None, salida: Path | str | None = None
) -> Path:
    """Regenera el inventario y devuelve la ruta escrita.

    Los RFC sin ninguna fila (descargas que llegaron vacías) no aparecen: el inventario
    dice lo que HAY, no lo que se intentó.
    """
    import duckdb

    raiz = Path(parquet_root) if parquet_root else config.CPA_VISION_PARQUET_DIR
    destino = Path(salida) if salida else config.CPA_VISION_DIR / NOMBRE_ARCHIVO
    patron = f"{raiz.as_posix()}/**/*.parquet"

    with duckdb.connect() as con:
        con.execute("PRAGMA disable_progress_bar")
        try:
            # El agregado recorre decenas de millones de filas; sin tope DuckDB intenta
            # materializarlo en RAM y muere. Con limite usa disco para lo que no quepa.
            con.execute("SET memory_limit='4GB'")
        except Exception:  # noqa: BLE001 — versiones viejas de DuckDB no lo soportan
            pass
        df = con.execute(_CONSULTA, [patron, patron, patron]).df()

    destino.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNAS].to_excel(destino, index=False)
    return destino


def actualizar_inventario(parquet_root: Path | str | None = None) -> Path | None:
    """Igual que `generar_inventario`, pero nunca lanza.

    Se llama al cerrar un lote de descarga: si el inventario falla (Excel abierto por el
    auditor, permisos, DuckDB sin memoria) no debe tirar un lote que costó horas ni ocultar
    que las descargas SÍ se hicieron. Se avisa y se sigue.
    """
    try:
        destino = generar_inventario(parquet_root)
        print(f"Inventario CPA Vision actualizado: {destino}", flush=True)
        return destino
    except Exception as exc:  # noqa: BLE001
        print(f"[Inventario] no se pudo actualizar ({exc})", flush=True)
        return None
