from __future__ import annotations

from pathlib import Path

import pandas as pd

from automation_cobros.calculations import prepare_compras_dataframe
from automation_cobros.excel_exporter import write_compras_workbook


def read_compras_workbook(path: Path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_excel(path, sheet_name="Compras", header=6, engine="openpyxl")
    df = df.dropna(how="all")
    df.columns = [str(column).strip() for column in df.columns]
    unnamed = [column for column in df.columns if column.startswith("Unnamed:")]
    if unnamed:
        df = df.drop(columns=unnamed)
    return df


def recalculate_compras_file(input_path: Path, output_path: Path) -> Path:
    df = read_compras_workbook(input_path)
    recalculated = prepare_compras_dataframe(df)
    return write_compras_workbook(recalculated, output_path)
