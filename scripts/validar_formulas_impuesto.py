"""Doble validación de las fórmulas de impuesto contra el dato real del CFDI.

Idea (propuesta por Óscar el 2026-07-22): en vez de decidir a ciegas qué fórmula usar
para `impiva_edi` / `imieps_edi`, calcular las candidatas y compararlas contra el
importe en pesos que el propio CFDI declara (columnas `IVA` e `IEPS` de CPA Vision).
La que cuadre, gana.

Se corre sobre el dataset Parquet de CPA Vision con DuckDB.

Uso:
    python scripts/validar_formulas_impuesto.py
"""

from datetime import datetime
import config
from pathlib import Path

import duckdb

PARQUET = config.CPA_VISION_PARQUET_DIR
GLOB = f"{PARQUET.as_posix()}/**/*.parquet"
TOL = 0.02  # tolerancia en pesos


def main():
    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute(
        f"""CREATE VIEW r AS SELECT UUID,
        TRY_CAST(Total AS DOUBLE) tot, TRY_CAST(Subtotal AS DOUBLE) sub,
        TRY_CAST(IVA AS DOUBLE) iva_imp, TRY_CAST(IEPS AS DOUBLE) ieps_imp,
        TRY_CAST("TASA IVA" AS DOUBLE) t_iva, TRY_CAST("TASA IEPS" AS DOUBLE) t_ieps,
        TRY_CAST(Base AS DOUBLE) base,
        TRY_CAST("Importe Impuesto" AS DOUBLE) imp_imp
        FROM read_parquet('{GLOB}', hive_partitioning=1)"""
    )

    print(f"Corrida: {datetime.now():%Y-%m-%d %H:%M:%S}\n")

    # --- Nivel renglón: ¿qué es realmente la columna IVA / IEPS? ---
    for etiqueta, col_imp, col_tasa, tasa in (
        ("IVA 16%", "iva_imp", "t_iva", 0.16),
        ("IEPS 8%", "ieps_imp", "t_ieps", 0.08),
    ):
        print(f"== Nivel RENGLÓN — {etiqueta} ==")
        print(
            con.execute(
                f"""SELECT COUNT(*) filas,
                SUM(CASE WHEN abs({col_imp} - imp_imp) < {TOL} THEN 1 ELSE 0 END)
                    AS "= Importe Impuesto",
                SUM(CASE WHEN abs({col_imp} - base*{col_tasa}) < {TOL} THEN 1 ELSE 0 END)
                    AS "= Base x tasa",
                SUM(CASE WHEN abs({col_imp} - tot/(1+{col_tasa})*{col_tasa}) < {TOL} THEN 1 ELSE 0 END)
                    AS "= Total/(1+t) x t"
                FROM r WHERE {col_tasa} = {tasa}"""
            ).df().to_string(index=False)
        )
        print()

    # --- Nivel factura: ¿sirve despejar el impuesto desde el Total? ---
    con.execute(
        """CREATE VIEW fac AS SELECT UUID,
        MAX(tot) tot, SUM(iva_imp) iva_real, COUNT(*) renglones,
        COUNT(DISTINCT t_iva) tasas_distintas
        FROM r WHERE UUID IS NOT NULL GROUP BY UUID HAVING SUM(iva_imp) > 0"""
    )
    print("== Nivel FACTURA — ¿cuadra Total/1.16*0.16 con el IVA real? ==")
    print(
        con.execute(
            f"""SELECT
            CASE WHEN tasas_distintas = 1 THEN 'tasa ÚNICA' ELSE 'tasas MEZCLADAS' END AS tipo,
            COUNT(*) facturas,
            ROUND(100.0*SUM(CASE WHEN abs(tot/1.16*0.16 - iva_real) < {TOL} THEN 1 ELSE 0 END)
                  / COUNT(*), 1) AS "% que cuadra",
            ROUND(AVG(tot/1.16*0.16 - iva_real), 2) AS "error promedio (pesos)"
            FROM fac GROUP BY 1"""
        ).df().to_string(index=False)
    )


if __name__ == "__main__":
    main()
