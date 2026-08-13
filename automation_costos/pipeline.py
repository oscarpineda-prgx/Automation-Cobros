"""Pipeline de una sola acción: de un proveedor a su archivo de salida.

Encadena las cuatro etapas post-descarga en memoria:

    SQL (compras) → cruce CPA Vision → recálculo → Validación de Condiciones

Asume que la descarga de CPA Vision ya ocurrió (el Parquet existe). No descarga nada.

El Compras se escribe completo aunque sea grande (decisión de Óscar, opción B; ver
docs/RENDIMIENTO_EXPORTADOR.md). La Validación se arma desde el DataFrame en memoria, sin
releer el Compras gigante.

Cada proveedor se entrega como un paquete autocontenido dentro de `output_dir`:

    output_dir/
      <numero>_<nombre>/
        Compras_<numero>_<nombre>.xlsx
        Validacion_<numero>_<nombre>.xlsx
        cpa vision soportes/
          <request_id>_..._1.zip      (los ZIP de CPA Vision que respaldan la salida)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from automation_costos.calculations import prepare_compras_dataframe
from automation_costos.cruce_cpa import (
    ResultadoCruce,
    cargar_cpa,
    cruzar,
    request_id_principal,
    rfc_de_compras,
    solo_digitos,
)
from automation_costos.database import contar_compras, fetch_compras
from automation_costos.excel_exporter import write_compras_files
from automation_costos.utils import clean_code, safe_filename, to_number
from automation_costos.validation_exporter import write_validation_from_dataframe

# Subcarpeta, dentro de la del proveedor, donde se dejan los ZIP de CPA Vision que
# respaldan la salida. Con espacios, tal como se acordó nombrarla.
SUBCARPETA_SOPORTES = "cpa vision soportes"

# Cobertura EDI minima del propio Compras para aceptar seguir SIN datos de CPA Vision.
# Es el mismo 90% con el que la planeacion decide si un proveedor-año hay que descargarlo:
# por encima de eso la factura electronica ya viene poblada de origen y el cruce no aporta.
_MINIMO_EDI_SIN_CPA = 0.90


def _cobertura_edi(df) -> float:
    """Proporcion de renglones que ya traen costo del CFDI (`ctonto_edi`) en el Compras."""
    if "ctonto_edi" not in df.columns or df.empty:
        return 0.0
    return float((to_number(df["ctonto_edi"]) != 0).mean())

# Arriba de estos renglones el proveedor NO cabe en memoria de una sola vez y se procesa
# año por año (pipeline_streaming). Debajo se usa el camino normal (todo en memoria), que es
# más rápido. Celaya (1.24M) y Nestlé (~1.3M) caben; Arca/Pepsico (10-12M) no.
MAX_FILAS_EN_MEMORIA = 2_500_000


@dataclass(slots=True)
class ResultadoPipeline:
    rfc: str
    compras_path: Path  # el primer Compras (para la GUI); todos en `compras_paths`
    validacion_path: Path
    cruce: ResultadoCruce | None = None  # None en el camino por año (se cruza por año)
    compras_paths: list[Path] = field(default_factory=list)
    proveedor_dir: Path | None = None
    soportes: list[Path] = field(default_factory=list)


def generar_salida_proveedor(
    vendor: str,
    start_date: str,
    end_date: str,
    parquet_root: Path | str,
    output_dir: Path | str,
    *,
    log: Callable[[str], None] = print,
    usar_cpa: bool = True,
    anios_cruce: set[int] | None = None,
) -> ResultadoPipeline:
    """Genera la salida de un proveedor eligiendo el camino según su tamaño.

    Hace un COUNT barato en SQL: si el proveedor cabe en memoria usa el camino normal (todo
    de una vez, más rápido); si no, lo procesa año por año (pipeline_streaming), acotando la
    memoria. El resultado es equivalente; solo cambia cómo se calcula.
    """
    try:
        total = contar_compras(vendor, start_date, end_date)
        log(f"[0/4] {total:,} renglones en SQL para {vendor} ({start_date}..{end_date}).")
    except Exception as exc:  # noqa: BLE001 — si el COUNT falla, seguimos por el camino normal
        total = 0
        log(f"[0/4] No se pudo contar de antemano ({exc}); se intenta el camino normal.")

    if total > MAX_FILAS_EN_MEMORIA:
        log(f"      Proveedor grande (> {MAX_FILAS_EN_MEMORIA:,}): se procesa por trimestres.")
        from automation_costos.pipeline_streaming import generar_salida_proveedor_por_anios

        resultado = generar_salida_proveedor_por_anios(
            vendor, start_date, end_date, parquet_root, output_dir, log=log, usar_cpa=usar_cpa
        )
    else:
        resultado = _generar_salida_en_memoria(
            vendor, start_date, end_date, parquet_root, output_dir, log=log,
            usar_cpa=usar_cpa, anios_cruce=anios_cruce,
        )
    actualizar_reporte_consolidado(output_dir, log=log)
    return resultado


def actualizar_reporte_consolidado(output_dir: Path | str, *, log: Callable[[str], None] = print) -> None:
    """Refresca el reporte de control de diferencias de toda la carpeta de entregables.

    Se cuelga del final de cada proveedor para que el archivo que revisa Héctor esté al día
    sin que nadie tenga que acordarse de regenerarlo. **Nunca** puede tumbar la corrida: el
    entregable del proveedor ya está escrito y es lo que importa, así que cualquier fallo
    aquí se reporta y se sigue.
    """
    try:
        from automation_costos.reporte_diferencias import actualizar_reporte

        destino = actualizar_reporte(output_dir, log=lambda m: None)
        log(f"[+] Reporte de diferencias actualizado: {destino.name}")
    except Exception as exc:  # noqa: BLE001 — el reporte es accesorio, el entregable no
        log(f"[+] No se pudo actualizar el reporte de diferencias: {exc}")


def _mascara_anios(raw, anios: set[int] | None):
    """Renglones cuyo año de recibo está en `anios`, o None si aplica a todos.

    Devolver None cuando no hay recorte evita partir y reconcatenar el DataFrame en el caso
    normal, que es el de todos los proveedores menos un par.
    """
    if not anios:
        return None
    fechas = pd.to_datetime(raw.get("rcvdt"), errors="coerce")
    mascara = fechas.dt.year.isin(anios)
    return None if bool(mascara.all()) else mascara


def _generar_salida_en_memoria(
    vendor: str,
    start_date: str,
    end_date: str,
    parquet_root: Path | str,
    output_dir: Path | str,
    *,
    log: Callable[[str], None] = print,
    usar_cpa: bool = True,
    anios_cruce: set[int] | None = None,
) -> ResultadoPipeline:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log(f"[1/4] Compras de {vendor} ({start_date}..{end_date}) desde SQL Server...")
    raw = fetch_compras(vendor, start_date, end_date)
    if raw.empty:
        raise ValueError(f"El proveedor {vendor} no devolvió compras en ese periodo.")
    rfc = rfc_de_compras(raw)
    log(f"      {len(raw):,} renglones · RFC {rfc}")

    cruce = None
    cpa = None
    if not usar_cpa:
        # Decision explicita de quien llama: la columna `accion` del plan dice solo
        # "Ejecutar", asi que el entregable sale con el EDI que ya trae el Compras. No se
        # mira el Parquet aunque tenga datos de ese RFC: que el resultado dependa de que
        # se alcanzo a descargar haria la corrida irreproducible.
        log("[2/4] Sin cruce con CPA Vision (ejecucion sin CPA, por indicacion del plan).")
    else:
        log("[2/4] Rellenando columnas EDI desde CPA Vision...")
        barcodes = set(raw["codbarra"].map(solo_digitos)) - {""}
        cpa = cargar_cpa(rfc, parquet_root, barcodes=barcodes)
    if usar_cpa and cpa.empty:
        # Sin CPA se sigue adelante, pero solo si el propio Compras ya trae la factura
        # electronica: hay proveedores que la planeacion marca "Ejecutar" y no "Descargar"
        # justamente porque su cobertura EDI ya viene alta de origen (p. ej. Laboratorios
        # Serral, 98.9%) y no hay nada que descargar de CPA. Abortar ahi impedia generar
        # un entregable perfectamente valido.
        #
        # Si en cambio el Compras viene VACIO de EDI, la falta de CPA si es un problema
        # real —parquet equivocado, RFC mal resuelto o descarga pendiente— y ahi si se
        # aborta, porque la Validacion saldria sin sustento.
        cobertura = _cobertura_edi(raw)
        if cobertura < _MINIMO_EDI_SIN_CPA:
            raise ValueError(
                f"El RFC {rfc} no tiene datos en el dataset Parquet y el Compras solo trae "
                f"{cobertura:.1%} de cobertura EDI. Falta descargarlo de CPA Vision."
            )
        log(
            f"      SIN datos de CPA para {rfc}; se continua porque el Compras ya trae "
            f"{cobertura:.1%} de cobertura EDI (no habia nada que cruzar)."
        )
    elif usar_cpa:
        # `anios_cruce` acota el cruce a ciertos años. Hace falta porque hay proveedores
        # cuya columna `accion` pide "Descargar/Ejecutar" en un año y solo "Ejecutar" en
        # los otros: cruzar el periodo completo metería CPA en años que el plan excluye.
        # El año de un renglón es el de su fecha de recibo, que es por donde F_COMPRAS
        # filtra el periodo.
        objetivo = _mascara_anios(raw, anios_cruce)
        if objetivo is None:
            cruce = cruzar(raw, cpa)
        else:
            log(f"      Cruce acotado a los años {sorted(anios_cruce)}: "
                f"{int(objetivo.sum()):,} de {len(raw):,} renglones.")
            parte = raw.loc[objetivo].copy()
            resto = raw.loc[~objetivo]
            cruce = cruzar(parte, cpa, en_sitio=True)
            # sort_index restituye el orden original: las dos mitades vuelven a intercalarse
            # como venían de SQL, no una detrás de la otra.
            cruce.df = pd.concat([cruce.df, resto]).sort_index()
        for linea in cruce.resumen().splitlines():
            log("      " + linea)

    # Cada proveedor tiene su propia carpeta "<numero>_<nombre>"; adentro van el Compras,
    # la Validación y la subcarpeta de soportes de CPA Vision. Así queda un paquete
    # autocontenido por proveedor.
    base = _nombre_base(raw, vendor)
    proveedor_dir = output_dir / base
    proveedor_dir.mkdir(parents=True, exist_ok=True)
    validacion_path = proveedor_dir / f"Validacion_{base}.xlsx"

    # Si hubo cruce se sigue con su DataFrame; si no lo hubo (proveedor sin CPA y con el EDI
    # ya poblado), se sigue con el Compras tal como vino de SQL.
    trabajo = cruce.df if cruce is not None else raw

    # Soltamos las tablas de origen (grandes y tipo object) antes de la parte pesada:
    # el cruce ya produjo su propio DataFrame y no volvemos a usar raw ni cpa.
    del raw, cpa

    # Preparamos UNA sola vez y reusamos para Validación y Compras (antes se preparaba
    # dos veces, duplicando el pico de memoria en proveedores grandes). `en_sitio` deja
    # que la preparación reescriba el DataFrame del cruce en vez de copiarlo.
    prepared = prepare_compras_dataframe(trabajo, en_sitio=True)
    if cruce is not None:
        cruce.df = prepared
    del trabajo

    # La Validación va PRIMERO: es el entregable real y es chica. Así sale aunque el
    # Compras gigante falle, y trabaja sobre el DataFrame antes de que el exportador le
    # aplique los valores de fórmula en sitio.
    log("[3/4] Generando la Validación de Condiciones...")
    write_validation_from_dataframe(prepared, validacion_path)
    log(f"      {validacion_path}")

    log("[4/4] Generando el Compras (esto puede tardar en proveedores grandes)...")
    compras_paths = write_compras_files(
        prepared, proveedor_dir, base, vendor=vendor,
        start_date=start_date, end_date=end_date, already_prepared=True,
    )
    if len(compras_paths) > 1:
        log(f"      Proveedor grande: se partio en {len(compras_paths)} archivos por año.")
    for ruta in compras_paths:
        log(f"      {ruta}")

    # Los ZIP de CPA Vision quedan junto a la salida como soporte. Es un paso opcional:
    # si algo falla (falta el ZIP, permisos, disco), se avisa pero NO se tumba la salida,
    # que ya está escrita.
    # Sin cruce no se copian soportes: el entregable no se apoya en ningun CFDI, y meter
    # los ZIP sugeriria lo contrario a quien lo revise.
    soportes = (
        copiar_soportes_cpa(rfc, parquet_root, proveedor_dir, log=log) if usar_cpa else []
    )

    return ResultadoPipeline(
        rfc=rfc,
        compras_path=compras_paths[0],
        validacion_path=validacion_path,
        cruce=cruce,
        compras_paths=compras_paths,
        proveedor_dir=proveedor_dir,
        soportes=soportes,
    )


def copiar_soportes_cpa(
    rfc: str,
    parquet_root: Path | str,
    proveedor_dir: Path,
    *,
    origen: Path | str | None = None,
    log: Callable[[str], None] = print,
) -> list[Path]:
    """Copia a `proveedor_dir/SUBCARPETA_SOPORTES` el ZIP de soporte de CPA Vision.

    Se copia (no se mueve) **una sola descarga: la más completa**. Si el proveedor se bajó
    dos veces, la segunda descarga es la misma información repetida, así que NO se copia
    —solo se avisa que se ignoró—. Un mismo request puede venir partido en varios ZIP
    (`..._1.zip`, `..._2.zip`): esos sí se copian todos, porque son una sola descarga en
    pedazos, no información duplicada.

    Idempotente (si el ZIP ya está con el mismo tamaño no se recopia) y nunca lanza:
    cualquier problema se reporta y devuelve lo que sí se pudo copiar.
    """
    # Por convención los ZIP viven junto al dataset Parquet (p. ej. outputs/cpa_vision/,
    # con el Parquet en outputs/cpa_vision/parquet).
    origen = Path(origen) if origen else Path(parquet_root).parent
    destino = Path(proveedor_dir) / SUBCARPETA_SOPORTES

    try:
        soporte = request_id_principal(rfc, parquet_root)
    except Exception as exc:  # noqa: BLE001 — soporte opcional, no debe tumbar la salida
        log(f"      [soportes] No se pudo resolver el request de {rfc}: {exc}")
        return []

    if not soporte.principal:
        log(f"      [soportes] Sin request para {rfc}; no hay ZIP que copiar.")
        return []

    # Una descarga y una sola: las demás son la misma información repetida.
    if soporte.redundantes:
        log(
            f"      [soportes] {rfc} se descargó {len(soporte.redundantes) + 1} veces; se "
            f"copia solo la más completa (request {soporte.principal}). Ignoradas por "
            f"duplicadas: {', '.join(soporte.redundantes)}."
        )
    # Aviso fuerte si —caso que hoy no ocurre— el principal no cubriera todos los años.
    if not soporte.cobertura_completa:
        faltan = sorted(set(soporte.anios_totales) - set(soporte.anios_principal))
        log(
            f"      [soportes] AVISO: el request {soporte.principal} no cubre los años "
            f"{', '.join(faltan)}. Revisa manualmente si necesitas otra descarga."
        )

    if not origen.is_dir():
        log(f"      [soportes] No existe la carpeta de descargas: {origen}")
        return []

    # El nombre empieza con "<request_id>_"; el guion evita casar un id prefijo de otro.
    candidatos = sorted(origen.glob(f"{soporte.principal}_*.zip"))
    if not candidatos:
        log(f"      [soportes] No se hallaron ZIP para request {soporte.principal} en {origen}.")
        return []

    destino.mkdir(parents=True, exist_ok=True)
    copiados: list[Path] = []
    for zip_path in candidatos:
        final = destino / zip_path.name
        try:
            if final.exists() and final.stat().st_size == zip_path.stat().st_size:
                copiados.append(final)  # ya estaba, se reutiliza
                continue
            shutil.copy2(zip_path, final)
            copiados.append(final)
        except Exception as exc:  # noqa: BLE001
            log(f"      [soportes] No se pudo copiar {zip_path.name}: {exc}")

    if copiados:
        log(f"      [soportes] {len(copiados)} ZIP (request {soporte.principal}) en {destino}")
    return copiados


def _nombre_base(raw, vendor: str) -> str:
    codigo = clean_code(vendor) or (
        clean_code(raw["vndnbr"].dropna().iloc[0])
        if "vndnbr" in raw.columns and raw["vndnbr"].notna().any()
        else ""
    )
    nombre = (
        str(raw["vndname"].dropna().iloc[0]).strip()
        if "vndname" in raw.columns and raw["vndname"].notna().any()
        else ""
    )
    return safe_filename(f"{codigo}_{nombre}".strip("_")).rstrip(" .")
