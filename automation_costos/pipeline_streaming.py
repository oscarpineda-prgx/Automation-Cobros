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
4. **Validación:** las filas de los folios con diferencia se dejan en pickles temporales (uno
   por trimestre) y `write_validation_streaming` arma con ellos una sola Validación
   consolidada, leyéndolos de uno en uno.

Es equivalente, renglón por renglón, al camino normal (verificado forzando un proveedor que
sí cabe por ambos caminos). No modifica el camino normal ni la función de SQL.
"""

from __future__ import annotations

import gc
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

import config
from automation_costos.cancelacion import SenalCancelacion, revisar
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
from automation_costos.utils import (
    anios_de_compras,
    formatear_periodo,
    make_folio_series,
    to_number,
)
from automation_costos.validation_exporter import (
    _COLUMNAS_FUENTE,
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
    cancelado: SenalCancelacion | None = None,
    reanudar: bool = False,
    por_mes: bool = False,
) -> ResultadoPipeline:
    """Genera Compras (un archivo por TRIMESTRE) + Validación consolidada, por trozos.

    Un año completo de estos proveedores (1.6M compras + 2.9M CPA) no cabe en RAM, así que se
    procesa por trimestre. La Validación se consolida globalmente en un solo archivo.

    `cancelado` se consulta **al empezar cada trimestre**, que es la unica frontera donde no
    hay nada a medio escribir. Estas corridas duran horas: sin puntos de corte, "Detener" no
    significaba nada justo donde mas falta hace.

    `reanudar` reusa los `Compras_*.xlsx` que ya estén en disco en vez de reescribirlos. Es
    para retomar una corrida que murió DESPUÉS de escribirlos (p. ej. en la Validación): el
    re-cruce es determinista, así que el archivo del disco es el mismo que se escribiría, y
    saltarlo ahorra los minutos que cuesta volcar cada Excel de cientos de MB.

    `por_mes` arranca partiendo por mes en vez de por trimestre. Normalmente no hace falta:
    el trimestre que no quepa se parte solo (ver `_recorrer_intervalos`). Está para forzarlo
    de antemano en una máquina que ya se sabe justa de memoria y ahorrarse el intento fallido."""
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
    intervalos = _intervalos_mes(start_date, end_date) if por_mes else _intervalos_trimestre(start_date, end_date)

    # -- PASADA 1: por trimestre -> cruzar y acumular por folio y factura (sin guardar filas) --
    marca_metricas = 0
    hubo_datos = False

    def _pasada1(etiqueta: str, ini: str, fin: str) -> None:
        nonlocal folio_acc, inv_acc, rfc, base, marca_metricas, hubo_datos
        marca_metricas = len(metricas_cruce)
        log(f"[pasada 1 · {etiqueta}] Compras desde SQL y cruce...")
        salida = _salida_intervalo(vendor, ini, fin, parquet_root, usar_cpa=usar_cpa,
                                   metricas=metricas_cruce)
        if salida is None:
            log("                   (sin renglones)")
            return
        prepared, rfc, base = salida
        # Los dos acumulados se calculan ANTES de reasignar ninguno: si el segundo `_fundir`
        # se queda sin memoria, `folio_acc` no debe haber absorbido ya este intervalo, o el
        # reintento por meses lo sumaría otra vez y los importes saldrían inflados.
        nuevo_folio = _fundir(folio_acc, _agg_por_clave(prepared, _folio(prepared), con_dsp=True), con_dsp=True)
        nuevo_inv = _fundir(inv_acc, _agg_por_clave(prepared, _invoice_group_key(prepared), con_dsp=False), con_dsp=False)
        folio_acc, inv_acc = nuevo_folio, nuevo_inv
        hubo_datos = True
        log(f"                   {len(prepared):,} renglones · acumulados")
        del prepared, salida
        gc.collect()

    def _deshacer_pasada1(etiqueta: str, ini: str, fin: str) -> None:
        # `folio_acc`/`inv_acc` son atómicos (ver arriba), así que solo hay que retirar lo que
        # el intento fallido sí alcanzó a registrar: su métrica de cruce.
        del metricas_cruce[marca_metricas:]

    # La pasada 1 puede partir hasta el DÍA —solo acumula, sus trozos no son entregables— pero
    # `con_datos` guarda el TRIMESTRE, no el trozo que acabó funcionando. Así la pasada 2
    # arranca otra vez desde el trimestre y degrada por su cuenta con piso de mes, en vez de
    # heredar una granularidad de días que produciría cientos de `Compras_*.xlsx`.
    for etiqueta, ini, fin in intervalos:
        hubo_datos = False
        _recorrer_intervalos(
            [(etiqueta, ini, fin)], _pasada1, log=log, cancelado=cancelado,
            fase="la pasada 1 de", deshacer=_deshacer_pasada1, piso=PISO_DIA,
        )
        if hubo_datos:
            con_datos.append(_Intervalo(etiqueta, ini, fin))

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
    #
    # 2026-08-25 · El detalle NO se acumula en memoria. Antes se guardaba `trozo.copy()` de
    # cada trimestre —las 105 columnas del Compras— y al final se concatenaba todo para
    # `write_validation_from_dataframe`, que arma el libro con openpyxl: los objetos Cell de
    # las ~10M celdas del "Detalle PAGOS" viven todos a la vez. PROPIMEX (472k renglones de
    # folios con diferencia) reventó ahí con MemoryError, con los cinco Compras ya escritos y
    # ~35 min de trabajo tirado. Ahora cada trimestre se recorta a las columnas que alimentan
    # la Validación y se deja en un pickle temporal; el libro lo escribe
    # `write_validation_streaming` (xlsxwriter en constant_memory), que ya existía para el
    # camino de los gigantes y lee los trozos de uno en uno. Mismo contenido, pico acotado.
    compras_paths: list[Path] = []
    trozos_detalle: list[Path] = []
    anios_detalle: set[int] = set()
    tmp = Path(tempfile.mkdtemp(prefix=f"val_{vendor}_"))
    try:
        def _pasada2(etiqueta: str, ini: str, fin: str) -> None:
            log(f"[pasada 2 · {etiqueta}] re-cruce y escritura del Compras...")
            salida = _salida_intervalo(vendor, ini, fin, parquet_root, usar_cpa=usar_cpa)
            if salida is None:  # no debería pasar (ya tuvo datos en la pasada 1)
                return
            prepared, _, _ = salida
            _pegar_totales_globales(prepared, folio_global, inv_global)

            # El detalle se guarda ANTES de escribir el Excel a propósito. Así, si el
            # intervalo no cabe y hay que reintentarlo partido, lo único que puede haber
            # quedado en disco es el pickle (que `_deshacer_pasada2` borra); un Compras del
            # trimestre conviviendo con los Compras de sus meses sería datos duplicados en
            # el entregable, y eso nadie lo nota hasta que alguien suma dos veces.
            folio = make_folio_series(prepared["strnbr"], prepared["rcvnbr"])
            trozo = prepared[folio.isin(folios_con_dif)]
            if not trozo.empty:
                columnas = [c for c in _COLUMNAS_FUENTE if c in trozo.columns]
                ligero = trozo[columnas].copy()
                ligero["folio"] = make_folio_series(ligero["strnbr"], ligero["rcvnbr"])
                anios_detalle.update(anios_de_compras(ligero))
                ruta = tmp / f"{etiqueta}.pkl"
                ligero.to_pickle(ruta)
                trozos_detalle.append(ruta)
                del ligero

            destino = proveedor_dir / f"Compras_{base}_{etiqueta}.xlsx"
            if reanudar and destino.exists():
                # El re-cruce es determinista, así que el Compras del disco es idéntico al que
                # se escribiría. Reusarlo ahorra los ~7 min por trimestre que cuesta volcar un
                # Excel de 150 MB cuando lo único que falta es la Validación.
                log(f"                   {destino.name} ya existe · se reusa")
            else:
                escribir_libro_compras(
                    destino, prepared, vendor=vendor, start_date=start_date, end_date=end_date
                )
            compras_paths.append(destino)
            log(f"                   {destino.name} · {len(trozo):,} renglones de folios con diferencia")
            del prepared, salida, trozo, folio
            gc.collect()

        def _deshacer_pasada2(etiqueta: str, ini: str, fin: str) -> None:
            ruta = tmp / f"{etiqueta}.pkl"
            if ruta in trozos_detalle:
                trozos_detalle.remove(ruta)
            ruta.unlink(missing_ok=True)
            destino = proveedor_dir / f"Compras_{base}_{etiqueta}.xlsx"
            if destino in compras_paths:
                compras_paths.remove(destino)

        _recorrer_intervalos(
            [(iv.etiqueta, iv.ini, iv.fin) for iv in con_datos],
            _pasada2, log=log, cancelado=cancelado,
            fase="la pasada 2 de", deshacer=_deshacer_pasada2, piso=PISO_MES,
        )

        # -- VALIDACIÓN consolidada (mismo escritor que el camino de los gigantes) ------------
        log("[validación] consolidando...")
        # Fuente del Consolidado: un renglón por folio. Es chica (un folio por renglón) y sale
        # de los mismos trozos, así que no hay que releer nada de SQL.
        src_partes = []
        for ruta in trozos_detalle:
            t = pd.read_pickle(ruta)
            src_partes.append(t.drop_duplicates(subset="folio", keep="first"))
            del t
        if src_partes:
            consolidado_src = pd.concat(src_partes, ignore_index=True).drop_duplicates(
                subset="folio", keep="first"
            )
        else:
            consolidado_src = pd.DataFrame(columns=COMPRAS_COLUMNS)
        del src_partes
        gc.collect()

        def _chunks():
            for ruta in trozos_detalle:
                yield pd.read_pickle(ruta)

        validacion_path = proveedor_dir / f"Validacion_{base}.xlsx"
        log(f"[validación] streaming · {len(consolidado_src):,} folios con diferencia")
        write_validation_streaming(
            consolidado_src, _chunks(), validacion_path,
            periodo=formatear_periodo(anios_detalle),
        )
        log(f"[validación] {validacion_path.name}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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


#: Hasta dónde se puede partir un intervalo que no cabe en memoria.
#:
#: `"dia"` es para las fases que solo **acumulan** (sus trozos van a un pickle temporal y el
#: entregable no cambia): ahí partir fino sale gratis y salva la corrida.
#:
#: `"mes"` es para las fases que **escriben un archivo por intervalo**. Ahí el piso no es
#: técnico sino de utilidad: partir al día produciría ~450 `Compras_*.xlsx` de un proveedor y
#: tardaría días — la corrida "no falla", pero el entregable es inservible. Medido con
#: PROPIMEX a 2.5 GB el 2026-08-26. Un año en 12-15 archivos sí se puede trabajar.
PISO_DIA = "dia"
PISO_MES = "mes"


def _subdividir(ini: str, fin: str, piso: str = PISO_DIA) -> list[tuple[str, str, str]]:
    """Trozos más finos de un intervalo, o `[]` si ya no hay nada más fino que intentar.

    La cadena es trimestre → meses → días, cortada en `piso`. Se devuelve el primer nivel que
    **de verdad** parta el intervalo en más de un trozo: subdividir un mes en "un mes" sería
    un bucle infinito reintentando exactamente lo mismo.
    """
    niveles = (_intervalos_mes,) if piso == PISO_MES else (_intervalos_mes, _intervalos_dia)
    for partir in niveles:
        trozos = partir(ini, fin)
        if len(trozos) > 1:
            return trozos
    return []


def _recorrer_intervalos(
    intervalos: Sequence[tuple[str, str, str]],
    trabajo: Callable[[str, str, str], None],
    *,
    log: Callable[[str], None],
    cancelado: SenalCancelacion | None = None,
    fase: str = "",
    deshacer: Callable[[str, str, str], None] | None = None,
    piso: str = PISO_DIA,
) -> None:
    """Corre `trabajo(etiqueta, ini, fin)` sobre cada intervalo, **degradando la granularidad
    del que no quepa en memoria**.

    Cuánto cabe en RAM no se puede saber de antemano: depende de la máquina del auditor, de
    lo que tenga abierto y de cuántos CFDI traiga ese trimestre en la CPA. Elegir el tamaño
    del trozo con un umbral fijo es adivinar, y equivocarse cuesta la corrida entera. Aquí no
    se adivina: se intenta el trimestre y, si revienta, se reintenta partido en meses; si un
    mes tampoco cabe, en días. El proveedor sale igual, solo repartido en más archivos.

    `deshacer(etiqueta, ini, fin)` es la red de seguridad del reintento: el intento fallido
    pudo dejar efectos a medias (un acumulado ya fundido, un pickle escrito), y los
    sub-intervalos van a rehacer ese mismo trabajo. Sin deshacerlos primero, los importes se
    contarían dos veces y la auditoría saldría mal — un fallo peor que el MemoryError,
    porque no se nota. Quien llama es el único que sabe qué dejó a medias.
    """
    for etiqueta, ini, fin in intervalos:
        revisar(cancelado, f"antes de {fase or 'el intervalo'} {etiqueta}")
        sin_memoria = False
        try:
            trabajo(etiqueta, ini, fin)
        except MemoryError:
            # El reintento NO puede ir aquí dentro: mientras corre el `except`, la excepción
            # viva mantiene su traceback, y el traceback mantiene los frames de `trabajo`
            # **con sus locals** — o sea el DataFrame que acaba de reventar la memoria.
            # `gc.collect()` no lo libera porque sigue referenciado, así que el reintento
            # moriría igual. Se marca la bandera, se sale del handler (ahí muere el
            # traceback y se libera todo) y se reintenta fuera. Misma trampa documentada en
            # `pipeline.generar_salida_proveedor`.
            sin_memoria = True
        if not sin_memoria:
            continue

        gc.collect()
        if deshacer is not None:
            deshacer(etiqueta, ini, fin)
        trozos = _subdividir(ini, fin, piso)
        if not trozos:
            raise MemoryError(
                f"El intervalo {etiqueta} ({ini}..{fin}) no cabe en memoria ni partido por "
                f"{piso}. Cierra otros programas, o corre este proveedor como grande: "
                "`cpa-validacion-grande` para la Validación (aguanta mucha menos RAM porque "
                "solo trae los renglones auditables) y `cpa-compras-grande` para los Compras, "
                "que es resumible."
            )
        log(f"      [{etiqueta}] sin memoria · se reintenta en {len(trozos)} trozos más finos")
        _recorrer_intervalos(
            trozos, trabajo, log=log, cancelado=cancelado, fase=fase, deshacer=deshacer,
            piso=piso,
        )


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

        def _acumular(etiqueta: str, ini: str, fin: str) -> None:
            nonlocal folio_acc, rfc, base
            log(f"[{etiqueta}] auditables desde SQL + cruce...")
            salida = _salida_intervalo(vendor, ini, fin, parquet_root, filtro_filas=FILTRO_AUDITABLES, usar_cpa=usar_cpa)
            if salida is None:
                log("           (sin renglones)")
                return
            prepared, rfc, base = salida
            ligero = prepared[[c for c in columnas if c in prepared.columns]].copy()
            del prepared

            folio = make_folio_series(ligero["strnbr"], ligero["rcvnbr"])
            agg = pd.DataFrame(
                {"imp": to_number(ligero["imp_aud"]).to_numpy(),
                 "pay": to_number(ligero["tot_pagado_ne"]).to_numpy()},
                index=folio.to_numpy(),
            ).groupby(level=0).agg(imp=("imp", "sum"), pay=("pay", "max"))
            nuevo_acc = agg if folio_acc is None else pd.concat([folio_acc, agg]).groupby(level=0).agg(
                imp=("imp", "sum"), pay=("pay", "max")
            )

            # `folio_acc` se reasigna hasta DESPUÉS de que el pickle esté en disco: si la
            # escritura revienta, el acumulado no debe haber absorbido ya este intervalo, o
            # el reintento partido lo sumaría dos veces y la Validación saldría inflada.
            ruta = tmp / f"{etiqueta}.pkl"
            ligero.to_pickle(ruta)
            folio_acc = nuevo_acc
            trozos.append(ruta)
            log(f"           {len(ligero):,} auditables · acumulados")
            del ligero, salida
            gc.collect()

        def _deshacer(etiqueta: str, ini: str, fin: str) -> None:
            ruta = tmp / f"{etiqueta}.pkl"
            if ruta in trozos:
                trozos.remove(ruta)
            ruta.unlink(missing_ok=True)

        _recorrer_intervalos(intervalos, _acumular, log=log, deshacer=_deshacer)

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

    def _escribir(etiqueta: str, ini: str, fin: str) -> None:
        nonlocal base
        if base and (output_dir / base / f"Compras_{base}_{etiqueta}.xlsx").exists():
            log(f"[{etiqueta}] ya existe · se salta")
            rutas.append(output_dir / base / f"Compras_{base}_{etiqueta}.xlsx")
            return

        salida = _salida_intervalo(vendor, ini, fin, parquet_root, usar_cpa=usar_cpa)  # sin filtro: TODOS los renglones
        if salida is None:
            log(f"[{etiqueta}] sin renglones")
            return
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

    def _deshacer(etiqueta: str, ini: str, fin: str) -> None:
        # `escribir_libro_compras` ya borra su propio archivo trunco, así que aquí solo se
        # retira la ruta de la lista; los sub-intervalos escribirán las suyas.
        if base:
            destino = output_dir / base / f"Compras_{base}_{etiqueta}.xlsx"
            if destino in rutas:
                rutas.remove(destino)

    # Piso de mes: este camino escribe un Compras por intervalo, y partir al día daría
    # cientos de archivos. Es resumible, así que un fallo aquí no tira lo ya escrito.
    _recorrer_intervalos(intervalos, _escribir, log=log, deshacer=_deshacer, piso=PISO_MES)

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


def _intervalos_dia(start_date: str, end_date: str) -> list[tuple[str, str, str]]:
    """Parte el periodo en días (etiqueta 'YYYY-MM-DD').

    Es el último recurso de `_subdividir`, para el mes que ni así cabe. Un día de compras
    entra en cualquier máquina; el costo es que el proveedor sale repartido en muchos
    archivos, que es infinitamente mejor que no salir.
    """
    dias = pd.date_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="D")
    return [(d.date().isoformat(), d.date().isoformat(), d.date().isoformat()) for d in dias]


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
