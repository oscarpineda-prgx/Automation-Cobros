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


DATE_COLUMNS = [
    "podt",
    "rcvdt",
    "invdt",
    "paychkdt",
    "payinvdt",
    "invdt_ne",
    "paychkdt_ne",
]


def normalize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    for column in DATE_COLUMNS:
        if column in df.columns:
            df[column] = _normalize_date_series(df[column])
    return df


def _normalize_date_series(series: pd.Series) -> pd.Series:
    """Convierte una columna a fechas sin recorrerla celda a celda.

    Deja `datetime64` cuando todos los valores parsean (8 bytes por celda en vez de un
    objeto de Python por celda) y solo cae a `object` si hay valores que no son fecha,
    para no perderlos —igual que hacía `excel_serial_to_datetime` renglón por renglón.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    # Seriales de Excel: los valores numéricos > 20000, como en la versión escalar.
    numerico = pd.to_numeric(series, errors="coerce")
    es_serial = numerico.notna() & (numerico > 20000)

    fechas = pd.to_datetime(series.where(~es_serial), errors="coerce")
    if es_serial.any():
        seriales = EXCEL_EPOCH + pd.to_timedelta(numerico.where(es_serial), unit="D")
        fechas = fechas.where(~es_serial, seriales)

    # Lo que no es fecha ni serial se conserva tal cual, igual que la versión escalar.
    perdidos = fechas.isna() & series.notna() & ~es_serial
    if not perdidos.any():
        return fechas
    return fechas.astype(object).mask(perdidos, series)


def make_folio(tienda: Any, nota_entrada: Any) -> str:
    tienda_text = clean_code(tienda).zfill(4)[-4:]
    nota_text = clean_code(nota_entrada).zfill(8)[-8:]
    return f"{config.FOLIO_PREFIX}{tienda_text}{nota_text}"


def clean_code_series(series: pd.Series) -> pd.Series:
    """Versión vectorizada de `clean_code` para una columna entera.

    Equivalente celda a celda, pero sin el bucle de Python: con proveedores de más de un
    millón de renglones el `for` construía listas de strings que disparaban la memoria.
    """
    text = series.astype(str).str.strip()
    text = text.str.replace(r"^(-?\d+)\.0$", r"\1", regex=True)
    return text.mask(series.isna(), "")


def make_folio_series(tienda: pd.Series, nota_entrada: pd.Series) -> pd.Series:
    """Versión vectorizada de `make_folio`. Mismo formato: prefijo + tienda(4) + nota(8)."""
    tienda_text = clean_code_series(tienda).str.zfill(4).str[-4:]
    nota_text = clean_code_series(nota_entrada).str.zfill(8).str[-8:]
    return config.FOLIO_PREFIX + tienda_text + nota_text


def safe_filename(text: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "salida"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
