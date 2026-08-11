from __future__ import annotations

from datetime import date

import pandas as pd
import pyodbc

import config


# F_COMPRAS está partido por año en dos bases del MISMO servidor:
#   SORIANA_PROJECTS       -> compras 2020-2024
#   SORIANA_2025_PROJECTS  -> compras 2025 y 2026 (ver abajo)
# Cada fuente cubre un rango de años cerrado. Un periodo que cruce el límite
# (p. ej. 2020-2025 completo) consulta las dos y concatena. Agregar un año
# futuro es añadir una línea aquí (p. ej. SORIANA_2026_PROJECTS -> 2027).
#
# El periodo "2025" de la auditoría incluye el arrastre a 2026 (facturas tardías y pagos con
# plazo hasta 90 días). SORIANA_2025_PROJECTS trae 2026 cargado hasta ~marzo-2026 (corte
# actual), así que su límite superior se extiende a 2026 y la ejecución usa `--end 2026-03-31`
# (reunión con Mónica, 2026-08-05). No duplica años: 2020-2024 sigue viniendo de la otra base.
#
# ⚠️ NO AMPLIAR el límite INFERIOR de SORIANA_2025_PROJECTS por debajo de 2025. Esa base
# *también* devuelve renglones de 2022-2024, pero esos años **están incompletos** ahí
# (confirmado por Óscar el 2026-07-24). La fuente de verdad de todo lo anterior a 2025 es
# SORIANA_PROJECTS. El límite superior (2026) sí es seguro: 2026 no existe en ninguna otra base.
FUENTES_COMPRAS = [
    (config.DB_NAME, 2020, 2024),
    (config.DB_NAME_2025, 2025, 2026),
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


def resolver_rfc(vendor: str, start_date: str, end_date: str) -> str:
    """Devuelve el RFC del proveedor leyendo un solo renglón de F_COMPRAS.

    El RFC vive en la columna `cnpj` del Compras; para descargar de CPA Vision hace falta
    ese RFC pero no todo el archivo. Un `SELECT TOP (1)` sobre la función es barato (segundos)
    y evita traer las compras completas solo para conocer el RFC. Recorre las fuentes por año
    y devuelve el primero que encuentre; cadena vacía si el proveedor no tiene compras.
    """
    inicio = pd.to_datetime(start_date).date()
    fin = pd.to_datetime(end_date).date()
    conn_str = config.get_connection_string()
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        for database, anio_ini, anio_fin in FUENTES_COMPRAS:
            desde = max(inicio, date(anio_ini, 1, 1))
            hasta = min(fin, date(anio_fin, 12, 31))
            if desde > hasta:
                continue
            query = (
                f"SELECT TOP (1) cnpj FROM {database}.dbo.F_COMPRAS(?, ?, ?) "
                f"WHERE cnpj IS NOT NULL;"
            )
            cursor.execute(query, vendor, desde.isoformat(), hasta.isoformat())
            row = cursor.fetchone()
            if row and row[0]:
                return str(row[0]).strip()
    return ""


def test_connection() -> None:
    conn_str = config.get_connection_string()
    with pyodbc.connect(conn_str, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
