from __future__ import annotations

import numpy as np
import pandas as pd

from automation_cobros.utils import clean_code, make_folio, normalize_date_columns, to_number


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


def prepare_compras_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(column).strip() for column in df.columns]
    df = normalize_date_columns(df)
    df = add_derived_base_columns(df)
    df = recalculate_dataframe(df)

    for column in COMPRAS_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan
    return df[COMPRAS_COLUMNS]


def add_derived_base_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "strnbr" in df.columns and "rcvnbr" in df.columns:
        df["concaten"] = [
            clean_code(store) + clean_code(receipt)
            for store, receipt in zip(df["strnbr"], df["rcvnbr"])
        ]
        df["folio"] = [
            make_folio(store, receipt)
            for store, receipt in zip(df["strnbr"], df["rcvnbr"])
        ]

    if "ctouni" in df.columns and "ctouni_sistema" not in df.columns:
        df["ctouni_sistema"] = df["ctouni"]
    if "fact_empaq" in df.columns and "fante" not in df.columns:
        df["fante"] = df["fact_empaq"]
    if "factem_edi" in df.columns and "facdecto" not in df.columns:
        df["facdecto"] = df["factem_edi"]
    return df


def recalculate_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = normalize_date_columns(df)
    df = add_derived_base_columns(df)

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
        df["folio"] = [
            make_folio(store, receipt)
            for store, receipt in zip(_col(df, "strnbr"), _col(df, "rcvnbr"))
        ]

    df["debio_pagar_ne"] = df.groupby("folio", dropna=False)["imp_aud"].transform("sum").round(4)
    df["dpagar"] = df["debio_pagar_ne"]

    tot_pagado_ne = _best_total_paid_ne(df)
    df["tot_pagado_ne"] = tot_pagado_ne
    df["dif_det_ne"] = (to_number(df["tot_pagado_ne"]) - to_number(df["debio_pagar_ne"])).round(4)

    df = _recalculate_invoice_level(df)
    if "concepto" not in df.columns:
        df["concepto"] = ""
    else:
        df["concepto"] = df["concepto"].fillna("").astype(str).str.strip()
    return df


def build_pending_edi_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    existing = [column for column in EDI_COLUMNS if column in df.columns]
    if not existing:
        return pd.DataFrame()
    mask = df[existing].isna() | df[existing].astype(str).eq("")
    pending = df.loc[mask.any(axis=1)].copy()
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


def _recalculate_invoice_level(df: pd.DataFrame) -> pd.DataFrame:
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
    return df.drop(columns=["_invoice_key"])


def _invoice_group_key(df: pd.DataFrame) -> pd.Series:
    parts = []
    for column in ["vndnbr", "strnbr", "invnbr"]:
        if column in df.columns:
            parts.append(df[column].map(clean_code))
    if not parts:
        return pd.Series([""] * len(df), index=df.index)
    key = parts[0]
    for part in parts[1:]:
        key = key + "|" + part
    return key
