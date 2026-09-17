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
    COLUMNAS_AUDITOR,
    COMPRAS_COLUMNS,
    EDI_COLUMNS,
    apply_display_formula_values,
    build_pending_edi_dataframe,
    prepare_compras_dataframe,
)
from automation_costos.utils import (
    anios_de_compras,
    clean_code,
    ensure_parent,
    formatear_periodo,
)

# Columnas de TRABAJO: se siguen calculando (el pipeline y el agrupado por año dependen de
# varias) pero NO se escriben en el archivo. Son intermedias del cálculo —restos de cuando
# el Excel llevaba fórmulas— y para el auditor solo son ruido: `imp_aud`, `debio_pagar_ne`
# y compañía ya dicen lo mismo en las columnas que sí se entregan.
#
# Recortar aquí y no en `COMPRAS_COLUMNS` es deliberado: `concaten` agrupa las hojas por año
# y `dpagar` alimenta el debió-pagar por folio. Si se dejaran de calcular, se romperían.
COLUMNAS_INTERNAS = (
    "concaten",
    "fante",
    "facdecto",
    "ctouni_sistema",
    "ctontol",
    "impaud",
    "dpagar",
    "imp",
    "dif cto fac ctouni",
    "ctontopza",
)

# Lo que realmente se entrega, en el mismo orden que traía COMPRAS_COLUMNS.
COLUMNAS_SALIDA = [c for c in COMPRAS_COLUMNS if c not in COLUMNAS_INTERNAS]

HEADER_ROW = 6  # 0-indexed (fila 7 en Excel)
DATA_ROW = 7  # 0-indexed (fila 8 en Excel)
SHEET_ROW_LIMIT = 1_048_576  # tope duro de filas por hoja en Excel

# Arriba de este numero de renglones, el Compras se parte en UN ARCHIVO POR AÑO
# (Compras_<base>_2020.xlsx, ...) en vez de un solo archivo gigante. Los proveedores
# chicos siguen en un unico archivo con hojas por año. Decision de Oscar (2026-07-24).
UMBRAL_PARTIR_POR_ANIO = 1_000_000

_HEADER_BG = "#00FD28"
_TITLE_COLOR = "#000000"

# --- El codigo de color del Compras (acordado con Monica, 2026-09-11) -----------------
#
# El color dice QUE SE HACE con cada columna, y esa es toda su razon de ser:
#
#   verde oscuro  -> DATO DE ORIGEN. Viene del sistema y de CPA Vision. **No se edita**:
#                    lo que el cruce rellena se queda como esta y el resto tal cual vino.
#   piel          -> LO QUE EDITA EL AUDITOR. Son las tres columnas auditadas.
#   verde claro   -> RESULTADO. Se recalcula solo a partir de las de color piel.
#
# Antes el piel estaba en el bloque EDI, que es justo lo que el auditor NO toca: invitaba
# a corregir el dato de origen en vez del criterio de auditoria.
_EDI_BG = "#375623"          # verde oscuro: dato de origen, no se edita
_EDI_FONT = "#FFFFFF"        # sobre verde oscuro, el texto negro no se lee
_AUDITOR_BG = "#FFF2CC"      # piel: lo que edita el auditor
_AUDIT_BG = "#E2F0D9"        # verde claro: resultado calculado

#: Las tres que edita el auditor. La lista vive en `calculations` porque es una regla de
#: negocio, no una decision de presentacion; aqui solo se pinta.
_AUDITOR_COLS = frozenset(COLUMNAS_AUDITOR)

#: El resultado: de `imp_aud` a `dif_det_inv`. Se recalcula siempre a partir de las de
#: color piel, asi que editarlas a mano no sirve de nada.
_AUDIT_COLS = frozenset({
    "imp_aud",
    "debio_pagar_ne", "dif_det_ne", "debio_pagar_inv", "tot_pagado_inv", "dif_det_inv",
})

_WIDTHS = {
    "cnpj": 16, "vndnbr": 10, "vndname": 28, "ponbr": 14, "podt": 12,
    "rcvnbr": 12, "rcvdt": 12, "strnbr": 12, "invnbr": 18, "itmdesc": 34,
    "uuid": 36, "txt_cabec": 24, "txt_item": 24,
}

# --- Formato numerico de la hoja (peticion de Monica, 2026-08-27) ---------------------
# Los valores se escriben como numeros crudos y Excel los mostraba en "General": de ahi
# salian `21.000000000`, `345.120000000` y `2E+06`. El formato se aplica por COLUMNA (con
# `set_column`), no celda por celda: xlsxwriter en modo `constant_memory` escribe en
# streaming y un formato por celda multiplicaria la memoria justo en los proveedores
# grandes. El dato guardado NO cambia — solo cambia como se ve.
_FMT_MONTO = "#,##0.00"      # dinero y costos: dos decimales, con separador de miles
_FMT_TASA = "0.######"       # tasas y factores: sin ceros de relleno (0.16, 0.265)
_FMT_CANTIDAD = "#,##0.##"   # piezas/cajas: 21 se ve 21, no 21.000000000
_FMT_ENTERO = "0"            # folios numericos: evita la notacion cientifica (2E+06)

_COLS_MONTO = frozenset({
    "poitmgrscst", "poitmnetcst", "ctouni",
    "compra_bruta", "compra_bruta mas impuestos", "compra_neta", "compra neta mas impuestos",
    "ctobto_edi", "ctonto_edi", "impart_edi", "imieps_edi", "impiva_edi", "totfactura",
    "cto_aud", "imp_aud",
    "debio_pagar_ne", "dif_det_ne", "debio_pagar_inv", "tot_pagado_inv", "dif_det_inv",
    "paynetamt", "tot_pagado_ne",
})

# Tasas y factores de descuento: NO llevan dos decimales. Un IEPS de 0.265 redondeado a
# 0.27 cambiaria el impuesto calculado a la vista del auditor.
_COLS_TASA = frozenset({
    "ieps_t007s", "iva_t007s", "prieps_edi", "poriva_edi", "iva_aud", "ieps_aud",
    "nor1_konv", "nor2_konv", "nor3_konv", "nor4_konv",
    "adi1_konv", "adi2_konv", "adi3_konv",
    "bonif1_konv", "bonif2_konv", "bonif3_konv", "bonif4_konv", "bonif5_konv",
    "pp_konv", "cen_konv", "porccargo_konv", "fact_desct",
})

_COLS_CANTIDAD = frozenset({
    "fact_empaq", "poitmcspck", "poqty", "rcvqty", "invqty", "can_rec",
    "canfac_edi", "factem_edi",
})

_COLS_ENTERO = frozenset({"vndnbr", "dptnbr", "ponbr", "rcvnbr", "strnbr"})


def _formato_columna(wb, column: str):
    """Formato de presentacion de una columna, o `None` si va tal cual (texto/fecha)."""
    for grupo, codigo in (
        (_COLS_MONTO, _FMT_MONTO), (_COLS_TASA, _FMT_TASA),
        (_COLS_CANTIDAD, _FMT_CANTIDAD), (_COLS_ENTERO, _FMT_ENTERO),
    ):
        if column in grupo:
            return wb.add_format({"num_format": codigo})
    return None


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


def write_compras_cruzado(
    df: pd.DataFrame,
    output_path: Path,
    *,
    vendor: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Path:
    """Escribe el resultado del cruce CPA como un **Compras de verdad**, no como un volcado.

    Es el punto UNICO de escritura del paso "Rellenar EDI con los CFDI", y lo comparten la
    interfaz y el subcomando `cpa-cruce` para que no puedan volver a separarse.

    **Por que existe.** Los dos escribian con `DataFrame.to_excel(index=False)`: hoja
    "Sheet1", encabezados en la fila 1 y sin formato. Pero un Compras tiene el titulo
    arriba, los **encabezados en la fila 7** y una hoja por año llamada "Compras <año>", que
    es justo lo que `recalculate.read_compras_workbook` busca al releerlo. Resultado medido
    el 2026-09-11 sobre un archivo de 10 renglones: el recalculo tomaba el **renglon 6 como
    encabezado**, devolvia 4 renglones y las columnas salian con nombres inventados
    (`cnpj5`, `5`, `vndname5`). La cadena paso 3 -> paso 4 estaba rota y **no avisaba**:
    producia un archivo que parecia valido.

    Solo se notaba haciendo el cruce por separado. `generar_salida_proveedor` ("GENERAR
    TODO") nunca paso por aqui porque cruza en memoria y escribe el Compras una sola vez.

    El proveedor del titulo se deduce del propio DataFrame cuando no se indica: quien cruza
    un archivo suelto no tiene por que volver a teclear de quien es.
    """
    if not vendor:
        vendor = _vendor_del_dataframe(df)
    return write_compras_workbook(df, output_path, vendor, start_date, end_date)


def _vendor_del_dataframe(df: pd.DataFrame) -> str | None:
    """Numero de proveedor tomado de la columna `vndnbr`, o None si no se puede saber."""
    if "vndnbr" in df.columns and df["vndnbr"].notna().any():
        return clean_code(df["vndnbr"].dropna().iloc[0]) or None
    return None


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
    # El periodo se calcula UNA vez sobre el libro completo. La hoja con titulo es la primera
    # (un solo año cuando se parte por años), asi que derivarlo del chunk anunciaria "2020"
    # en un archivo que lleva 2020-2025.
    periodo = formatear_periodo(anios_de_compras(df))
    if not len(df):
        _write_compras_sheet(wb, df, vendor, start_date, end_date, name="Compras", with_title=True, periodo=periodo)
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
                wb, chunk, vendor, start_date, end_date, name=nombre, with_title=primero,
                periodo=periodo,
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
    wb, df, vendor, start_date, end_date, *, name="Compras", with_title=True, periodo: str = ""
) -> None:
    ws = wb.add_worksheet(name)
    ws.hide_gridlines(2)
    ws.freeze_panes(DATA_ROW, 0)

    title = wb.add_format({"bold": True, "font_size": 14, "align": "center", "font_color": _TITLE_COLOR})
    hdr = wb.add_format({"bold": True, "bg_color": _HEADER_BG, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    hdr_edi = wb.add_format({"bold": True, "bg_color": _EDI_BG, "font_color": _EDI_FONT, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    hdr_auditor = wb.add_format({"bold": True, "bg_color": _AUDITOR_BG, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    hdr_aud = wb.add_format({"bold": True, "bg_color": _AUDIT_BG, "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})

    # Logo + titulo (solo en la primera hoja)
    if with_title:
        _add_logo(ws)
        vendor_name = _first(df, "vndname")
        vendor_code = vendor or _first(df, "vndnbr")
        ws.merge_range(1, 3, 1, 11, "Tiendas Soriana, S.A. de C.V.", title)
        ws.merge_range(2, 3, 2, 11, f"{vendor_code} - {vendor_name}".strip(" -"), title)
        # Manda el periodo REAL de los renglones; el rango pedido a SQL es solo respaldo
        # (puede abarcar años que el plan recorto o que el proveedor no tuvo movimientos).
        etiqueta = periodo or _period_label(start_date, end_date)
        ws.merge_range(3, 3, 3, 11, f"Compras Periodo {etiqueta}", title)

    # Encabezados de columna (con resaltado EDI/auditoria)
    # Los formatos numericos se crean UNA vez por libro y se reusan entre hojas: un
    # `add_format` por columna y por hoja dejaria cientos de objetos equivalentes.
    if not hasattr(wb, "_fmt_numeros"):
        wb._fmt_numeros = {c: _formato_columna(wb, c) for c in COLUMNAS_SALIDA}

    for col_idx, column in enumerate(COLUMNAS_SALIDA):
        # El orden importa: primero lo que se edita, luego el origen, luego el resultado.
        formato = (
            hdr_auditor if column in _AUDITOR_COLS
            else hdr_edi if column in EDI_COLUMNS
            else hdr_aud if column in _AUDIT_COLS
            else hdr
        )
        ws.write(HEADER_ROW, col_idx, column, formato)
        ws.set_column(col_idx, col_idx, _WIDTHS.get(column, 13), wb._fmt_numeros.get(column))

    # Datos como valores, en streaming. Se recorta por POSICION en cada renglon en vez de
    # hacer `df[COLUMNAS_SALIDA]`: esa seleccion consolidaria bloques y copiaria millones de
    # renglones en los proveedores grandes, que es justo lo que este camino evita.
    posiciones = [df.columns.get_loc(c) for c in COLUMNAS_SALIDA if c in df.columns]
    _write_rows(ws, df, start_row=DATA_ROW, posiciones=posiciones)

    if len(df):
        ws.autofilter(HEADER_ROW, 0, HEADER_ROW + len(df), len(COLUMNAS_SALIDA) - 1)


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


def _write_rows(
    ws, df: pd.DataFrame, *, start_row: int, posiciones: list[int] | None = None
) -> None:
    """Escribe los valores del DataFrame fila por fila, saneando NaN a celda vacía.

    Con `posiciones` se escriben solo esas columnas (por índice), sin materializar una
    proyección del DataFrame.
    """
    for offset, row in enumerate(df.itertuples(index=False, name=None)):
        datos = row if posiciones is None else [row[i] for i in posiciones]
        ws.write_row(start_row + offset, 0, [_clean(v) for v in datos])


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
