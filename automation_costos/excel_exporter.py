"""Generación del Excel de Compras.

Escribe con **xlsxwriter** y en modo `constant_memory`, que serializa las filas al vuelo
en streaming. openpyxl tardaba minutos en guardar cientos de miles de filas (la
serialización XML es su cuello de botella); xlsxwriter lo hace en segundos.

Las columnas que antes eran fórmulas vivas de Excel ahora se calculan como **valores** en
Python (`apply_display_formula_values`). Eso quita el tope del VLOOKUP y evita que Excel se
congele al abrir archivos con millones de fórmulas. Si el auditor edita algo, recalcula con
el botón "Recalcular" (que corre en Python).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import xlsxwriter

import config
from automation_costos.calculations import (
    COMPRAS_COLUMNS,
    EDI_COLUMNS,
    apply_display_formula_values,
    build_pending_edi_dataframe,
    prepare_compras_dataframe,
)
from automation_costos.utils import ensure_parent

HEADER_ROW = 6  # 0-indexed (fila 7 en Excel)
DATA_ROW = 7  # 0-indexed (fila 8 en Excel)
SHEET_ROW_LIMIT = 1_048_576  # tope duro de filas por hoja en Excel

# Arriba de este numero de renglones, el Compras se parte en UN ARCHIVO POR AÑO
# (Compras_<base>_2020.xlsx, ...) en vez de un solo archivo gigante. Los proveedores
# chicos siguen en un unico archivo con hojas por año. Decision de Oscar (2026-07-24).
UMBRAL_PARTIR_POR_ANIO = 1_000_000

_HEADER_BG = "#00FD28"
_AUDIT_BG = "#E2F0D9"
_EDI_BG = "#FFF2CC"
_TITLE_COLOR = "#000000"

_AUDIT_COLS = frozenset({
    "cto_aud", "iva_aud", "ieps_aud", "imp_aud",
    "debio_pagar_ne", "dif_det_ne", "debio_pagar_inv", "tot_pagado_inv", "dif_det_inv",
})

_WIDTHS = {
    "cnpj": 16, "vndnbr": 10, "vndname": 28, "ponbr": 14, "podt": 12,
    "rcvnbr": 12, "rcvdt": 12, "strnbr": 12, "invnbr": 18, "itmdesc": 34,
    "uuid": 36, "txt_cabec": 24, "txt_item": 24,
}


def write_compras_workbook(
    df: pd.DataFrame,
    output_path: Path,
    vendor: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    already_prepared: bool = False,
) -> Path:
    """Escribe el Compras. `already_prepared=True` evita recalcular `prepare_compras_dataframe`
    cuando quien llama ya lo hizo (lo usa el pipeline para no preparar dos veces).

    Con `already_prepared=True` el DataFrame recibido se **muta**: las columnas de fórmula
    se calculan en sitio para no duplicar la tabla en proveedores de más de un millón de
    renglones. Quien llama lo comparte a sabiendas (el pipeline reusa el mismo objeto para
    la Validación, y ahí los valores de fórmula ya calculados son los correctos).
    """
    output_path = Path(output_path)
    ensure_parent(output_path)
    prepared = _preparar_para_escritura(df, already_prepared)
    _escribir_libro(output_path, prepared, vendor, start_date, end_date)
    return output_path


def write_compras_files(
    df: pd.DataFrame,
    proveedor_dir: Path,
    base: str,
    vendor: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    already_prepared: bool = False,
) -> list[Path]:
    """Escribe el/los Compras de un proveedor y devuelve las rutas escritas.

    - Proveedor chico (hasta `UMBRAL_PARTIR_POR_ANIO` renglones): **un solo archivo**
      `Compras_<base>.xlsx` con una hoja por año.
    - Proveedor grande: **un archivo por año**, `Compras_<base>_2020.xlsx`, ..., cada uno
      con su propio `Pendientes_EDI` de ese año. Se corta en limites de año, asi que una
      nota de entrada (un recibo, una fecha) nunca queda partida entre archivos: esto es
      solo como se reparte la salida, no cambia ningun calculo.
    """
    proveedor_dir = Path(proveedor_dir)
    proveedor_dir.mkdir(parents=True, exist_ok=True)
    prepared = _preparar_para_escritura(df, already_prepared)

    if len(prepared) <= UMBRAL_PARTIR_POR_ANIO:
        ruta = proveedor_dir / f"Compras_{base}.xlsx"
        _escribir_libro(ruta, prepared, vendor, start_date, end_date)
        return [ruta]

    rutas: list[Path] = []
    for etiqueta, posiciones in _grupos_por_anio(prepared):
        sufijo = etiqueta if etiqueta is not None else "sin_fecha"
        ruta = proveedor_dir / f"Compras_{base}_{sufijo}.xlsx"
        _escribir_libro(ruta, prepared.take(posiciones), vendor, start_date, end_date)
        rutas.append(ruta)
    return rutas


def _preparar_para_escritura(df: pd.DataFrame, already_prepared: bool) -> pd.DataFrame:
    """Deja el DataFrame con las 105 columnas y los valores de formula ya calculados."""
    prepared = df if already_prepared else prepare_compras_dataframe(df)
    prepared = apply_display_formula_values(prepared, en_sitio=already_prepared)
    if list(prepared.columns) != COMPRAS_COLUMNS:
        prepared = prepared[COMPRAS_COLUMNS]
    return prepared


def escribir_libro_compras(
    output_path: Path,
    prepared_display: pd.DataFrame,
    vendor: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Path:
    """Escribe UN .xlsx de Compras a partir de un DataFrame **ya preparado y con los valores
    de fórmula aplicados** (no vuelve a prepararlo ni a aplicar `apply_display_formula_values`).

    Lo usa el pipeline por intervalos (proveedores grandes), que prepara cada año por
    separado y ya trae los valores de fórmula calculados. Reutiliza exactamente la misma
    escritura de hojas por año + Pendientes_EDI que el camino normal."""
    output_path = Path(output_path)
    if list(prepared_display.columns) != COMPRAS_COLUMNS:
        prepared_display = prepared_display[COMPRAS_COLUMNS]
    _escribir_libro(output_path, prepared_display, vendor, start_date, end_date)
    return output_path


def _escribir_libro(output_path, prepared, vendor, start_date, end_date) -> None:
    """Abre un .xlsx y escribe las hojas de Compras (por año) + `Pendientes_EDI` del
    `prepared` dado. Si algo falla, borra el archivo trunco en vez de dejar una salida
    a medias que parezca buena."""
    output_path = Path(output_path)
    ensure_parent(output_path)
    pending = build_pending_edi_dataframe(prepared)

    # use_zip64: el Compras de un proveedor de más de un millón de renglones rebasa los
    # límites del ZIP clásico y xlsxwriter aborta con FileSizeError al cerrar el libro.
    wb = xlsxwriter.Workbook(str(output_path), {"constant_memory": True, "use_zip64": True})
    try:
        _write_compras_sheets(wb, prepared, vendor, start_date, end_date)
        _write_pending_sheet(wb, pending)
        wb.close()
    except BaseException:
        try:
            wb.close()
        except BaseException:
            pass
        output_path.unlink(missing_ok=True)
        raise


def _write_compras_sheets(wb, df, vendor, start_date, end_date) -> None:
    """Escribe el Compras con **una hoja por año** (segun `rcvdt`): "Compras 2020",
    "Compras 2021", ...

    Si un año pasa del tope de filas de Excel, ese año se parte en "Compras 2020 (2)", etc.
    Cada renglon se conserva: nada se descarta en silencio. La primera hoja lleva el
    titulo/logo; las demas solo encabezado y datos.

    El agrupado por año es **solo presentacion**: reordena en que hoja cae cada renglon,
    pero no cambia ningun valor calculado (los calculos ya vienen hechos por renglon y por
    grupo). El reparto de los renglones sin fecha se explica en `_anio_agrupacion`.
    """
    capacidad = SHEET_ROW_LIMIT - DATA_ROW  # filas de datos que caben tras titulo + encabezado
    if not len(df):
        _write_compras_sheet(wb, df, vendor, start_date, end_date, name="Compras", with_title=True)
        return

    primero = True
    for etiqueta, posiciones in _grupos_por_anio(df):
        grupo = df.take(posiciones)  # .take respeta el orden original de las filas
        partes = max(1, math.ceil(len(grupo) / capacidad))
        for parte in range(partes):
            chunk = grupo.iloc[parte * capacidad:(parte + 1) * capacidad] if partes > 1 else grupo
            base = "Compras" if etiqueta is None else f"Compras {etiqueta}"
            # 1er pedazo sin sufijo ("Compras 2020"); los siguientes "(2)", "(3)"...
            nombre = base if parte == 0 else f"{base} ({parte + 1})"
            _write_compras_sheet(
                wb, chunk, vendor, start_date, end_date, name=nombre, with_title=primero
            )
            primero = False


def _grupos_por_anio(df):
    """Genera pares (etiqueta_de_año, posiciones) en orden de año ascendente.

    `posiciones` son indices posicionales (0..n-1) en el orden original de `df`, de modo
    que dentro de cada hoja las filas quedan como venian. La etiqueta es el año como texto,
    o `None` si —caso extremo, sin ninguna fecha en todo el proveedor— no se pudo
    determinar el año y todo va a una sola hoja "Compras".
    """
    anio = _anio_agrupacion(df).to_numpy()
    conocido = ~np.isnan(anio)
    for valor in sorted(np.unique(anio[conocido])):
        yield str(int(valor)), np.flatnonzero(anio == valor)
    resto = np.flatnonzero(~conocido)
    if resto.size:
        yield None, resto


def _anio_agrupacion(df) -> pd.Series:
    """Año de agrupacion de cada renglon, a partir de `rcvdt`.

    Los renglones sin fecha (NaT) **no** van a una hoja aparte: se les asigna el año de su
    MISMO grupo, para que caigan junto a los que les corresponden. En orden de preferencia:

    1. Por nota de entrada (`concaten`): una nota de entrada es un solo recibo con una sola
       fecha, asi que es la mejor coincidencia.
    2. Por factura (`invnbr`): si la nota de entrada no bastara.
    3. Por la fila vecina en el orden original (ffill/bfill), como ultimo recurso.

    Asi ningun renglon se pierde ni se aisla, y como esto solo decide en que hoja se
    muestra, no afecta ningun calculo.
    """
    if "rcvdt" not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")

    anio = pd.to_datetime(df["rcvdt"], errors="coerce").dt.year.astype("float64")
    for clave in ("concaten", "invnbr"):
        if not anio.isna().any():
            break
        if clave in df.columns:
            anio = anio.fillna(anio.groupby(df[clave]).transform("first"))
    if anio.isna().any():
        anio = anio.ffill().bfill()
    return anio


def _write_compras_sheet(
    wb, df, vendor, start_date, end_date, *, name="Compras", with_title=True
) -> None:
    ws = wb.add_worksheet(name)
    ws.hide_gridlines(2)
    ws.freeze_panes(DATA_ROW, 0)

    title = wb.add_format({"bold": True, "font_size": 14, "align": "center", "font_color": _TITLE_COLOR})
    hdr = wb.add_format({"bold": True, "bg_color": _HEADER_BG, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    hdr_edi = wb.add_format({"bold": True, "bg_color": _EDI_BG, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    hdr_aud = wb.add_format({"bold": True, "bg_color": _AUDIT_BG, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})

    # Logo + titulo (solo en la primera hoja)
    if with_title:
        _add_logo(ws)
        vendor_name = _first(df, "vndname")
        vendor_code = vendor or _first(df, "vndnbr")
        ws.merge_range(1, 3, 1, 11, "Tiendas Soriana, S.A. de C.V.", title)
        ws.merge_range(2, 3, 2, 11, f"{vendor_code} - {vendor_name}".strip(" -"), title)
        ws.merge_range(3, 3, 3, 11, f"Compras Periodo {_period_label(start_date, end_date)}", title)

    # Encabezados de columna (con resaltado EDI/auditoria)
    for col_idx, column in enumerate(COMPRAS_COLUMNS):
        formato = hdr_edi if column in EDI_COLUMNS else hdr_aud if column in _AUDIT_COLS else hdr
        ws.write(HEADER_ROW, col_idx, column, formato)
        ws.set_column(col_idx, col_idx, _WIDTHS.get(column, 13))

    # Datos como valores, en streaming.
    _write_rows(ws, df, start_row=DATA_ROW)

    if len(df):
        ws.autofilter(HEADER_ROW, 0, HEADER_ROW + len(df), len(COMPRAS_COLUMNS) - 1)


def _write_pending_sheet(wb, pending) -> None:
    ws = wb.add_worksheet("Pendientes_EDI")
    ws.hide_gridlines(2)
    aviso = wb.add_format({"bold": True, "font_color": "#9C5700"})
    ws.write(0, 0, "Registros con campos EDI vacios para complemento manual o CPA Vision", aviso)

    if pending is None or pending.empty:
        ws.write(2, 0, "No se detectaron pendientes EDI.")
        ws.set_column(0, 0, 80)
        return

    # Si el pendiente rebasa el tope de Excel, lo recortamos con aviso visible
    # (no lo dejamos caer en silencio).
    capacidad = SHEET_ROW_LIMIT - 3
    if len(pending) > capacidad:
        ws.write(
            1, 0,
            f"AVISO: {len(pending):,} pendientes; se muestran los primeros {capacidad:,} "
            "por el tope de Excel.",
            aviso,
        )
        pending = pending.iloc[:capacidad]

    hdr = wb.add_format({"bold": True, "bg_color": _HEADER_BG, "border": 1})
    for col_idx, column in enumerate(pending.columns):
        ws.write(2, col_idx, str(column), hdr)
        ws.set_column(col_idx, col_idx, max(12, min(36, len(str(column)) + 4)))
    _write_rows(ws, pending, start_row=3)
    ws.freeze_panes(3, 0)
    ws.autofilter(2, 0, 2 + len(pending), len(pending.columns) - 1)


def _write_rows(ws, df: pd.DataFrame, *, start_row: int) -> None:
    """Escribe los valores del DataFrame fila por fila, saneando NaN a celda vacía."""
    for offset, row in enumerate(df.itertuples(index=False, name=None)):
        ws.write_row(start_row + offset, 0, [_clean(v) for v in row])


def _clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "isoformat"):  # datetime/date
        return value.isoformat()[:10]
    return value


def _add_logo(ws) -> None:
    logo_path = config.RESOURCE_DIR / "templates" / "Soriana-Logo.png"
    if logo_path.exists():
        ws.insert_image(1, 0, str(logo_path), {"x_scale": 0.5, "y_scale": 0.5})


def _first(df: pd.DataFrame, column: str) -> str:
    if column in df.columns and df[column].notna().any():
        return str(df[column].dropna().iloc[0])
    return ""


def _period_label(start_date: str | None, end_date: str | None) -> str:
    if not start_date and not end_date:
        return ""
    start = str(start_date or "")[:4]
    end = str(end_date or "")[:4]
    parsed_end = pd.to_datetime(end_date, errors="coerce") if end_date else None
    parsed_start = pd.to_datetime(start_date, errors="coerce") if start_date else None
    if parsed_end is not None and not pd.isna(parsed_end) and parsed_end.month == 1 and parsed_end.day == 1:
        if parsed_start is None or pd.isna(parsed_start) or parsed_end.year > parsed_start.year:
            end = str(parsed_end.year - 1)
    if start and end and start != end:
        return f"{start}-{end}"
    return start or end
