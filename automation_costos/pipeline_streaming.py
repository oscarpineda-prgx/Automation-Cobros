"""Pipeline por intervalos (año por año) para proveedores que NO caben en memoria.

Algunos proveedores traen 10-12 millones de renglones de compras: el DataFrame completo no
cabe en RAM y `fetch_compras` muere con MemoryError. Este módulo los procesa **un año a la
vez** —llamando `F_COMPRAS(vendor, año-01-01, año-12-31)` tal cual, sin tocar la función— y
consolida el resultado. El pico de memoria queda acotado a un solo año (~1.4M renglones).

Se hace en **dos pasadas** (la consulta a SQL es barata, del orden de segundos):

1. **Pasada 1 — acumular:** por año, traer + cruzar con CPA + preparar; acumular por folio la
   suma de `imp_aud` (debió pagar), la suma de `impaud` de display (dpagar) y el máx de
   `paynetamt` (pagado). Se descartan los renglones; solo queda la tabla chica por folio.
2. **Global:** con esos acumulados se obtiene el debió pagar / pagado **por folio a nivel de
   todo el proveedor**, de modo que los pocos folios que cruzan un año salen exactos.
3. **Pasada 2 — escribir:** por año, traer + cruzar otra vez, pegarle los totales globales del
   folio y escribir `Compras_<base>_<año>.xlsx`. Se juntan las filas de los folios con
   diferencia para la Validación.
4. **Validación:** con esas filas (chicas) se reusa `write_validation_from_dataframe` → una
   sola Validación consolidada.

Es equivalente, renglón por renglón, al camino normal (verificado forzando un proveedor que
sí cabe por ambos caminos). No modifica el camino normal ni la función de SQL.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

import config
from automation_costos.calculations import (
    COMPRAS_COLUMNS,
    apply_display_formula_values,
    prepare_compras_dataframe,
    _invoice_group_key,
)
from automation_costos.cruce_cpa import (
    cargar_cpa,
    cruzar,
    normalizar_factura,
    rfc_de_compras,
    solo_digitos,
)
from automation_costos.database import fetch_compras
from automation_costos.excel_exporter import escribir_libro_compras
from automation_costos.pipeline import (
    ResultadoPipeline,
    _nombre_base,
    actualizar_reporte_consolidado,
    copiar_soportes_cpa,
)
from automation_costos.utils import make_folio_series, to_number
from automation_costos.validation_exporter import (
    _COLUMNAS_FUENTE,
    write_validation_from_dataframe,
    write_validation_rapida,
    write_validation_streaming,
)

# Renglones sin nota de entrada (rcvnbr nulo) no son auditables a nivel folio y hoy caen en
# un folio degenerado que nunca se marca como diferencia: excluirlos NO cambia la Validación,
# solo la aligera. Ver el análisis en docs/LOGICA_NEGOCIO.md.
FILTRO_AUDITABLES = "rcvnbr IS NOT NULL"


@dataclass(slots=True)
class _Intervalo:
    """Un trimestre que sí trajo renglones (para no re-consultar los vacíos en la 2a pasada)."""

    etiqueta: str  # p. ej. "2020-T1"
    ini: str
    fin: str


def generar_salida_proveedor_por_anios(
    vendor: str,
    start_date: str,
    end_date: str,
    parquet_root: Path | str,
    output_dir: Path | str,
    *,
    log: Callable[[str], None] = print,
    usar_cpa: bool = True,
) -> ResultadoPipeline:
    """Genera Compras (un archivo por TRIMESTRE) + Validación consolidada, por trozos.

    Un año completo de estos proveedores (1.6M compras + 2.9M CPA) no cabe en RAM, así que se
    procesa por trimestre. La Validación se consolida globalmente en un solo archivo."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    umbral = config.VALIDATION_DIFFERENCE_THRESHOLD

    rfc = ""
    base = ""
    folio_acc: pd.DataFrame | None = None  # nivel nota de entrada (NE)
    inv_acc: pd.DataFrame | None = None  # nivel factura
    con_datos: list[_Intervalo] = []
    # Un ResultadoCruce por trimestre; al final se suman para el reporte de metricas.
    metricas_cruce: list = []
    intervalos = _intervalos_trimestre(start_date, end_date)

    # -- PASADA 1: por trimestre -> cruzar y acumular por folio y factura (sin guardar filas) --
    for etiqueta, ini, fin in intervalos:
        log(f"[pasada 1 · {etiqueta}] Compras desde SQL y cruce...")
        salida = _salida_intervalo(vendor, ini, fin, parquet_root, usar_cpa=usar_cpa,
                                   metricas=metricas_cruce)
        if salida is None:
            log("                   (sin renglones)")
            continue
        prepared, rfc, base = salida
        folio_acc = _fundir(folio_acc, _agg_por_clave(prepared, _folio(prepared), con_dsp=True), con_dsp=True)
        inv_acc = _fundir(inv_acc, _agg_por_clave(prepared, _invoice_group_key(prepared), con_dsp=False), con_dsp=False)
        con_datos.append(_Intervalo(etiqueta, ini, fin))
        log(f"                   {len(prepared):,} renglones · acumulados")
        del prepared, salida
        gc.collect()

    if folio_acc is None or not con_datos:
        raise ValueError(f"El proveedor {vendor} no devolvió compras en {start_date}..{end_date}.")

    # -- GLOBAL: totales por folio y por factura de todo el proveedor ------------------------
    folio_global = _totales_globales(folio_acc, con_dsp=True)
    inv_global = _totales_globales(inv_acc, con_dsp=False)
    folios_con_dif = set(folio_global.index[folio_global["dif"] > umbral])
    log(f"[global] {len(folio_global):,} folios · {len(folios_con_dif):,} con diferencia > {umbral}")

    proveedor_dir = output_dir / base
    proveedor_dir.mkdir(parents=True, exist_ok=True)

    # -- PASADA 2: por trimestre -> re-cruzar, pegar totales globales, escribir Compras + detalle
    compras_paths: list[Path] = []
    detalle_partes: list[pd.DataFrame] = []
    for iv in con_datos:
        log(f"[pasada 2 · {iv.etiqueta}] re-cruce y escritura del Compras...")
        salida = _salida_intervalo(vendor, iv.ini, iv.fin, parquet_root, usar_cpa=usar_cpa)
        if salida is None:  # no debería pasar (ya tuvo datos en la pasada 1)
            continue
        prepared, _, _ = salida
        _pegar_totales_globales(prepared, folio_global, inv_global)

        destino = proveedor_dir / f"Compras_{base}_{iv.etiqueta}.xlsx"
        escribir_libro_compras(destino, prepared, vendor=vendor, start_date=start_date, end_date=end_date)
        compras_paths.append(destino)

        folio = make_folio_series(prepared["strnbr"], prepared["rcvnbr"])
        trozo = prepared[folio.isin(folios_con_dif)]
        if not trozo.empty:
            detalle_partes.append(trozo.copy())
        log(f"                   {destino.name} · {len(trozo):,} renglones de folios con diferencia")
        del prepared, salida
        gc.collect()

    # -- VALIDACIÓN consolidada (reusa el escritor del camino normal) ------------------------
    log("[validación] consolidando...")
    df_dif = (
        pd.concat(detalle_partes, ignore_index=True)
        if detalle_partes
        else pd.DataFrame(columns=COMPRAS_COLUMNS)
    )
    validacion_path = proveedor_dir / f"Validacion_{base}.xlsx"
    write_validation_from_dataframe(df_dif, validacion_path)
    log(f"[validación] {validacion_path.name}")

    # Sin cruce no se copian soportes: el entregable no se apoya en ningun CFDI.
    soportes = (
        copiar_soportes_cpa(rfc, parquet_root, proveedor_dir, log=log) if usar_cpa else []
    )

    # Métricas del cruce: aquí hay un ResultadoCruce por trimestre, así que se suman antes
    # de anotarlos. Solo la pasada 1 los acumuló, para no contarlos dos veces.
    if metricas_cruce:
        from automation_costos.metricas_cruce import fila_desde_varios, registrar

        fila = fila_desde_varios(
            metricas_cruce,
            proveedor=str(vendor),
            nombre=base.split("_", 1)[1] if "_" in base else "",
            rfc=rfc,
            periodo=f"{str(start_date)[:4]}-{str(end_date)[:4]}",
        )
        registrar(fila, output_dir, log=log)

    return ResultadoPipeline(
        rfc=rfc,
        compras_path=compras_paths[0],
        validacion_path=validacion_path,
        cruce=None,  # el cruce se hizo por año; no hay un único ResultadoCruce
        compras_paths=compras_paths,
        proveedor_dir=proveedor_dir,
        soportes=soportes,
    )


def _intervalos_trimestre(start_date: str, end_date: str) -> list[tuple[str, str, str]]:
    """Parte el periodo en trimestres, recortados al periodo pedido.

    Cada trimestre (~400k renglones en estos proveedores) cabe holgado en memoria. Devuelve
    `(etiqueta, ini, fin)`, p. ej. ("2020-T1", "2020-01-01", "2020-03-31")."""
    lo, hi = pd.to_datetime(start_date), pd.to_datetime(end_date)
    salida: list[tuple[str, str, str]] = []
    for anio in range(lo.year, hi.year + 1):
        for q, mes0 in enumerate((1, 4, 7, 10), start=1):
            ini = max(pd.Timestamp(anio, mes0, 1), lo)
            fin = min(pd.Timestamp(anio, mes0, 1) + pd.offsets.MonthEnd(3), hi)  # último día del trimestre
            if ini > fin:
                continue
            salida.append((f"{anio}-T{q}", ini.date().isoformat(), fin.date().isoformat()))
    return salida


def generar_validacion_grande(
    vendor: str,
    start_date: str,
    end_date: str,
    parquet_root: Path | str,
    output_dir: Path | str,
    *,
    por_mes: bool = False,
    log: Callable[[str], None] = print,
    usar_cpa: bool = True,
) -> ResultadoPipeline:
    """Genera SOLO la Validación consolidada de un proveedor gigante, rápido y sin OOM.

    Una pasada por trimestre: trae solo los renglones auditables (con nota de entrada),
    cruza, prepara, y **vuelca a disco** las columnas de la Validación (no acumula en RAM).
    Al final consolida el debió-pagar por folio GLOBAL, se queda con los folios con
    diferencia y escribe la Validación con el motor rápido (xlsxwriter). No escribe el
    Compras (decisión de Óscar: la Validación primero).
    """
    import shutil
    import tempfile

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    umbral = config.VALIDATION_DIFFERENCE_THRESHOLD
    columnas = [c for c in _COLUMNAS_FUENTE]

    tmp = Path(tempfile.mkdtemp(prefix=f"val_{vendor}_"))
    try:
        rfc = ""
        base = ""
        folio_acc: pd.DataFrame | None = None
        trozos: list[Path] = []

        intervalos = _intervalos_mes(start_date, end_date) if por_mes else _intervalos_trimestre(start_date, end_date)
        for etiqueta, ini, fin in intervalos:
            log(f"[{etiqueta}] auditables desde SQL + cruce...")
            salida = _salida_intervalo(vendor, ini, fin, parquet_root, filtro_filas=FILTRO_AUDITABLES, usar_cpa=usar_cpa)
            if salida is None:
                log("           (sin renglones)")
                continue
            prepared, rfc, base = salida
            ligero = prepared[[c for c in columnas if c in prepared.columns]].copy()
            del prepared

            folio = make_folio_series(ligero["strnbr"], ligero["rcvnbr"])
            agg = pd.DataFrame(
                {"imp": to_number(ligero["imp_aud"]).to_numpy(),
                 "pay": to_number(ligero["tot_pagado_ne"]).to_numpy()},
                index=folio.to_numpy(),
            ).groupby(level=0).agg(imp=("imp", "sum"), pay=("pay", "max"))
            folio_acc = agg if folio_acc is None else pd.concat([folio_acc, agg]).groupby(level=0).agg(
                imp=("imp", "sum"), pay=("pay", "max")
            )

            ruta = tmp / f"{etiqueta}.pkl"
            ligero.to_pickle(ruta)
            trozos.append(ruta)
            log(f"           {len(ligero):,} auditables · acumulados")
            del ligero, salida
            gc.collect()

        if folio_acc is None or not trozos:
            raise ValueError(f"El proveedor {vendor} no devolvió compras auditables en {start_date}..{end_date}.")

        # Totales GLOBALES por folio y folios con diferencia.
        debio = folio_acc["imp"].round(4)
        pagado = folio_acc["pay"].round(4)
        dif = (pagado - debio).round(4)
        con_dif = set(dif.index[dif > umbral])
        log(f"[global] {len(folio_acc):,} folios auditables · {len(con_dif):,} con diferencia > {umbral}")

        # Lee un trozo (trimestre/mes), lo filtra a los folios con diferencia y le pega los
        # totales globales por folio. Se usa en dos pasadas para NO tener el detalle completo
        # (millones de renglones) en memoria a la vez.
        def _enriquecer(ruta: Path) -> pd.DataFrame | None:
            t = pd.read_pickle(ruta)
            folio = make_folio_series(t["strnbr"], t["rcvnbr"])
            t = t[folio.isin(con_dif)]
            if t.empty:
                return None
            folio = make_folio_series(t["strnbr"], t["rcvnbr"])
            t["debio_pagar_ne"] = folio.map(debio).to_numpy()
            t["tot_pagado_ne"] = folio.map(pagado).to_numpy()
            t["dif_det_ne"] = folio.map(dif).to_numpy()
            t["folio"] = folio.to_numpy()
            return t

        # Pasada 1: fuente del Consolidado — un renglón por folio (chico, cabe siempre).
        src_partes: list[pd.DataFrame] = []
        for ruta in trozos:
            t = _enriquecer(ruta)
            if t is None:
                continue
            src_partes.append(t.drop_duplicates(subset="folio", keep="first"))
            del t
            gc.collect()
        if src_partes:
            consolidado_src = pd.concat(src_partes, ignore_index=True).drop_duplicates(
                subset="folio", keep="first"
            )
        else:
            consolidado_src = pd.DataFrame(columns=columnas)
        del src_partes

        # Pasada 2: Detalle en streaming — un trozo a la vez.
        def _chunks():
            for ruta in trozos:
                t = _enriquecer(ruta)
                if t is not None:
                    yield t

        proveedor_dir = output_dir / base
        proveedor_dir.mkdir(parents=True, exist_ok=True)
        validacion_path = proveedor_dir / f"Validacion_{base}.xlsx"
        log(f"[validación] streaming · {len(consolidado_src):,} folios con diferencia (detalle completo)")
        write_validation_streaming(consolidado_src, _chunks(), validacion_path)
        log(f"[validación] {validacion_path.name}")

        # Sin cruce no se copian soportes (mismo criterio que el camino normal).
        soportes = (
            copiar_soportes_cpa(rfc, parquet_root, proveedor_dir, log=log) if usar_cpa else []
        )
        # Los gigantes se corren con `cpa-validacion-grande`, que no pasa por
        # `generar_salida_proveedor`; sin este enganche quedarían fuera del reporte de control.
        actualizar_reporte_consolidado(output_dir, log=log)
        return ResultadoPipeline(
            rfc=rfc,
            compras_path=validacion_path,  # no hay Compras en este modo; se apunta a la Validación
            validacion_path=validacion_path,
            compras_paths=[],
            proveedor_dir=proveedor_dir,
            soportes=soportes,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def generar_compras_grande(
    vendor: str,
    start_date: str,
    end_date: str,
    parquet_root: Path | str,
    output_dir: Path | str,
    *,
    por_mes: bool = False,
    log: Callable[[str], None] = print,
    usar_cpa: bool = True,
) -> list[Path]:
    """Escribe SOLO los archivos de Compras de un proveedor gigante, por intervalo, resumible.

    Una pasada por trimestre (o por mes con `por_mes=True`): trae el intervalo completo
    (todos los renglones, no solo auditables — el Compras es la referencia completa), cruza
    con CPA (ya filtrada por factura, lo que lo hace caber), y escribe `Compras_<base>_<etiq>.xlsx`.

    **Resumible:** si el archivo de un intervalo ya existe, se salta sin re-consultar SQL —
    así no se pierde el trabajo ya hecho (p. ej. los trimestres de Arca 2020-2021). No escribe
    Validación (esa se genera aparte con `generar_validacion_grande`), así que no acumula nada
    en memoria: el pico queda acotado a un intervalo.

    Nota: los totales por folio del Compras (`debio_pagar_ne`, etc.) son **por intervalo**; para
    los pocos folios cuyos pedidos cruzan un intervalo difieren del global, pero el número
    exacto de auditoría vive en la Validación (que sí es global). Es una referencia.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    intervalos = _intervalos_mes(start_date, end_date) if por_mes else _intervalos_trimestre(start_date, end_date)

    # base desde la carpeta ya existente del proveedor, para poder SALTAR sin consultar SQL.
    existentes = sorted(output_dir.glob(f"{vendor}_*"))
    base = existentes[0].name if existentes else ""

    rutas: list[Path] = []
    for etiqueta, ini, fin in intervalos:
        if base and (output_dir / base / f"Compras_{base}_{etiqueta}.xlsx").exists():
            log(f"[{etiqueta}] ya existe · se salta")
            rutas.append(output_dir / base / f"Compras_{base}_{etiqueta}.xlsx")
            continue

        salida = _salida_intervalo(vendor, ini, fin, parquet_root, usar_cpa=usar_cpa)  # sin filtro: TODOS los renglones
        if salida is None:
            log(f"[{etiqueta}] sin renglones")
            continue
        prepared, _, base = salida
        proveedor_dir = output_dir / base
        proveedor_dir.mkdir(parents=True, exist_ok=True)
        destino = proveedor_dir / f"Compras_{base}_{etiqueta}.xlsx"
        if destino.exists():  # por si base se resolvió recién aquí
            log(f"[{etiqueta}] ya existe · se salta")
        else:
            escribir_libro_compras(destino, prepared, vendor=vendor, start_date=start_date, end_date=end_date)
            log(f"[{etiqueta}] {destino.name} · {len(prepared):,} renglones")
        rutas.append(destino)
        del prepared, salida
        gc.collect()

    log(f"Listo: {len(rutas)} archivos de Compras en {output_dir / base if base else output_dir}")
    return rutas


def _intervalos_mes(start_date: str, end_date: str) -> list[tuple[str, str, str]]:
    """Parte el periodo en meses (etiqueta 'YYYY-MM'), recortados al periodo pedido."""
    lo, hi = pd.to_datetime(start_date), pd.to_datetime(end_date)
    salida: list[tuple[str, str, str]] = []
    cur = pd.Timestamp(lo.year, lo.month, 1)
    while cur <= hi:
        ini = max(cur, lo)
        fin = min(cur + pd.offsets.MonthEnd(1), hi)
        salida.append((f"{cur.year}-{cur.month:02d}", ini.date().isoformat(), fin.date().isoformat()))
        cur = cur + pd.offsets.MonthBegin(1)
    return salida


def _salida_intervalo(
    vendor: str, ini: str, fin: str, parquet_root: Path | str, *,
    filtro_filas: str = "", usar_cpa: bool = True, metricas: list | None = None,
) -> tuple[pd.DataFrame, str, str] | None:
    """Trae un intervalo, lo cruza con CPA y lo deja preparado + con valores de fórmula.

    Devuelve `(prepared, rfc, base)` o `None` si no trajo renglones. Es determinista:
    llamarlo dos veces (una por pasada) da exactamente el mismo resultado.

    Si se pasa `metricas`, se le agrega el `ResultadoCruce` de este intervalo. Va como
    acumulador opcional y no como valor de retorno a proposito: esta funcion se llama DOS
    veces por intervalo (una por pasada), asi que solo la pasada 1 pasa la lista y no se
    cuentan dos veces las mismas celdas.
    """
    raw = fetch_compras(vendor, ini, fin, filtro_filas=filtro_filas)
    if raw.empty:
        return None
    rfc = rfc_de_compras(raw)
    base = _nombre_base(raw, vendor)
    barcodes = set(raw["codbarra"].map(solo_digitos)) - {""}
    # Llaves de factura del lote: recortan la CPA a lo que puede cruzar (clave en Pepsico).
    facturas = (
        set(raw["invnbr"].map(normalizar_factura)) - {""},
        set(raw["invnbr"].map(solo_digitos)) - {""},
    )
    if usar_cpa:
        cpa = cargar_cpa(rfc, parquet_root, barcodes=barcodes, facturas=facturas)
        # en_sitio: sin copias extra (poseemos raw y cpa de este año); es lo que hace caber en RAM.
        resultado_cruce = cruzar(raw, cpa, en_sitio=True)
        if metricas is not None:
            metricas.append(resultado_cruce)
        prepared = prepare_compras_dataframe(resultado_cruce.df, en_sitio=True)
        del cpa
    else:
        # Sin cruce: el Compras sale con el EDI que ya traia de origen. Es la ejecucion que
        # pide la columna `accion` cuando dice solo "Ejecutar".
        prepared = prepare_compras_dataframe(raw, en_sitio=True)
    prepared = apply_display_formula_values(prepared, en_sitio=True)[COMPRAS_COLUMNS]
    gc.collect()
    return prepared, rfc, base


def _folio(df: pd.DataFrame) -> pd.Series:
    return make_folio_series(df["strnbr"], df["rcvnbr"])


def _agg_por_clave(prepared: pd.DataFrame, clave: pd.Series, *, con_dsp: bool) -> pd.DataFrame:
    """Agrega un año por la clave dada (folio o factura).

    `imp` = suma de `imp_aud` (debió pagar). `pay` = máx del pagado ya calculado por el
    camino normal (`tot_pagado_ne` a nivel folio, `tot_pagado_inv` a nivel factura), que ya
    resuelve de qué columna sale el pagado. `dsp` (solo folio) = suma de `impaud` de display,
    que alimenta `dpagar`.
    """
    pagado_col = "tot_pagado_ne" if con_dsp else "tot_pagado_inv"
    datos = {
        "imp": to_number(prepared["imp_aud"]).to_numpy(),
        "pay": to_number(prepared[pagado_col]).to_numpy(),
    }
    if con_dsp:
        datos["dsp"] = to_number(prepared["impaud"]).to_numpy()
    d = pd.DataFrame(datos, index=clave.to_numpy())
    return d.groupby(level=0).agg(**_reglas(con_dsp))


def _fundir(acc: pd.DataFrame | None, nuevo: pd.DataFrame, *, con_dsp: bool) -> pd.DataFrame:
    """Funde el agregado de un año con lo acumulado: sumas se suman, pagado toma el máx."""
    if acc is None:
        return nuevo
    return pd.concat([acc, nuevo]).groupby(level=0).agg(**_reglas(con_dsp))


def _reglas(con_dsp: bool) -> dict:
    reglas = {"imp": ("imp", "sum"), "pay": ("pay", "max")}
    if con_dsp:
        reglas["dsp"] = ("dsp", "sum")
    return reglas


def _totales_globales(acc: pd.DataFrame, *, con_dsp: bool) -> pd.DataFrame:
    """De los acumulados por clave saca debió pagar / pagado / diferencia globales."""
    out = pd.DataFrame(index=acc.index)
    out["debio"] = acc["imp"].round(4)
    out["pagado"] = acc["pay"].round(4)
    out["dif"] = (out["pagado"] - out["debio"]).round(4)
    if con_dsp:
        out["dpagar"] = acc["dsp"].round(4)
    return out


def _pegar_totales_globales(
    df: pd.DataFrame, folio_global: pd.DataFrame, inv_global: pd.DataFrame
) -> None:
    """Sobrescribe (in situ) las columnas de folio y de factura con los totales GLOBALES.

    Solo estas dependen de todos los renglones de su grupo; el resto ya es correcto por
    renglón. Así los grupos que cruzan un año quedan con el total del proveedor completo.
    """
    folio = _folio(df)
    df["debio_pagar_ne"] = folio.map(folio_global["debio"]).to_numpy()
    df["dpagar"] = folio.map(folio_global["dpagar"]).to_numpy()
    df["tot_pagado_ne"] = folio.map(folio_global["pagado"]).to_numpy()
    df["dif_det_ne"] = (to_number(df["tot_pagado_ne"]) - to_number(df["debio_pagar_ne"])).round(4)

    inv = _invoice_group_key(df)
    df["debio_pagar_inv"] = inv.map(inv_global["debio"]).to_numpy()
    df["tot_pagado_inv"] = inv.map(inv_global["pagado"]).to_numpy()
    df["dif_det_inv"] = (to_number(df["tot_pagado_inv"]) - to_number(df["debio_pagar_inv"])).round(4)
