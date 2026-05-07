from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import config


EXCEL_EPOCH = datetime(1899, 12, 30)


def clean_code(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def to_number(series: pd.Series | Any, default: float = 0.0) -> pd.Series | float:
    if isinstance(series, pd.Series):
        return pd.to_numeric(series, errors="coerce").fillna(default)
    value = pd.to_numeric(pd.Series([series]), errors="coerce").iloc[0]
    if pd.isna(value):
        return default
    return float(value)


def excel_serial_to_datetime(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if isinstance(value, (int, float)) and value > 20000:
        return EXCEL_EPOCH + pd.to_timedelta(value, unit="D")
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return value
    return parsed.to_pydatetime()


def normalize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    date_columns = [
        "podt",
        "rcvdt",
        "invdt",
        "paychkdt",
        "payinvdt",
        "invdt_ne",
        "paychkdt_ne",
    ]
    for column in date_columns:
        if column in df.columns:
            df[column] = df[column].apply(excel_serial_to_datetime)
    return df


def make_folio(tienda: Any, nota_entrada: Any) -> str:
    tienda_text = clean_code(tienda).zfill(4)[-4:]
    nota_text = clean_code(nota_entrada).zfill(8)[-8:]
    return f"{config.FOLIO_PREFIX}{tienda_text}{nota_text}"


def safe_filename(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "salida"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
