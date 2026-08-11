from __future__ import annotations

from pathlib import Path

import pandas as pd

from automation_costos.calculations import prepare_compras_dataframe
from automation_costos.excel_exporter import write_compras_workbook


def read_compras_workbook(path: Path) -> pd.DataFrame:
    """Lee el Compras completo, uniendo TODAS sus hojas de datos.

    El Compras se guarda con una hoja por año ("Compras 2020", "Compras 2021", ...) —y un
    año enorme puede partirse ademas en "Compras 2020 (2)"—, asi que hay que leerlas todas
    y concatenarlas; leer solo la primera perderia renglones. Se excluye "Pendientes_EDI".
    """
    path = Path(path)
    hojas = _hojas_de_compras(path)
    libro = pd.read_excel(path, sheet_name=hojas, header=6, engine="openpyxl")
    partes = [libro[nombre] for nombre in hojas]
    df = pd.concat(partes, ignore_index=True) if len(partes) > 1 else partes[0]

    df = df.dropna(how="all")
    df.columns = [str(column).strip() for column in df.columns]
    unnamed = [column for column in df.columns if column.startswith("Unnamed:")]
    if unnamed:
        df = df.drop(columns=unnamed)
    return df


def _hojas_de_compras(path: Path) -> list[str]:
    """Nombres de las hojas de datos del Compras (las "Compras*"), en orden del libro.

    Excluye "Pendientes_EDI". Si por alguna razon no hubiera hojas con ese prefijo (un
    archivo con otro formato), cae a todas menos "Pendientes_EDI" para no quedarse sin nada.
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        nombres = list(wb.sheetnames)
    finally:
        wb.close()
    compras = [n for n in nombres if str(n).startswith("Compras")]
    if compras:
        return compras
    return [n for n in nombres if n != "Pendientes_EDI"] or nombres


def recalculate_compras_file(input_path: Path, output_path: Path) -> Path:
    df = read_compras_workbook(input_path)
    recalculated = prepare_compras_dataframe(df)
    return write_compras_workbook(recalculated, output_path)
