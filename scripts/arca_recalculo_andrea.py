"""Recálculo COMPLETO de Arca (391250) con las fórmulas de Andrea — CASO AISLADO.

Pedido de Andrea Soler a Óscar (reunión 2026-08-26). **No es parte del pipeline normal y no
debe volverse parte de él**: el resto de los proveedores sigue exactamente igual.

Qué cambia respecto al proceso de siempre
-----------------------------------------
La auditoría de Arca se venía calculando sobre `can_rec` (cantidad recibida tal cual) y
`ctouni` (costo unitario del sistema). Andrea encontró dos problemas al revisar con el
cliente:

1. **Cantidades sin redondear.** `can_rec` trae valores como 79.92 cuando la cantidad real
   son 80 piezas. Al calcular sobre el valor crudo, el importe auditado sale mal.
2. **Factores de empaque malos.** El costo unitario derivado de ellos arrastra el error, y
   eso infló diferencias que resultaron no proceder (de $98M reportados quedaron $6.3M).

Su corrección reconstruye el costo unitario por otro camino —desde la compra bruta menos el
descuento comercial del 2.5 % que Arca da a pie de factura, dividida entre la cantidad ya
redondeada— y vuelve a comparar contra el CFDI.

El reemplazo es 1:1 con la fórmula que ya usa el programa, solo cambian los insumos:

    imp_aud       = cto_aud       × can_rec      × (1+iva_aud) × (1+ieps_aud)   ← antes
    Importe Audi2 = Mejor Costo 2 × Canti Correc × (1+iva_aud) × (1+ieps_aud)   ← ahora

y `Mejor Costo 2` conserva la estructura de `cto_aud` (gana el costo del CFDI si es válido y
menor), solo que el "costo del sistema" pasa de `ctouni` a `Costo Unitario VF`.

Por qué se recalcula desde SQL y no se leen los Compras ya entregados
---------------------------------------------------------------------
Los 24 `Compras_*.xlsx` de la carpeta de Arca **no son homogéneos**: el 2020-T1 tiene 112
columnas, los T2-T4 de 2020 tienen 106 y de 2021 en adelante 105 — se les fueron agregando
columnas a mano en distintos momentos. Leerlos exigiría lógica distinta por archivo, tardaría
horas (openpyxl sobre ~7 GB) y heredaría cualquier edición manual. Recalcular desde
`F_COMPRAS` + el Parquet de CPA es determinista, reproducible y da los Compras completos que
de todos modos hay que entregar.

Las dos metodologías de costo (decisión de Andrea)
--------------------------------------------------
Se dejan **las dos** columnas a propósito: `CTONTO2` va por (costo bruto ÷ factor empaque)
menos 2.5 %, y `Costo Unitario VF` va por (compra bruta − 2.5 %) ÷ cantidad redondeada.
Coinciden cuando `can_rec` es múltiplo exacto del factor de empaque y **difieren justo en los
renglones "Not Rounded"**, que es donde está el hallazgo. Andrea quiere poder mostrarle al
cliente que se llegó al mismo número por los dos caminos.

Uso
---
    python scripts/arca_recalculo_andrea.py --extraer    # SQL + cruce + Compras (lento)
    python scripts/arca_recalculo_andrea.py --generar    # Validaciones por año (rápido)
    python scripts/arca_recalculo_andrea.py              # las dos

`--extraer` es **resumible**: cada trimestre que termina deja su caché en Parquet y su
Compras en disco, y una segunda corrida los salta. Así una interrupción no cuesta la corrida
entera. `--generar` trabaja solo contra el caché, para poder repetirlo si hay que ajustar el
formato sin volver a consultar SQL.
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# La consola de Windows es cp1252 y revienta con acentos. Un print no puede tumbar una
# corrida de horas.
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import xlsxwriter

import config
from automation_costos.calculations import COMPRAS_COLUMNS
from automation_costos.pipeline_streaming import _intervalos_trimestre, _salida_intervalo
from automation_costos.utils import ensure_parent, make_folio_series, to_number
from automation_costos.validation_exporter import (
    AJUSTES_COLUMNS,
    DETALLE_COLUMNS,
    _DetalleStream,
    _formatos_xlsx,
    _volcar_xlsx,
    aplicar_ajustes_a_consolidado,
    build_consolidado,
    build_detalle_rapido,
)

PROVEEDOR = "391250"
NOMBRE = "DISTRIBUIDORA ARCA CONTINENTAL S DE RL DE CV"
BASE = f"{PROVEEDOR}_{NOMBRE}"
INICIO, FIN = "2020-01-01", "2025-12-31"

CARPETA_ARCA = Path(
    r"X:\Soriana\00 - AUDITORIA 2020 - 2024\Proceso Validación de condiciones (Oscar Pineda)"
) / BASE
SALIDA = CARPETA_ARCA / "Arca regenerado recalculos"

# El caché va al disco LOCAL, no al share: X: está al 99 % y este caché ronda 1-2 GB.
CACHE = Path(r"C:\Users\opined01\AppData\Local\Temp\arca_recalculo_cache")

#: Descuento comercial que Arca da a pie de factura. Es 2.5 % en TODO el periodo y para todos
#: los renglones — lo determinó Andrea con el proveedor. Para cualquier otro proveedor habría
#: que revisarlo, por eso vive aquí y no en el pipeline.
FACTOR_DESCUENTO = 2.5

#: Columnas nuevas, en el orden en que Andrea las dejó en su archivo de muestra, ancladas a la
#: columna del Compras después de la cual van. Replicar su layout hace que el archivo le
#: resulte familiar y pueda comparar contra sus ejemplos sin buscar columnas.
NUEVAS_TRAS = {
    "vndname": ["concaten tienda+NE", "Concatenar RCVN+COD BA"],
    "strnbr": ["Concatenar+ RCVN_EAN"],
    "fact_empaq": ["fact_empaq Correcto"],
    "can_rec": ["Redondeo", "Canti Correc"],
    "poitmnetcst": ["facdescto"],
    "ctouni": ["CTONTO2", "Costo Unitario VF", "impor AUD VF"],
    "compra_bruta mas impuestos": ["Compra Bruta - 2.5%"],
    "compra_neta": ["Factor aw/at", "Diferencia AV - NetaAW", "Factor AW - AY", "Importe + Imp"],
    "uuid": ["Mejor Costo 2", "Importe Audi2"],
}

#: Andrea **renombró** `concaten` a "Cruce con diferencias" (misma columna, misma posición) y
#: eliminó la versión sin guion. No es cosmético: `concaten` pega tienda y nota SIN separador,
#: que es exactamente lo que hace colisionar 73+2455 con 732+455 — el bug que ella encontró.
#: Se respeta su título para que el archivo sea espejo del suyo y las letras de columna
#: coincidan, de modo que sus fórmulas copiadas sigan apuntando a donde deben.
RENOMBRES = {"concaten": "Cruce con diferencias"}

#: Además de renombrarla, Andrea la **movió**: en el Compras normal `concaten` va en la
#: cuarta columna, y en el suyo aparece pegada a `rcvnbr`, que es contra lo que cruza.
MOVER_TRAS = {"concaten": "rcvnbr"}

DETALLE_COLUMNS_ARCA = [*DETALLE_COLUMNS, "Trimestre"]

#: Lo que la Validación lee del caché. El caché guarda el trimestre completo, pero la fase 2
#: solo necesita estas: leer las 117 por trozo multiplicaría la memoria sin usarse.
COLUMNAS_VALIDACION = [
    "vndnbr", "vndname", "strnbr", "rcvnbr", "po_org", "podt", "ponbr", "rcvdt",
    "invnbr", "invnbr_ne", "paychkdt_ne", "paychknbr_ne", "tot_pagado_ne",
    "nombre_division", "po_groupdescrip", "grupoarticulo", "cltstyle", "codbarra",
    "itmdesc", "fact_empaq", "can_rec", "ctouni", "ctonto_edi", "cto_aud",
    "prieps_edi", "ieps_aud", "poriva_edi", "iva_aud", "imp_aud",
    "folio", "Trimestre",
]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------------------
# El cálculo
# ---------------------------------------------------------------------------------------
def calcular_columnas_andrea(df: pd.DataFrame) -> dict[str, int]:
    """Agrega (in situ) las columnas de Andrea y **sobrescribe** las cuatro que la Validación
    consume, para que el Consolidado y el Detalle salgan con la metodología nueva.

    Devuelve un diccionario de anomalías para poder reportarlas: los renglones donde una
    división no se puede hacer (cantidad o factor de empaque en cero) quedan en 0 en vez de
    reventar, igual que un `#DIV/0!` de Excel se dejaría vacío, pero **se cuentan** porque son
    justamente los casos que Andrea va a querer revisar con el cliente.
    """
    can_rec = to_number(df["can_rec"])
    poitmgrscst = to_number(df["poitmgrscst"])
    fact_empaq = to_number(df["fact_empaq"])
    compra_bruta = to_number(df["compra_bruta"])
    ctonto_edi = to_number(df["ctonto_edi"])
    ieps_aud = to_number(df["ieps_aud"])
    iva_aud = to_number(df["iva_aud"])

    # --- Concatenados de trabajo. El guion NO es cosmético: sin él "73"+"2455" y "732"+"455"
    # colapsan en el mismo texto y el cruce toma el renglón equivocado. Lo detectó Andrea.
    strnbr = df["strnbr"].astype(str).str.strip()
    rcvnbr = df["rcvnbr"].astype(str).str.strip()
    codbarra = df["codbarra"].astype(str).str.strip()
    df["concaten tienda+NE"] = strnbr + "-" + rcvnbr
    df["Concatenar RCVN+COD BA"] = rcvnbr + "-" + codbarra

    # --- Columna en blanco: la llena Andrea a mano al revisar con el proveedor.
    df["fact_empaq Correcto"] = pd.NA

    # --- Cantidad redondeada. `can_rec` trae 79.92 donde son 80 piezas.
    canti_correc = can_rec.round(0)
    df["Redondeo"] = np.where(can_rec.ne(canti_correc), "Not Rounded", "Rounded")
    df["Canti Correc"] = canti_correc

    df["facdescto"] = FACTOR_DESCUENTO

    # --- Metodología 1: costo bruto por pieza, menos el descuento comercial.
    sin_empaque = fact_empaq.eq(0) | fact_empaq.isna()
    df["CTONTO2"] = np.where(
        sin_empaque, 0.0,
        (poitmgrscst / fact_empaq.replace(0, np.nan)) * (1 - FACTOR_DESCUENTO / 100),
    )
    df["CTONTO2"] = to_number(df["CTONTO2"]).fillna(0.0)

    # --- Metodología 2 (la que manda): compra bruta menos 2.5 %, entre la cantidad redondeada.
    df["Compra Bruta - 2.5%"] = compra_bruta * (1 - FACTOR_DESCUENTO / 100)
    sin_cantidad = canti_correc.eq(0) | canti_correc.isna()
    costo_vf = np.where(
        sin_cantidad, 0.0,
        to_number(df["Compra Bruta - 2.5%"]) / canti_correc.replace(0, np.nan),
    )
    df["Costo Unitario VF"] = pd.Series(costo_vf, index=df.index).fillna(0.0)
    costo_vf = to_number(df["Costo Unitario VF"])

    impuestos = (1 + ieps_aud) * (1 + iva_aud)
    df["impor AUD VF"] = (costo_vf * canti_correc * impuestos).round(4)

    # --- Mejor Costo 2: misma regla que `cto_aud`, pero contra el costo unitario nuevo.
    # Gana el costo del CFDI solo si existe (>0) y es MENOR; si no, el del sistema.
    df["Mejor Costo 2"] = np.where(
        ctonto_edi.gt(0) & ctonto_edi.lt(costo_vf), ctonto_edi, costo_vf
    )
    mejor_costo = to_number(df["Mejor Costo 2"])
    df["Importe Audi2"] = (mejor_costo * canti_correc * impuestos).round(4)

    # --- El reemplazo. La Validación (build_consolidado / build_detalle_rapido) lee estas
    # cuatro columnas por nombre; sobrescribirlas es lo que hace que el entregable salga con la
    # metodología nueva SIN tocar una línea del código ya probado, y deja los encabezados
    # idénticos a los de siempre, que es lo que pidió Óscar.
    df["can_rec"] = canti_correc
    df["ctouni"] = costo_vf
    df["cto_aud"] = mejor_costo
    df["imp_aud"] = to_number(df["Importe Audi2"])

    return {
        "sin_factor_empaque": int(sin_empaque.sum()),
        "sin_cantidad": int(sin_cantidad.sum()),
        "no_redondeados": int(can_rec.ne(canti_correc).sum()),
    }


def agregar_columnas_verificacion(df: pd.DataFrame) -> None:
    """Las columnas con las que Andrea **comprueba** que el recálculo cuadra.

    No entran en ningún cálculo del entregable: existen para que ella pueda enseñarle al
    cliente que el descuento del 2.5 % que se aplicó coincide con el que el sistema ya traía
    en `compra_neta`. `Diferencia AV - NetaAW` es la que importa: si el sistema descontó bien,
    da ~0; donde se aleja, hay algo que revisar.

    Se calculan aparte de `calcular_columnas_andrea` porque son derivables de columnas que ya
    están en el caché, así que se pueden agregar al escribir el Compras sin repetir las horas
    de SQL y cruce.
    """
    compra_bruta = to_number(df["compra_bruta"])
    compra_neta = to_number(df["compra_neta"])
    bruta_menos = to_number(df.get("Compra Bruta - 2.5%", compra_bruta * (1 - FACTOR_DESCUENTO / 100)))
    iva = to_number(df["iva_t007s"]) if "iva_t007s" in df.columns else 0.0

    rcvnbr = df["rcvnbr"].astype(str).str.strip()
    codbarra = df["codbarra"].astype(str).str.strip()
    # Duplicado de "Concatenar RCVN+COD BA" a propósito: Andrea tiene las dos en su archivo y
    # el objetivo es que el layout coincida columna por columna.
    df["Concatenar+ RCVN_EAN"] = rcvnbr + "-" + codbarra

    # Descuento real que trae el sistema, como fracción. Sin compra bruta no hay porcentaje
    # que calcular (sería una división por cero), así que se deja vacío en vez de inventar 0.
    sin_bruta = compra_bruta.eq(0) | compra_bruta.isna()
    df["Factor aw/at"] = np.where(sin_bruta, np.nan, 1 - (compra_neta / compra_bruta.replace(0, np.nan)))
    # Sin redondear: son columnas de comprobación, no entran en ningún cálculo del entregable,
    # y así quedan idénticas a las del archivo de Andrea hasta el último decimal.
    df["Diferencia AV - NetaAW"] = bruta_menos - compra_neta
    sin_neta = compra_neta.eq(0) | compra_neta.isna()
    df["Factor AW - AY"] = np.where(
        sin_neta, np.nan,
        to_number(df["Diferencia AV - NetaAW"]) / compra_neta.replace(0, np.nan),
    )
    df["Importe + Imp"] = compra_bruta * (1 + iva)


#: Códigos que viajan como TEXTO aunque parezcan números: llevan ceros a la izquierda y se
#: usan como llave de cruce. Convertirlos a número los rompe en silencio (un `0032455` se
#: vuelve `32455` y deja de cruzar).
COLUMNAS_CODIGO = {
    "cnpj", "vndnbr", "vndname", "dptnbr", "ponbr", "rcvnbr", "strnbr", "cltstyle",
    "codbarra", "upc", "invnbr", "invnbr_ne", "payinvnbr", "payinvchknbr", "paychknbr_ne",
    "payinvchkn", "uuid", "concaten", "folio", "txt_item", "txt_cabec", "grupoarticulo",
    "division", "po_group", "cod_tipo_mvto", "cod_tip_doc", "cod_transac", "potaxcode",
    "concaten tienda+NE", "Concatenar RCVN+COD BA", "Concatenar+ RCVN_EAN", "Trimestre",
}


def normalizar_para_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Fija un tipo estable por columna para que Parquet pueda guardar el trimestre.

    Varias columnas del origen traen **tipos mezclados** —`canfac_edi` llega con el número 0 y
    el texto "0" en la misma columna, unas celdas del exportador y otras editadas a mano— y
    pyarrow aborta con `ArrowTypeError` al escribir. Es el mismo tropiezo que ya se documentó
    en el caso anterior de Arca (bitácora 2026-08-11, "HALLAZGO 3").

    Se decide **por contenido y no por una lista fija**: la lista de aquel caso cubría 9
    columnas y aquí se guardan 122, así que dejar el resto como texto convertiría
    `compra_bruta` o `totfactura` en cadenas y saldrían como texto en el Excel de Andrea. Solo
    se tocan las columnas `object`: si todos sus valores son convertibles a número, es
    numérica; si no, texto. Los códigos se protegen aparte porque *parecen* números.
    """
    for columna in df.columns:
        if df[columna].dtype != object:
            continue
        if columna in COLUMNAS_CODIGO:
            df[columna] = df[columna].astype("string")
            continue
        valores = df[columna].dropna()
        if valores.empty:
            df[columna] = df[columna].astype("string")
            continue
        if pd.to_numeric(valores, errors="coerce").notna().all():
            df[columna] = pd.to_numeric(df[columna], errors="coerce")
        else:
            df[columna] = df[columna].astype("string")
    return df


def _es_vacio(valor) -> bool:
    """¿Esta celda debe quedar en blanco? Cubre None, NaN y `pd.NA` de una sola forma."""
    if valor is None:
        return True
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):  # arrays y tipos raros: no son vacío
        return False


def _escribir_compras(destino: Path, df: pd.DataFrame, columnas: list[str]) -> None:
    """Escribe el Compras del trimestre con las 122 columnas.

    No se reusa `excel_exporter.escribir_libro_compras` a propósito: ese escritor recorta el
    DataFrame a las 105 columnas de siempre y toma los encabezados de una constante global,
    así que las columnas nuevas se perderían y la única forma de meterlas sería parchear esa
    global — justo lo que no se debe hacer en un caso aislado como este.

    Se conserva el layout que ya tienen los Compras de Arca (**encabezado en la fila 2, datos
    desde la 3**) para que Andrea pueda comparar contra sus archivos sin recolocar nada. Sin
    logo ni títulos, que Óscar confirmó que no hacen falta. `constant_memory` mantiene el pico
    acotado: escribe cada renglón y lo suelta, en vez de armar el libro entero en RAM.
    """
    ensure_parent(destino)
    wb = xlsxwriter.Workbook(str(destino), {"constant_memory": True, "use_zip64": True})
    try:
        ws = wb.add_worksheet(f"Compras {df['rcvdt'].dt.year.mode().iat[0]:.0f}"
                              if "rcvdt" in df.columns and df["rcvdt"].notna().any() else "Compras")
        hdr = wb.add_format({"bold": True, "bg_color": "#00FD28", "border": 1,
                             "align": "center", "valign": "vcenter", "text_wrap": True})
        # Las columnas que Andrea agregó van resaltadas para que se distingan de un vistazo de
        # las que vienen del sistema — es como ella misma las dejó marcadas en su archivo.
        hdr_nueva = wb.add_format({"bold": True, "bg_color": "#FFD966", "border": 1,
                                   "align": "center", "valign": "vcenter", "text_wrap": True})
        nuevas = {c for grupo in NUEVAS_TRAS.values() for c in grupo}
        for i, col in enumerate(columnas):
            ws.write(1, i, RENOMBRES.get(col, col), hdr_nueva if col in nuevas else hdr)
            ws.set_column(i, i, 14)
        ws.freeze_panes(2, 0)
        ws.hide_gridlines(2)

        # Se recorta por POSICIÓN en cada renglón en vez de hacer `df[columnas]`: esa selección
        # copiaría los millones de renglones del trimestre, que es lo que se quiere evitar.
        posiciones = [df.columns.get_loc(c) for c in columnas]
        fila = 2
        for renglon in df.itertuples(index=False, name=None):
            for destino_col, origen in enumerate(posiciones):
                valor = renglon[origen]
                # Los vacíos se SALTAN, no se escriben. Sin esto, `pd.NA` (que no es None ni
                # NaN) caía en el `str()` de abajo y dejaba el texto "<NA>" en la celda — en
                # `fact_empaq Correcto`, que es justamente la columna que Andrea tiene que
                # llenar a mano, y en cualquier otra columna nullable vacía.
                if _es_vacio(valor):
                    continue
                if isinstance(valor, pd.Timestamp):
                    valor = valor.date().isoformat()
                elif not isinstance(valor, (str, int, float, bool)):
                    valor = str(valor)
                ws.write(fila, destino_col, valor)
            fila += 1
        if len(df):
            ws.autofilter(1, 0, 1 + len(df), len(columnas) - 1)
        wb.close()
    except BaseException:
        try:
            wb.close()
        except BaseException:
            pass
        destino.unlink(missing_ok=True)
        raise


def _ordenar_columnas(df: pd.DataFrame) -> list[str]:
    """Las 105 de siempre con las nuevas insertadas donde Andrea las dejó."""
    movidas = set(MOVER_TRAS)
    orden: list[str] = []
    for col in COMPRAS_COLUMNS:
        if col not in movidas:  # se coloca más abajo, tras su ancla
            orden.append(col)
        for reubicada, ancla in MOVER_TRAS.items():
            if ancla == col and reubicada in df.columns:
                orden.append(reubicada)
        for extra in NUEVAS_TRAS.get(col, []):
            if extra in df.columns:
                orden.append(extra)
    # Cualquier columna nueva cuya ancla no exista se agrega al final antes que perderla.
    faltan = [c for grupo in NUEVAS_TRAS.values() for c in grupo if c in df.columns and c not in orden]
    return [*orden, *faltan]


# ---------------------------------------------------------------------------------------
# Fase 1: extraer
# ---------------------------------------------------------------------------------------
def extraer(con_compras: bool = True, solo: list[str] | None = None) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    SALIDA.mkdir(parents=True, exist_ok=True)
    intervalos = _intervalos_trimestre(INICIO, FIN)
    if solo:
        intervalos = [iv for iv in intervalos if iv[0] in set(solo)]
    _log(f"{len(intervalos)} trimestres · caché en {CACHE}")

    anomalias: dict[str, int] = {}
    total_filas = 0
    for etiqueta, ini, fin in intervalos:
        ruta_cache = CACHE / f"{etiqueta}.parquet"
        destino = SALIDA / f"Compras_{BASE}_{etiqueta}.xlsx"
        if ruta_cache.exists():
            filas = pd.read_parquet(ruta_cache, columns=["folio"]).shape[0]
            total_filas += filas
            if destino.exists() or not con_compras:
                _log(f"[{etiqueta}] ya estaba · {filas:,} renglones")
                continue
            # El caché guarda el trimestre COMPLETO, así que un Compras que falta se puede
            # reescribir sin volver a consultar SQL ni a cruzar la CPA (8 min por trimestre).
            _log(f"[{etiqueta}] falta el Compras · se reescribe desde el caché")
            t = pd.read_parquet(ruta_cache)
            agregar_columnas_verificacion(t)
            _escribir_compras(destino, t, [c for c in _ordenar_columnas(t) if c in t.columns])
            del t
            gc.collect()
            continue

        t0 = time.time()
        _log(f"[{etiqueta}] SQL + cruce CPA...")
        salida = _salida_intervalo(PROVEEDOR, ini, fin, config.CPA_VISION_PARQUET_DIR)
        if salida is None:
            _log(f"[{etiqueta}] sin renglones")
            continue
        prepared, _, _ = salida

        marcas = calcular_columnas_andrea(prepared)
        for k, v in marcas.items():
            anomalias[k] = anomalias.get(k, 0) + v
        prepared["Trimestre"] = etiqueta
        if "folio" not in prepared.columns:
            prepared["folio"] = make_folio_series(prepared["strnbr"], prepared["rcvnbr"])

        # El caché primero, y COMPLETO: si el Excel revienta —o si hay que rehacerlo por un
        # cambio de formato— el trabajo caro (SQL + cruce de la CPA, ~8 min por trimestre) ya
        # está guardado. Parquet comprime bien, así que el caché entero ronda unos pocos GB
        # en disco local, que sobran.
        orden_cache = [c for c in _ordenar_columnas(prepared) if c in prepared.columns]
        # `folio` y `Trimestre` van al FINAL y aparte: no son columnas del Compras (por eso no
        # están en el orden espejo), pero la fase 2 las necesita para agrupar y para la columna
        # Trimestre de la Validación. Al ir al final, el Excel sigue saliendo con las 122 tal
        # cual, porque `_escribir_compras` toma solo las del orden espejo.
        servicio = [c for c in ("folio", "Trimestre") if c in prepared.columns and c not in orden_cache]
        prepared = normalizar_para_parquet(prepared)
        prepared[[*orden_cache, *servicio]].to_parquet(ruta_cache, index=False)

        if con_compras and not destino.exists():
            agregar_columnas_verificacion(prepared)
            orden = [c for c in _ordenar_columnas(prepared) if c in prepared.columns]
            _escribir_compras(destino, prepared, orden)

        total_filas += len(prepared)
        _log(f"[{etiqueta}] {len(prepared):,} renglones · {time.time()-t0:.0f}s")
        del prepared, salida
        gc.collect()

    _log(f"EXTRACCIÓN LISTA · {total_filas:,} renglones")
    if anomalias:
        _log(f"  anomalías (para revisar con Andrea): {anomalias}")


# ---------------------------------------------------------------------------------------
# Fase 2: generar las Validaciones por año
# ---------------------------------------------------------------------------------------
def _totales_por_folio() -> pd.DataFrame:
    """Debió pagar / pagado / diferencia por folio, sobre TODO el proveedor.

    Los totales se calculan globales, no por año, porque un folio puede tener renglones en dos
    trimestres (y en dos años): partirlo daría un "debió pagar" incompleto en cada lado. Es el
    mismo criterio que usa el pipeline normal.
    """
    acc: pd.DataFrame | None = None
    resumir = dict(debio=("debio", "sum"), pagado=("pagado", "max"), cheque=("cheque", "max"))
    for ruta in sorted(CACHE.glob("*.parquet")):
        t = pd.read_parquet(ruta, columns=["folio", "imp_aud", "tot_pagado_ne", "paynetamt"])
        agg = pd.DataFrame(
            {"debio": to_number(t["imp_aud"]).to_numpy(),
             "pagado": to_number(t["tot_pagado_ne"]).to_numpy(),
             # El importe del cheque, para poder contrastarlo con `tot_pagado_ne` (ver abajo).
             "cheque": to_number(t["paynetamt"]).to_numpy()},
            index=t["folio"].to_numpy(),
        ).groupby(level=0).agg(**resumir)
        acc = agg if acc is None else pd.concat([acc, agg]).groupby(level=0).agg(**resumir)
        del t, agg
        gc.collect()
    if acc is None:
        raise SystemExit("El caché está vacío: corre primero con --extraer.")
    for columna in ("debio", "pagado", "cheque"):
        acc[columna] = acc[columna].round(4)
    acc["dif"] = (acc["pagado"] - acc["debio"]).round(4)
    return acc


#: A partir de aquí se considera que `tot_pagado_ne` no cuadra con el cheque. No es 0 porque
#: hay redondeos de centavos que no significan nada; los casos reales son múltiplos (2x, 3x).
_TOLERANCIA_PAGO = 1.001

#: Columnas de aviso que se pegan al final del Consolidado.
COLUMNAS_ALERTA_PAGO = ["Importe del Cheque", "Pago NE / Cheque", "Alerta Pago"]


def marcar_pago_inconsistente(
    consolidado: pd.DataFrame, columnas: list[str], totales: pd.DataFrame
) -> list[str]:
    """Marca los folios donde el "Total Pagado" no cuadra con el importe del cheque.

    POR QUÉ: `tot_pagado_ne` viene de `F_COMPRAS` y en algunos folios llega **multiplicado**
    (se vio un caso de 27 renglones, un solo cheque y una sola factura, donde el cheque decía
    110,002.33 y `tot_pagado_ne` decía 330,006.43 — exactamente el triple). Es el problema que
    Andrea ya conocía ("todavía viene mal el tema de tot netamon", reunión 2026-08-26) y por el
    que ella rehace el cruce de pagos por su cuenta.

    Son pocos folios (~1.6 % de los que tienen diferencia) pero concentran más de la mitad del
    monto, así que un total leído sin este aviso engaña. NO se corrigen ni se excluyen: la
    diferencia se sigue calculando igual que siempre y lo que se agrega es **información** —
    el importe del cheque, la proporción y un aviso— para que Andrea sepa cuáles mirar primero.
    Decidir qué hacer con ellos es suyo, no de este script.
    """
    if consolidado.empty:
        return columnas
    folio = consolidado["Folio"].astype(str)
    cheque = folio.map(totales["cheque"])
    pagado = folio.map(totales["pagado"])
    proporcion = (pagado / cheque.where(cheque.ne(0))).round(3)

    consolidado["Importe del Cheque"] = cheque
    consolidado["Pago NE / Cheque"] = proporcion
    consolidado["Alerta Pago"] = np.where(
        proporcion > _TOLERANCIA_PAGO, "REVISAR PAGO", ""
    )
    return [*columnas, *COLUMNAS_ALERTA_PAGO]


def _trozos_del_anio(anio: int, folios: set[str], totales: pd.DataFrame):
    """Renglones de ese año que pertenecen a folios con diferencia, trimestre por trimestre."""
    for ruta in sorted(CACHE.glob(f"{anio}-*.parquet")):
        disponibles = set(pq.ParquetFile(ruta).schema_arrow.names)
        t = pd.read_parquet(ruta, columns=[c for c in COLUMNAS_VALIDACION if c in disponibles])
        t = t[t["folio"].isin(folios)]
        if t.empty:
            continue
        # Los totales por folio son GLOBALES; se pegan aquí para que el Consolidado del año
        # muestre el debió pagar completo del folio, no solo la parte de este trimestre.
        t["debio_pagar_ne"] = t["folio"].map(totales["debio"]).to_numpy()
        t["tot_pagado_ne"] = t["folio"].map(totales["pagado"]).to_numpy()
        t["dif_det_ne"] = t["folio"].map(totales["dif"]).to_numpy()
        yield t
        del t
        gc.collect()


def generar() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    umbral = config.VALIDATION_DIFFERENCE_THRESHOLD
    _log("Totales por folio (global)...")
    totales = _totales_por_folio()
    con_dif = set(totales.index[totales["dif"] > umbral])
    _log(f"  {len(totales):,} folios · {len(con_dif):,} con diferencia > {umbral}")

    anios = sorted({int(p.name[:4]) for p in CACHE.glob("*.parquet")})
    for anio in anios:
        t0 = time.time()
        _log(f"[{anio}] armando la Validación...")

        # Fuente del Consolidado: un renglón por folio del año. Es chica y evita cargar el
        # detalle completo dos veces.
        partes = []
        for t in _trozos_del_anio(anio, con_dif, totales):
            partes.append(t.drop_duplicates(subset="folio", keep="first"))
        if not partes:
            _log(f"[{anio}] sin folios con diferencia · se salta")
            continue
        src = pd.concat(partes, ignore_index=True).drop_duplicates(subset="folio", keep="first")
        del partes

        consolidado = build_consolidado(src)
        consolidado, ajustes, cols_cons = aplicar_ajustes_a_consolidado(src, consolidado)
        cols_cons = marcar_pago_inconsistente(consolidado, cols_cons, totales)
        folios_anio = set(consolidado["Folio"].tolist())
        total = float(pd.to_numeric(
            consolidado["Diferencia Ajustada" if "Diferencia Ajustada" in consolidado.columns
                        else "Diferencia"], errors="coerce").fillna(0).sum())

        destino = SALIDA / f"Validacion_{BASE}_{anio}.xlsx"
        ensure_parent(destino)
        wb = xlsxwriter.Workbook(str(destino), {"constant_memory": True, "use_zip64": True})
        try:
            fmts = _formatos_xlsx(wb)
            etiqueta = f"{PROVEEDOR} - {NOMBRE}"
            resumen = wb.add_worksheet("Resumen")
            resumen.set_column(2, 2, 22)
            resumen.set_column(3, 3, 28)
            resumen.write(6, 2, "Resultado Auditoria", fmts["hdr"])
            resumen.write(6, 3, "Observaciones Auditor", fmts["hdr"])
            resumen.write_number(7, 2, total, fmts["money"])
            resumen.write(7, 3, "Diferencia costos" if not consolidado.empty else "")

            # Cuánto del resultado se apoya en folios cuyo pago no cuadra con el cheque. Va en
            # el Resumen porque es lo primero que se mira: un total del que la mitad está
            # marcado no se lee igual que uno limpio.
            if "Alerta Pago" in consolidado.columns:
                marcados = consolidado[consolidado["Alerta Pago"].eq("REVISAR PAGO")]
                col_dif = ("Diferencia Ajustada" if "Diferencia Ajustada" in consolidado.columns
                           else "Diferencia")
                monto_marcado = float(
                    pd.to_numeric(marcados[col_dif], errors="coerce").fillna(0).sum()
                )
                resumen.write(9, 2, "Folios con pago a revisar", fmts["hdr"])
                resumen.write(9, 3, "Monto que aportan", fmts["hdr"])
                resumen.write_number(10, 2, len(marcados))
                resumen.write_number(10, 3, monto_marcado, fmts["money"])
                resumen.write(11, 3, "tot_pagado_ne no cuadra con el importe del cheque")

            _volcar_xlsx(wb, "Consolidado", cols_cons, consolidado, etiqueta, fmts,
                         con_totales=True, periodo=str(anio))
            if not ajustes.empty:
                _volcar_xlsx(wb, "Ajustes", AJUSTES_COLUMNS, ajustes, etiqueta, fmts,
                             con_totales=False, periodo=str(anio))

            stream = _DetalleStream(wb, DETALLE_COLUMNS_ARCA, etiqueta, fmts, str(anio))
            renglones = 0
            for t in _trozos_del_anio(anio, folios_anio, totales):
                det = build_detalle_rapido(t, folios_anio)
                det["Trimestre"] = t["Trimestre"].to_numpy()
                stream.escribir(det)
                renglones += len(det)
                del t, det
                gc.collect()
            wb.close()
        except BaseException:
            try:
                wb.close()
            except BaseException:
                pass
            destino.unlink(missing_ok=True)
            raise

        _log(f"[{anio}] {destino.name} · {len(consolidado):,} folios · "
             f"{renglones:,} renglones de detalle · ${total:,.2f} · {time.time()-t0:.0f}s")

    _log(f"VALIDACIONES LISTAS en {SALIDA}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--extraer", action="store_true", help="SQL + cruce + Compras (lento)")
    ap.add_argument("--generar", action="store_true", help="Validaciones por año desde el caché")
    ap.add_argument("--sin-compras", action="store_true",
                    help="No escribir los Compras trimestrales (solo el caché)")
    ap.add_argument("--solo", nargs="+", default=None, metavar="TRIM",
                    help="Extraer solo estos trimestres (p. ej. 2020-T1). Para probar")
    args = ap.parse_args()
    if not args.extraer and not args.generar:
        args.extraer = args.generar = True
    if args.extraer:
        extraer(con_compras=not args.sin_compras, solo=args.solo)
    if args.generar:
        generar()


if __name__ == "__main__":
    main()
