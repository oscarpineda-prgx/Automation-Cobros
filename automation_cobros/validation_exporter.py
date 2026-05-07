from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config
from automation_cobros.recalculate import read_compras_workbook
from automation_cobros.calculations import prepare_compras_dataframe
from automation_cobros.utils import clean_code, ensure_parent, make_folio


TITLE_FONT = Font(bold=True, size=13, color="1F4E78")
HEADER_FILL = PatternFill("solid", fgColor="5B9BD5")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TOTAL_FILL = PatternFill("solid", fgColor="D9EAF7")
THIN_BORDER = Border(
    left=Side(style="thin", color="D9E2F3"),
    right=Side(style="thin", color="D9E2F3"),
    top=Side(style="thin", color="D9E2F3"),
    bottom=Side(style="thin", color="D9E2F3"),
)


CONSOLIDADO_COLUMNS = [
    "Proveedor",
    "Folio",
    "Tienda/CEDIS",
    "Negocio",
    "Fecha Pedido",
    "Pedido",
    "Fec Recibo",
    "Nota Entrada",
    "Factura",
    "Total Pagado",
    "Debio Pagar",
    "Diferencia",
    "Observaciones Auditor",
    "Fecha Pago",
    "Documento de Pago",
]

DETALLE_COLUMNS = [
    "Folio_Pedido",
    "FecPed",
    "Folio_NE",
    "FecRecibo",
    "Factura",
    "Tienda/CEDIS",
    "Division",
    "Categoria",
    "GciaCateg",
    "Material",
    "CodBarra",
    "Descripcion",
    "FactEmpaqu",
    "CantRec",
    "CtoUnitario_sistema",
    "Costo Unitario correcto",
    "Porc_IEPS",
    "IEPS_Aud",
    "Porc_IVA",
    "IVA_Aud",
    "Debio Pagar correcto",
]


def write_validation_workbook(compras_path: Path, output_path: Path) -> Path:
    compras_df = prepare_compras_dataframe(read_compras_workbook(compras_path))
    return write_validation_from_dataframe(compras_df, output_path)


def write_validation_from_dataframe(compras_df: pd.DataFrame, output_path: Path) -> Path:
    output_path = Path(output_path)
    ensure_parent(output_path)

    compras_df = compras_df.copy()
    if "folio" not in compras_df.columns:
        compras_df["folio"] = [
            make_folio(store, receipt)
            for store, receipt in zip(compras_df.get("strnbr", []), compras_df.get("rcvnbr", []))
        ]

    consolidated = build_consolidado(compras_df)
    detail = build_detalle(compras_df, consolidated["Folio"].tolist())

    wb = Workbook()
    resumen = wb.active
    resumen.title = "Resumen"
    ws_consolidado = wb.create_sheet("Consolidado")
    ws_detalle = wb.create_sheet("Detalle PAGOS")

    _write_resumen(resumen, compras_df, consolidated)
    _write_consolidado(ws_consolidado, compras_df, consolidated)
    _write_detalle(ws_detalle, compras_df, detail)

    wb.save(output_path)
    return output_path


def build_consolidado(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    threshold = config.VALIDATION_DIFFERENCE_THRESHOLD
    work["folio"] = [
        make_folio(store, receipt)
        for store, receipt in zip(work["strnbr"], work["rcvnbr"])
    ]

    sort_cols = [column for column in ["folio", "podt", "rcvdt", "invnbr"] if column in work.columns]
    if sort_cols:
        work = work.sort_values(sort_cols)

    use_concept_filter = _has_audit_concepts(work)
    grouped = work.groupby("folio", dropna=False)
    rows = []
    for folio, group in grouped:
        first = group.iloc[0]
        debio = _num(first.get("debio_pagar_ne"))
        total_pagado = _num(first.get("tot_pagado_ne"))
        diferencia = _num(first.get("dif_det_ne"))
        if use_concept_filter:
            concepts = group.get("concepto", pd.Series(dtype=str)).fillna("").astype(str).str.lower().str.strip()
            if not concepts.eq("dif costos").any():
                continue
        elif diferencia <= threshold:
            continue
        rows.append(
            {
                "Proveedor": clean_code(first.get("vndnbr")),
                "Folio": folio,
                "Tienda/CEDIS": clean_code(first.get("strnbr")),
                "Negocio": first.get("po_org") or "SORIANA",
                "Fecha Pedido": first.get("podt"),
                "Pedido": clean_code(first.get("ponbr")),
                "Fec Recibo": first.get("rcvdt"),
                "Nota Entrada": clean_code(first.get("rcvnbr")),
                "Factura": first.get("invnbr_ne") or first.get("invnbr"),
                "Total Pagado": total_pagado,
                "Debio Pagar": debio,
                "Diferencia": diferencia,
                "Observaciones Auditor": "",
                "Fecha Pago": first.get("paychkdt_ne"),
                "Documento de Pago": clean_code(first.get("paychknbr_ne")),
            }
        )
    return pd.DataFrame(rows, columns=CONSOLIDADO_COLUMNS)


def _has_audit_concepts(df: pd.DataFrame) -> bool:
    if "concepto" not in df.columns:
        return False
    concepts = df["concepto"].fillna("").astype(str).str.lower().str.strip()
    meaningful = concepts[concepts.ne("") & concepts.ne("nan")]
    return meaningful.isin({"dif costos", "sin diferencia", "sobrepago", "faltante"}).any()


def build_detalle(df: pd.DataFrame, folios: list[str]) -> pd.DataFrame:
    work = df.copy()
    work["folio"] = [
        make_folio(store, receipt)
        for store, receipt in zip(work["strnbr"], work["rcvnbr"])
    ]
    if folios:
        work = work[work["folio"].isin(folios)]
    rows = []
    for _, item in work.iterrows():
        rows.append(
            {
                "Folio_Pedido": clean_code(item.get("ponbr")),
                "FecPed": item.get("podt"),
                "Folio_NE": clean_code(item.get("rcvnbr")),
                "FecRecibo": item.get("rcvdt"),
                "Factura": item.get("invnbr_ne") or item.get("invnbr"),
                "Tienda/CEDIS": clean_code(item.get("strnbr")),
                "Division": item.get("nombre_division"),
                "Categoria": item.get("po_groupdescrip"),
                "GciaCateg": item.get("grupoarticulo"),
                "Material": clean_code(item.get("cltstyle")),
                "CodBarra": clean_code(item.get("codbarra")),
                "Descripcion": item.get("itmdesc"),
                "FactEmpaqu": _num(item.get("fact_empaq")),
                "CantRec": _num(item.get("can_rec")),
                "CtoUnitario_sistema": _num(item.get("ctonto_edi")),
                "Costo Unitario correcto": _num(item.get("cto_aud")),
                "Porc_IEPS": _num(item.get("prieps_edi")),
                "IEPS_Aud": _num(item.get("ieps_aud")),
                "Porc_IVA": _num(item.get("poriva_edi")),
                "IVA_Aud": _num(item.get("iva_aud")),
                "Debio Pagar correcto": _num(item.get("imp_aud")),
            }
        )
    return pd.DataFrame(rows, columns=DETALLE_COLUMNS)


def _write_resumen(ws, compras_df: pd.DataFrame, consolidated: pd.DataFrame) -> None:
    vendor = _vendor_label(compras_df)
    ws["C2"] = "Tiendas Soriana, S.A. de C.V."
    ws["C3"] = vendor
    ws["C4"] = "Validacion de Condiciones"
    for cell in ["C2", "C3", "C4"]:
        ws[cell].font = TITLE_FONT
        ws[cell].alignment = Alignment(horizontal="center")
    ws["C7"] = "Resultado Auditoria"
    ws["D7"] = "Observaciones Auditor"
    ws["C8"] = float(consolidated["Diferencia"].sum()) if not consolidated.empty else 0
    ws["D8"] = "Diferencia costos" if not consolidated.empty else ""
    for cell in ["C7", "D7"]:
        ws[cell].fill = HEADER_FILL
        ws[cell].font = HEADER_FONT
        ws[cell].alignment = Alignment(horizontal="center")
    ws["C8"].number_format = '#,##0.00'
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 28
    ws.sheet_view.showGridLines = False


def _write_consolidado(ws, compras_df: pd.DataFrame, consolidated: pd.DataFrame) -> None:
    _write_sheet_title(ws, compras_df)
    ws["L7"] = "=SUBTOTAL(109,L9:L1048576)"
    ws["M7"] = "=SUBTOTAL(109,M9:M1048576)"
    ws["L7"].fill = TOTAL_FILL
    ws["M7"].fill = TOTAL_FILL
    ws["L7"].number_format = '#,##0.00'
    ws["M7"].number_format = '#,##0.00'
    _write_table(ws, consolidated, CONSOLIDADO_COLUMNS, start_row=8, start_col=2)
    _format_validation_sheet(ws, start_col=2, num_cols=len(CONSOLIDADO_COLUMNS), money_cols={10, 11, 12}, date_cols={5, 7, 14})


def _write_detalle(ws, compras_df: pd.DataFrame, detail: pd.DataFrame) -> None:
    _write_sheet_title(ws, compras_df)
    ws["V7"] = "=SUBTOTAL(109,V9:V1048576)"
    ws["V7"].fill = TOTAL_FILL
    ws["V7"].number_format = '#,##0.00'
    _write_table(ws, detail, DETALLE_COLUMNS, start_row=8, start_col=2)
    _format_validation_sheet(ws, start_col=2, num_cols=len(DETALLE_COLUMNS), money_cols={15, 16, 21}, date_cols={2, 4}, percent_cols={17, 18, 19, 20})


def _write_sheet_title(ws, compras_df: pd.DataFrame) -> None:
    ws["B2"] = "Tiendas  Soriana, S.A. de C.V."
    ws["B3"] = _vendor_label(compras_df)
    ws["B4"] = "Validacion de Condiciones"
    for cell in ["B2", "B3", "B4"]:
        ws[cell].font = TITLE_FONT
    ws.sheet_view.showGridLines = False


def _write_table(ws, df: pd.DataFrame, columns: list[str], start_row: int, start_col: int) -> None:
    for idx, column in enumerate(columns, start=start_col):
        cell = ws.cell(start_row, idx, column)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER

    for row_idx, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for col_idx, value in enumerate(row, start=start_col):
            cell = ws.cell(row_idx, col_idx, None if pd.isna(value) else value)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center")

    end_row = start_row + max(len(df), 1)
    end_col = start_col + len(columns) - 1
    ws.auto_filter.ref = f"{get_column_letter(start_col)}{start_row}:{get_column_letter(end_col)}{end_row}"


def _format_validation_sheet(
    ws,
    start_col: int,
    num_cols: int,
    money_cols: set[int],
    date_cols: set[int],
    percent_cols: set[int] | None = None,
) -> None:
    percent_cols = percent_cols or set()
    widths = [14, 20, 13, 14, 13, 14, 13, 13, 18, 14, 14, 14, 24, 13, 18]
    for offset in range(num_cols):
        col_idx = start_col + offset
        width = widths[offset] if offset < len(widths) else 14
        ws.column_dimensions[get_column_letter(col_idx)].width = width
        data_col = offset + 1
        for cell in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=9):
            for item in cell:
                if data_col in money_cols:
                    item.number_format = '#,##0.00'
                elif data_col in date_cols:
                    item.number_format = "yyyy-mm-dd"
                elif data_col in percent_cols:
                    item.number_format = "0.00%"
    ws.freeze_panes = "B9"


def _vendor_label(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    vendor = clean_code(df.iloc[0].get("vndnbr"))
    name = df.iloc[0].get("vndname") or ""
    return f"{vendor} - {name}".strip(" -")


def _num(value) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return 0.0
    return float(parsed)
