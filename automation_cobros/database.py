from __future__ import annotations

import pandas as pd
import pyodbc

import config


def fetch_compras(vendor: str, start_date: str, end_date: str) -> pd.DataFrame:
    query = "SELECT * FROM dbo.F_COMPRAS(?, ?, ?);"
    conn_str = config.get_connection_string()
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute(query, vendor, start_date, end_date)
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


def test_connection() -> None:
    conn_str = config.get_connection_string()
    with pyodbc.connect(conn_str, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
