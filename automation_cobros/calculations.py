from __future__ import annotations

import numpy as np
import pandas as pd

from automation_cobros.utils import (
    clean_code_series,
    make_folio_series,
    normalize_date_columns,
    to_number,
)


EDI_COLUMNS = [
    "canfac_edi",
    "factem_edi",
    "ctobto_edi",
    "ctonto_edi",
    "impart_edi",
    "prieps_edi",
    "imieps_edi",
    "poriva_edi",
    "impiva_edi",
    "totfactura",
    "uuid",
]


COMPRAS_COLUMNS = [
    "cnpj",
    "vndnbr",
    "vndname",
    "concaten",
    "dptnbr",
    "ponbr",
    "podt",
    "tip_po",
    "ctg_po",
    "postatus",
    "po_org",
    "rcvnbr",
    "rcvdt",
    "strnbr",
    "invnbr",
    "invdt",
    "division",
    "nombre_division",
    "po_group",
    "po_groupdescrip",
    "cltstyle",
    "codbarra",
    "upc",
    "grupoarticulo",
    "gpoartdesc2",
    "itmdesc",
    "poitmcspck",
    "poitmsz",
    "fact_empaq",
    "poqty",
    "rcvqty",
    "invqty",
    "can_rec",
    "poitmgrscst",
    "poitmnetcst",
    "ctouni",
    "fante",
    "facdecto",
    "ctouni_sistema",
    "ctontol",
    "impaud",
    "dpagar",
    "imp",
    "compra_bruta",
    "compra_bruta mas impuestos",
    "compra_neta",
    "compra neta mas impuestos",
    "potaxcode",
    "ieps_t007s",
    "iva_t007s",
    "descr_impuesto",
    "nor1_konv",
    "nor2_konv",
    "nor3_konv",
    "nor4_konv",
    "adi1_konv",
    "adi2_konv",
    "adi3_konv",
    "bonif1_konv",
    "bonif2_konv",
    "bonif3_konv",
    "bonif4_konv",
    "bonif5_konv",
    "pp_konv",
    "cen_konv",
    "porccargo_konv",
    "fact_desct",
    "tipo_marca",
    "cod_tipo_mvto",
    "canfac_edi",
    "factem_edi",
    "ctobto_edi",
    "ctonto_edi",
    "dif cto fac ctouni",
    "ctontopza",
    "impart_edi",
    "prieps_edi",
    "imieps_edi",
    "poriva_edi",
    "impiva_edi",
    "totfactura",
    "uuid",
    "cto_aud",
    "iva_aud",
    "ieps_aud",
    "imp_aud",
    "debio_pagar_ne",
    "dif_det_ne",
    "debio_pagar_inv",
    "tot_pagado_inv",
    "dif_det_inv",
    "payinvnbr",
    "payinvchknbr",
    "paynetamt",
    "paychkdt",
    "payinvdt",
    "invnbr_ne",
    "invdt_ne",
    "tot_pagado_ne",
    "paychkdt_ne",
    "paychknbr_ne",
    "cod_tip_doc",
    "cod_transac",
    "txt_cabec",
    "txt_item",
]


# Columnas que la preparación necesita como insumo o resultado intermedio y que no salen
# en el Compras. Todo lo demás que traiga F_COMPRAS se descarta antes de calcular.
_AUX_COLUMNS = ("folio", "concepto")


def prepare_compras_dataframe(df: pd.DataFrame, *, en_sitio: bool = False) -> pd.DataFrame:
    """Deja el DataFrame listo para el Compras: recalculado y con las 105 columnas en orden.

    Con `en_sitio=True` esta función **toma posesión** del DataFrame recibido y lo muta;
    quien llama no debe volver a usarlo. Es lo que permite procesar proveedores de más de
    un millón de renglones: la versión que copiaba en cada paso mantenía cinco copias
    completas vivas a la vez y agotaba la memoria (ver docs/RENDIMIENTO_EXPORTADOR.md).
    """
    if not en_sitio:
        df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]

    # Recorte temprano: F_COMPRAS devuelve más columnas de las que salen en el Compras y
    # arrastrarlas por toda la cadena de cálculo es memoria pura.
    sobrantes = [
        column
        for column in df.columns
        if column not in COMPRAS_COLUMNS and column not in _AUX_COLUMNS
    ]
    if sobrantes:
        df.drop(columns=sobrantes, inplace=True)

    # recalculate_dataframe ya hace normalize_date_columns + add_derived_base_columns;
    # no hace falta repetirlos aqui (eran bucles por fila corriendo dos veces).
    df = recalculate_dataframe(df, en_sitio=True)

    faltantes = [column for column in COMPRAS_COLUMNS if column not in df.columns]
    for column in faltantes:
        df[column] = np.nan
    return _reordenar(df, COMPRAS_COLUMNS)


def _reordenar(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    """Deja solo `columnas` y en ese orden, sin materializar una copia si ya coinciden."""
    if list(df.columns) == list(columnas):
        return df
    df.drop(columns=[c for c in df.columns if c not in columnas], inplace=True)
    return df[columnas]


def add_derived_base_columns(df: pd.DataFrame, *, en_sitio: bool = False) -> pd.DataFrame:
    if not en_sitio:
        df = df.copy()
    if "strnbr" in df.columns and "rcvnbr" in df.columns:
        tienda = clean_code_series(df["strnbr"])
        nota = clean_code_series(df["rcvnbr"])
        df["concaten"] = tienda + nota
        df["folio"] = make_folio_series(df["strnbr"], df["rcvnbr"])
        del tienda, nota

    if "ctouni" in df.columns and "ctouni_sistema" not in df.columns:
        df["ctouni_sistema"] = df["ctouni"]
    if "fact_empaq" in df.columns and "fante" not in df.columns:
        df["fante"] = df["fact_empaq"]
    if "factem_edi" in df.columns and "facdecto" not in df.columns:
        df["facdecto"] = df["factem_edi"]
    return df


def recalculate_dataframe(df: pd.DataFrame, *, en_sitio: bool = False) -> pd.DataFrame:
    if not en_sitio:
        df = df.copy()
    df = normalize_date_columns(df)
    df = add_derived_base_columns(df, en_sitio=True)

    ctonto_edi = to_number(_col(df, "ctonto_edi"))
    ctouni = to_number(_col(df, "ctouni"))
    can_rec = to_number(_col(df, "can_rec"))
    poriva_edi = to_number(_col(df, "poriva_edi"))
    prieps_edi = to_number(_col(df, "prieps_edi"))
    iva_t007s = to_number(_col(df, "iva_t007s"))
    ieps_t007s = to_number(_col(df, "ieps_t007s"))

    has_edi_cost = ctonto_edi.ne(0)
    df["cto_aud"] = np.where(has_edi_cost & ctonto_edi.lt(ctouni), ctonto_edi, ctouni).round(4)
    df["iva_aud"] = np.where(has_edi_cost, poriva_edi, iva_t007s).round(6)
    df["ieps_aud"] = np.where(has_edi_cost, prieps_edi, ieps_t007s).round(6)
    df["imp_aud"] = (
        to_number(df["cto_aud"])
        * can_rec
        * (1 + to_number(df["iva_aud"]))
        * (1 + to_number(df["ieps_aud"]))
    ).round(4)

    df["impaud"] = df["imp_aud"]
    df["dif cto fac ctouni"] = (ctonto_edi - ctouni).round(4)
    df["ctontopza"] = ctonto_edi

    if "folio" not in df.columns:
        df["folio"] = make_folio_series(_col(df, "strnbr"), _col(df, "rcvnbr"))

    df["debio_pagar_ne"] = df.groupby("folio", dropna=False)["imp_aud"].transform("sum").round(4)
    df["dpagar"] = df["debio_pagar_ne"]

    tot_pagado_ne = _best_total_paid_ne(df)
    df["tot_pagado_ne"] = tot_pagado_ne
    df["dif_det_ne"] = (to_number(df["tot_pagado_ne"]) - to_number(df["debio_pagar_ne"])).round(4)

    df = _recalculate_invoice_level(df, en_sitio=True)
    if "concepto" not in df.columns:
        df["concepto"] = ""
    else:
        df["concepto"] = df["concepto"].fillna("").astype(str).str.strip()
    return df


def apply_display_formula_values(df: pd.DataFrame, *, en_sitio: bool = False) -> pd.DataFrame:
    """Calcula en Python las columnas que antes eran fórmulas vivas de Excel.

    Reemplaza el bloque de fórmulas del exportador para poder escribir el Compras como
    **valores** (rápido y sin el límite del VLOOKUP). Las definiciones replican las
    fórmulas originales del archivo, con guardas para no dividir entre cero.

    Con `en_sitio=True` muta el DataFrame recibido en vez de copiarlo.
    """
    if not en_sitio:
        df = df.copy()
    fact_empaq = to_number(_col(df, "fact_empaq"))
    can_rec = to_number(_col(df, "can_rec"))
    canfac_edi = to_number(_col(df, "canfac_edi"))
    ctonto_edi = to_number(_col(df, "ctonto_edi"))
    grs = to_number(_col(df, "poitmgrscst"))
    net = to_number(_col(df, "poitmnetcst"))

    df["fante"] = (canfac_edi * fact_empaq) - can_rec
    facdecto = np.where(grs != 0, 100 - (net / grs.replace(0, np.nan)) * 100, 0.0)
    df["facdecto"] = pd.Series(facdecto, index=df.index).fillna(0.0).round(6)
    ctouni_sistema = np.where(
        fact_empaq != 0, (grs / fact_empaq.replace(0, np.nan)) * (1 - to_number(df["facdecto"]) / 100), 0.0
    )
    df["ctouni_sistema"] = pd.Series(ctouni_sistema, index=df.index).fillna(0.0).round(6)

    sistema = to_number(df["ctouni_sistema"])
    mejor = np.where((ctonto_edi < sistema) & (ctonto_edi > 0), ctonto_edi, sistema)
    df["ctontol"] = pd.Series(mejor, index=df.index).round(6)

    df["imp"] = 0.16
    df["impaud"] = (to_number(df["ctontol"]) * can_rec * (1 + 0.16)).round(4)
    df["dif cto fac ctouni"] = (ctonto_edi - to_number(df["ctontol"])).round(4)
    df["ctontopza"] = np.where(fact_empaq != 0, ctonto_edi / fact_empaq.replace(0, np.nan), 0.0)
    df["ctontopza"] = pd.Series(df["ctontopza"], index=df.index).fillna(0.0).round(6)

    # dpagar = suma de impaud por folio (lo que hacía el SUMIF del VLOOKUP, sin tope de filas).
    if "concaten" in df.columns:
        df["dpagar"] = df.groupby("concaten", dropna=False)["impaud"].transform("sum").round(4)
    else:
        df["dpagar"] = df["impaud"]
    return df


def build_pending_edi_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    existing = [column for column in EDI_COLUMNS if column in df.columns]
    if not existing:
        return pd.DataFrame()
    # Máscara acumulada columna a columna: `df[existing].astype(str)` materializaba una
    # tabla de texto del tamaño del bloque EDI completo.
    mask = pd.Series(False, index=df.index)
    for column in existing:
        serie = df[column]
        mask |= serie.isna() | serie.astype(str).eq("")
    pending = df.loc[mask].copy()
    keep = [
        "folio",
        "vndnbr",
        "vndname",
        "ponbr",
        "podt",
        "rcvnbr",
        "rcvdt",
        "strnbr",
        "invnbr",
        "cltstyle",
        "codbarra",
        "itmdesc",
        *existing,
    ]
    keep = [column for column in keep if column in pending.columns]
    return pending[keep]


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    if name in df.columns:
        return df[name]
    return pd.Series([np.nan] * len(df), index=df.index)


def _best_total_paid_ne(df: pd.DataFrame) -> pd.Series:
    if "tot_pagado_ne" in df.columns and df["tot_pagado_ne"].notna().any():
        source = to_number(df["tot_pagado_ne"])
    elif "paynetamt" in df.columns:
        source = to_number(df["paynetamt"])
    else:
        source = pd.Series([0.0] * len(df), index=df.index)

    temp = pd.DataFrame({"folio": df["folio"], "paid": source})
    group_paid = temp.groupby("folio", dropna=False)["paid"].transform("max")
    return group_paid.round(4)


def _recalculate_invoice_level(df: pd.DataFrame, *, en_sitio: bool = False) -> pd.DataFrame:
    if not en_sitio:
        df = df.copy()
    invoice_key = _invoice_group_key(df)
    df["_invoice_key"] = invoice_key
    df["debio_pagar_inv"] = df.groupby("_invoice_key", dropna=False)["imp_aud"].transform("sum").round(4)

    if "tot_pagado_inv" in df.columns and df["tot_pagado_inv"].notna().any():
        paid_inv = to_number(df["tot_pagado_inv"])
    elif "paynetamt" in df.columns:
        paid_inv = to_number(df["paynetamt"])
    else:
        paid_inv = pd.Series([0.0] * len(df), index=df.index)
    df["tot_pagado_inv"] = pd.DataFrame({"key": invoice_key, "paid": paid_inv}).groupby(
        "key", dropna=False
    )["paid"].transform("max").round(4)
    df["dif_det_inv"] = (to_number(df["tot_pagado_inv"]) - to_number(df["debio_pagar_inv"])).round(4)
    df.drop(columns=["_invoice_key"], inplace=True)
    return df


def _invoice_group_key(df: pd.DataFrame) -> pd.Series:
    parts = []
    for column in ["vndnbr", "strnbr", "invnbr"]:
        if column in df.columns:
            parts.append(clean_code_series(df[column]))
    if not parts:
        return pd.Series([""] * len(df), index=df.index)
    key = parts[0]
    for part in parts[1:]:
        key = key + "|" + part
    return key
