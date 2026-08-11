"""Ajustes de pagos (MR8M y KG-14) sobre el Consolidado de Validación de Condiciones.

El Line Item de Compras (Audit Tools) no contempla ciertas **devoluciones/ajustes de pago**
que sí anulan diferencias reales. Viven en la función `F_APV2` de `SORIANA_PROJECTS` y son
de dos tipos (reunión 006, 2026-08-04 con Perla y Mónica):

- **MR8M**: devolución que **no** referencia nota de entrada ni tienda, solo la factura.
  Se identifica por `DOC_TEXT = 'MR8M'`. Llave de cruce: **proveedor + factura**.
- **KG-14**: ajuste que **sí** trae tienda (`StrNbr`) y nota (`RcpNbr`). Se identifica por
  `COD_TYPE_CODE = 'KG'` y `BSAK_BSIK_XREF3` que empieza en `14`. Llave: **nota de entrada
  (`RcpNbr`) + tienda (`StrNbr`)** — que es exactamente el folio del Consolidado.

El importe de la devolución es `GrsInvAmt` (viene **negativo**). Según el `ChkNbr`:

- **Compensada** (`ChkNbr` con valor): el pago ya fue efectivo. La devolución **reduce** la
  diferencia del renglón del Consolidado (se consume contra la diferencia disponible, sin
  dejarla por debajo de cero).
- **No compensada** (`ChkNbr` vacío o `0`): el ajuste está identificado por el cliente pero
  **aún no se ejecuta**. **No** se resta; en su lugar el renglón se **marca como alerta**
  ("No compensado/ejecutado") con el conteo y el monto pendiente, para que el auditor vigile
  esa factura/nota en el sistema del cliente y haga la resta manual cuando se compense
  (reunión 007, 2026-08-04).

Este módulo separa el acceso a BD (`fetch_pagos_ajustes`) de la lógica de aplicación
(`aplicar_ajustes`, pura y testeable). Ver docs/LOGICA_NEGOCIO.md §11.
"""

from __future__ import annotations

import pandas as pd

import config
from automation_costos.cruce_cpa import normalizar_factura
from automation_costos.utils import to_number

# Periodo de la auditoría; F_APV2 se consulta con un rango amplio para no perder ninguna
# devolución (las facturas van de 2020 a 2025).
PERIODO_INICIO = "1/1/2020"
PERIODO_FIN = "12/31/2025"

# Columnas de la hoja "Ajustes" (bitácora de cada devolución: compensada o pendiente).
AJUSTES_COLUMNS = [
    "Proveedor",
    "Tienda/CEDIS",
    "Nota Entrada",
    "Factura",
    "Diferencia Original",
    "Tipo Ajuste",
    "Compensado",
    "Ajuste Aplicado",
    "Monto No Compensado",
    "Documento Pago",
    "Fecha Pago",
    "DOC_TEXT",
]

# Columnas que se añaden al Consolidado cuando hay devoluciones (compensadas o pendientes).
COLUMNAS_AJUSTE = [
    "Tipo Ajuste",
    "Ajuste Pagos",
    "Diferencia Ajustada",
    "Compensado",
    "Conteo No Compensados",
    "Monto No Compensado",
]

_SELECT = (
    "SELECT VndNbr, InvNbr, StrNbr, RcpNbr, GrsInvAmt, ChkNbr, ChkDt, "
    "COD_TYPE_CODE, DOC_TEXT, BSAK_BSIK_XREF3 "
    "FROM {db}.dbo.[F_APV2](?, ?, ?)"
)


def fetch_pagos_ajustes(
    vndnbr: str,
    start_date: str = PERIODO_INICIO,
    end_date: str = PERIODO_FIN,
    *,
    database: str | None = None,
) -> pd.DataFrame:
    """Lee de `F_APV2` las devoluciones MR8M y KG-14 ejecutadas de un proveedor.

    Devuelve un DataFrame normalizado con columnas
    `[tipo, vndnbr, invnbr, strnbr, rcpnbr, importe, chknbr, chkdt, doc_text]`.
    Requiere pyodbc y conexión; el llamador decide qué hacer si falla.
    """
    import pyodbc

    database = database or config.DB_NAME
    with pyodbc.connect(config.get_connection_string()) as conn:
        cursor = conn.cursor()
        cursor.execute(_SELECT.format(db=database), str(vndnbr), start_date, end_date)
        columnas = [col[0] for col in cursor.description]
        filas = cursor.fetchall()
    crudo = pd.DataFrame.from_records([tuple(f) for f in filas], columns=columnas)
    return clasificar_pagos(crudo)


def clasificar_pagos(crudo: pd.DataFrame) -> pd.DataFrame:
    """Filtra el resultado de `F_APV2` a las devoluciones MR8M y KG-14 aplicables.

    Función pura (sin BD) para poder probarla con datos sintéticos.
    """
    cols = ["tipo", "vndnbr", "invnbr", "strnbr", "rcpnbr", "importe", "chknbr", "chkdt", "doc_text", "compensado"]
    vacio = pd.DataFrame(columns=cols)
    if crudo is None or crudo.empty:
        return vacio

    def texto(col: str) -> pd.Series:
        if col not in crudo.columns:
            return pd.Series([""] * len(crudo), index=crudo.index)
        return crudo[col].fillna("").astype(str).str.strip()

    doc_text = texto("DOC_TEXT").str.upper()
    cod_tipo = texto("COD_TYPE_CODE").str.upper()
    xref3 = texto("BSAK_BSIK_XREF3")
    importe = to_number(crudo.get("GrsInvAmt"))

    # Se incluyen TODAS las devoluciones MR8M/KG (negativas), compensadas o no; el estado
    # de compensación va en la columna `compensado` y lo decide `aplicar_ajustes`.
    es_mr8m = doc_text.eq("MR8M") & importe.lt(0)
    es_kg = cod_tipo.eq("KG") & xref3.str.startswith("14") & importe.lt(0)
    mask = es_mr8m | es_kg
    if not mask.any():
        return vacio

    tipo = pd.Series("", index=crudo.index)
    tipo[es_mr8m] = "MR8M"
    tipo[es_kg] = "KG"

    return pd.DataFrame(
        {
            "tipo": tipo[mask].values,
            "vndnbr": texto("VndNbr")[mask].values,
            "invnbr": texto("InvNbr")[mask].values,
            "strnbr": texto("StrNbr")[mask].values,
            "rcpnbr": texto("RcpNbr")[mask].values,
            "importe": importe[mask].values,
            "chknbr": texto("ChkNbr")[mask].values,
            "chkdt": crudo.get("ChkDt")[mask].values if "ChkDt" in crudo.columns else "",
            "doc_text": texto("DOC_TEXT")[mask].values,
            "compensado": _chk_ejecutado(texto("ChkNbr"))[mask].values,
        }
    )


def aplicar_ajustes(
    consolidado: pd.DataFrame, pagos: pd.DataFrame, *, threshold: float = 0.0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica las devoluciones al Consolidado. Función pura.

    Devuelve `(consolidado_con_columnas_ajuste, detalle_ajustes)`. Al Consolidado se le
    agregan seis columnas: `Tipo Ajuste`, `Ajuste Pagos` (suma compensada aplicada, negativa),
    `Diferencia Ajustada` (= Diferencia + Ajuste Pagos), `Compensado` (bandera de alerta),
    `Conteo No Compensados` y `Monto No Compensado`. `detalle_ajustes` trae una fila por
    devolución cruzada (para la hoja "Ajustes").

    - **Compensada** (`ChkNbr` con valor): se **consume** contra la diferencia disponible de
      los renglones que cruza (MR8M por proveedor+factura; KG por nota de entrada + tienda),
      sin dejar la diferencia por debajo de cero (una factura con varios folios reparte en
      cascada, sin descontar de más).
    - **No compensada** (`ChkNbr` vacío): **no** resta; marca los renglones cruzados con la
      bandera "No compensado/ejecutado", suma el monto pendiente y cuenta los registros.
    """
    con = consolidado.reset_index(drop=True).copy()
    diferencia = to_number(con.get("Diferencia"))
    con["Tipo Ajuste"] = ""
    con["Ajuste Pagos"] = 0.0
    con["Compensado"] = ""
    con["Conteo No Compensados"] = 0
    con["Monto No Compensado"] = 0.0

    if con.empty or pagos is None or pagos.empty:
        con["Diferencia Ajustada"] = diferencia.round(2)
        return con, pd.DataFrame(columns=AJUSTES_COLUMNS)

    prov = con.get("Proveedor", pd.Series([""] * len(con))).map(_norm_code)
    fac = con.get("Factura", pd.Series([""] * len(con))).map(normalizar_factura)
    tienda = con.get("Tienda/CEDIS", pd.Series([""] * len(con))).map(_norm_code)
    nota = con.get("Nota Entrada", pd.Series([""] * len(con))).map(_norm_code)
    restante = diferencia.clip(lower=0.0).tolist()  # diferencia disponible por renglón

    detalle: list[dict] = []
    for pago in pagos.itertuples(index=False):
        p_prov = _norm_code(pago.vndnbr)
        if pago.tipo == "MR8M":
            # MR8M no trae nota ni tienda: se liga por proveedor + factura.
            cruza = (prov == p_prov) & (fac == normalizar_factura(pago.invnbr))
        else:  # KG: se liga por nota de entrada (RcpNbr) + tienda (StrNbr) = el folio exacto.
            cruza = (prov == p_prov) & (nota == _norm_code(pago.rcpnbr)) & (tienda == _norm_code(pago.strnbr))

        indices = list(con.index[cruza])
        if not indices:
            continue
        monto = abs(_num(pago.importe))

        if not bool(pago.compensado):
            # No compensada: no se resta; se marca la alerta en cada renglón que cruza.
            for i in indices:
                con.at[i, "Conteo No Compensados"] = int(con.at[i, "Conteo No Compensados"]) + 1
                con.at[i, "Monto No Compensado"] = round(_num(con.at[i, "Monto No Compensado"]) + monto, 2)
                con.at[i, "Compensado"] = "No compensado/ejecutado"
                con.at[i, "Tipo Ajuste"] = _fusionar_tipo(con.at[i, "Tipo Ajuste"], pago.tipo)
                detalle.append(_fila_detalle(con, i, pago, aplicado=0.0, no_compensado=monto))
            continue

        # Compensada: se consume contra la diferencia disponible.
        por_consumir = monto
        for i in indices:
            if por_consumir <= 0.005:
                break
            disponible = restante[i]
            if disponible <= 0.005:
                continue
            toma = min(disponible, por_consumir)
            restante[i] = disponible - toma
            por_consumir -= toma
            con.at[i, "Ajuste Pagos"] = con.at[i, "Ajuste Pagos"] - toma
            con.at[i, "Tipo Ajuste"] = _fusionar_tipo(con.at[i, "Tipo Ajuste"], pago.tipo)
            detalle.append(_fila_detalle(con, i, pago, aplicado=-toma, no_compensado=0.0))

    con["Diferencia Ajustada"] = (diferencia + to_number(con["Ajuste Pagos"])).round(2)
    return con, pd.DataFrame(detalle, columns=AJUSTES_COLUMNS)


def _fila_detalle(con: pd.DataFrame, i: int, pago, *, aplicado: float, no_compensado: float) -> dict:
    """Una fila de la hoja 'Ajustes' (una devolución cruzada contra un renglón)."""
    return {
        "Proveedor": con.at[i, "Proveedor"],
        "Tienda/CEDIS": con.at[i, "Tienda/CEDIS"],
        "Nota Entrada": con.at[i, "Nota Entrada"],
        "Factura": con.at[i, "Factura"],
        "Diferencia Original": round(_num(con.at[i, "Diferencia"]), 2),
        "Tipo Ajuste": pago.tipo,
        "Compensado": "Sí" if bool(pago.compensado) else "No",
        "Ajuste Aplicado": round(aplicado, 2),
        "Monto No Compensado": round(no_compensado, 2),
        "Documento Pago": str(pago.chknbr).strip(),
        "Fecha Pago": _fecha_valida(pago.chkdt),
        "DOC_TEXT": str(pago.doc_text).strip(),
    }


def _fecha_valida(valor):
    """Fecha real o None. Descarta nulos y el placeholder `1900-01-01` que SQL Server pone
    en `ChkDt` cuando la devolución aún no está compensada (no tiene fecha de pago)."""
    if valor is None:
        return None
    try:
        ts = pd.Timestamp(valor)
    except (ValueError, TypeError):
        return None
    if pd.isna(ts) or ts.year <= 1900:
        return None
    return valor


def _chk_ejecutado(chknbr: pd.Series) -> pd.Series:
    """True donde el cheque está ejecutado: con folio real (no vacío, no 0)."""
    limpio = chknbr.astype(str).str.strip().str.lower()
    return ~limpio.isin(["", "0", "0.0", "none", "nan"])


def _fusionar_tipo(actual: str, nuevo: str) -> str:
    partes = {p for p in str(actual).split("+") if p}
    partes.add(nuevo)
    return "+".join(sorted(partes))


def _norm_code(valor) -> str:
    """Normaliza un código numérico (proveedor/tienda): sin espacios, sin ceros a la izquierda."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.lstrip("0") or texto


def _num(valor) -> float:
    parsed = pd.to_numeric(pd.Series([valor]), errors="coerce").iloc[0]
    return 0.0 if pd.isna(parsed) else float(parsed)
