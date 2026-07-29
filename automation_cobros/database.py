from __future__ import annotations

from datetime import date

import pandas as pd
import pyodbc

import config


# F_COMPRAS está partido por año en dos bases del MISMO servidor:
#   SORIANA_PROJECTS       -> compras 2020-2024
#   SORIANA_2025_PROJECTS  -> compras 2025
# Cada fuente cubre un rango de años cerrado. Un periodo que cruce el límite
# (p. ej. 2020-2025 completo) consulta las dos y concatena. Agregar un año
# futuro es añadir una línea aquí (p. ej. SORIANA_2026_PROJECTS -> 2026).
#
# ⚠️ NO AMPLIAR el rango de SORIANA_2025_PROJECTS. Esa base *también* devuelve renglones
# de 2022-2024, pero esos años **están incompletos** ahí (confirmado por Óscar el
# 2026-07-24). La fuente de verdad de todo lo anterior a 2025 es SORIANA_PROJECTS.
# Ampliar el rango no solo duplicaría renglones: metería datos parciales.
FUENTES_COMPRAS = [
    (config.DB_NAME, 2020, 2024),
    (config.DB_NAME_2025, 2025, 2025),
]


LOTE_LECTURA = 100_000


def _query_fuente(
    database: str, vendor: str, start_date: str, end_date: str, filtro_filas: str = ""
) -> pd.DataFrame:
    """Consulta F_COMPRAS en UNA base (nombre calificado a 3 partes).

    Lee en lotes: un `fetchall()` de un proveedor de más de un millón de renglones
    mantenía viva la lista completa de filas de pyodbc *además* del DataFrame ya armado,
    duplicando el pico de memoria justo al arrancar el pipeline.

    `filtro_filas` es un predicado SQL opcional (sin la palabra WHERE) que se aplica sobre
    el resultado de la función; p. ej. `"rcvnbr IS NOT NULL"` para dejar solo los renglones
    con nota de entrada (los únicos auditables). No se pasa por parámetro porque es SQL
    controlado internamente, nunca entrada del usuario.
    """
    where = f" WHERE {filtro_filas}" if filtro_filas else ""
    query = f"SELECT * FROM {database}.dbo.F_COMPRAS(?, ?, ?){where};"
    conn_str = config.get_connection_string()
    bloques: list[pd.DataFrame] = []
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute(query, vendor, start_date, end_date)
        columns = [column[0] for column in cursor.description]
        while True:
            filas = cursor.fetchmany(LOTE_LECTURA)
            if not filas:
                break
            bloques.append(pd.DataFrame.from_records(filas, columns=columns))
            del filas

    if not bloques:
        return pd.DataFrame(columns=columns)
    if len(bloques) == 1:
        return bloques[0]
    return pd.concat(bloques, ignore_index=True)


def fetch_compras(
    vendor: str, start_date: str, end_date: str, *, filtro_filas: str = ""
) -> pd.DataFrame:
    """Trae las compras del proveedor en el periodo, uniendo las fuentes por año.

    Si el periodo abarca 2020-2024 y 2025, se consultan las dos bases (cada una
    recortada a su rango de años) y se concatena. Si solo toca una, se hace una
    sola consulta.

    `filtro_filas` es un predicado SQL opcional (sin WHERE) para reducir renglones en el
    servidor; p. ej. `"rcvnbr IS NOT NULL"` cuando solo interesan los auditables.
    """
    inicio = pd.to_datetime(start_date).date()
    fin = pd.to_datetime(end_date).date()

    partes: list[pd.DataFrame] = []
    for database, anio_ini, anio_fin in FUENTES_COMPRAS:
        # Intersección del periodo pedido con el rango de años de esta fuente.
        desde = max(inicio, date(anio_ini, 1, 1))
        hasta = min(fin, date(anio_fin, 12, 31))
        if desde > hasta:
            continue  # esta base no aporta nada al periodo
        partes.append(
            _query_fuente(database, vendor, desde.isoformat(), hasta.isoformat(), filtro_filas)
        )

    if not partes:
        return pd.DataFrame()
    # concat conserva las columnas aunque alguna parte venga vacía.
    return pd.concat(partes, ignore_index=True)


def contar_compras(vendor: str, start_date: str, end_date: str) -> int:
    """Cuenta los renglones del proveedor en el periodo, SIN traerlos a memoria.

    Sirve para decidir si un proveedor cabe en memoria (camino normal) o hay que
    procesarlo por intervalos (pipeline por año). Ejecuta la función en el servidor y
    devuelve solo el número; es barato (segundos) aunque el proveedor sea enorme.
    """
    inicio = pd.to_datetime(start_date).date()
    fin = pd.to_datetime(end_date).date()
    total = 0
    conn_str = config.get_connection_string()
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        for database, anio_ini, anio_fin in FUENTES_COMPRAS:
            desde = max(inicio, date(anio_ini, 1, 1))
            hasta = min(fin, date(anio_fin, 12, 31))
            if desde > hasta:
                continue
            query = f"SELECT COUNT(*) FROM {database}.dbo.F_COMPRAS(?, ?, ?);"
            cursor.execute(query, vendor, desde.isoformat(), hasta.isoformat())
            total += int(cursor.fetchone()[0])
    return total


def test_connection() -> None:
    conn_str = config.get_connection_string()
    with pyodbc.connect(conn_str, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
