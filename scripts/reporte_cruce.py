"""Reporte estructurado en Excel con las metricas del CRUCE CPA Vision -> Compras.

Es el mensaje que la aplicacion muestra en pantalla al terminar la Etapa 2 ("Celdas vacias
rellenadas: N", "Con CFDI encontrado: N (x%)"...), pero guardado en un archivo, con una fila
por proveedor-anio. Peticion de Monica (2026-08-19): ese resumen se pierde al cerrar la app.

Sirve TAMBIEN para los proveedores YA ejecutados
------------------------------------------------
No hace falta abrir los Compras ya generados (son 122 archivos y 20.4 GB de Excel: releerlos
tardaria horas). El cruce se vuelve a calcular en memoria desde sus dos fuentes originales
—SQL y el Parquet de CPA Vision— que es justo lo que ya hace `scripts/beneficio_cpa.py`.
La diferencia es que aqui SI se conserva el `ResultadoCruce`, que trae todas las metricas.

El resultado es identico al de la corrida original siempre que no hayan cambiado ni la base
ni el acervo CPA. Si entretanto se descargo mas CPA de ese proveedor, el reporte reflejara
la cobertura de HOY, que es mayor: es un dato mas util, pero conviene saberlo al leerlo.

Es RESUMIBLE: cada proveedor terminado se anota en un CSV de avance, asi que si se corta a
media corrida (o si se agrega un proveedor nuevo) se retoma sin repetir lo ya calculado.

Uso:
    .venv/Scripts/python.exe scripts/reporte_cruce.py                  # los ya entregados
    .venv/Scripts/python.exe scripts/reporte_cruce.py --vendors 741 5462
    .venv/Scripts/python.exe scripts/reporte_cruce.py --rehacer        # ignora el avance
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import pandas as pd

import config
from automation_costos.cruce_cpa import cargar_cpa, cruzar, rfc_de_compras, solo_digitos
from automation_costos.database import fetch_compras

PARQUET = config.CPA_VISION_PARQUET_DIR
SALIDA = RAIZ / "outputs" / "Reporte_Cruce_CPA.xlsx"
AVANCE = RAIZ / "outputs" / "_reporte_cruce_avance.csv"
ANIOS = range(2020, 2026)


def proveedores_ya_entregados() -> dict[int, str]:
    """Numero -> nombre, leyendo las carpetas de entregables que tienen Validacion."""
    encontrados: dict[int, str] = {}
    raiz = config.ENTREGABLES_DIR
    if not raiz.exists():
        return encontrados
    for carpeta in raiz.iterdir():
        if not carpeta.is_dir():
            continue
        m = re.match(r"^(\d+)_(.*)$", carpeta.name)
        if not m:
            continue
        if any(v.name.startswith("Validacion_") for v in carpeta.glob("*.xlsx")):
            encontrados[int(m.group(1))] = m.group(2).strip()
    return encontrados


def metricas_de_un_anio(vendor: int, anio: int) -> dict | None:
    """Vuelve a cruzar UN proveedor-anio y devuelve las metricas del cruce.

    Se procesa anio por anio a proposito: acota la memoria y permite que un proveedor
    grande no tumbe la corrida.
    """
    compras = fetch_compras(str(vendor), f"{anio}-01-01", f"{anio}-12-31")
    if compras.empty:
        return None

    # Mismo criterio de `beneficio_cpa`: se excluyen los movimientos 161/162 y el anio se
    # define por `rcvdt` (fecha de recibo). Ver LOGICA_NEGOCIO seccion 13.
    tipo_mvto = pd.to_numeric(compras["cod_tipo_mvto"], errors="coerce")
    reg = compras[~tipo_mvto.isin([161, 162])].copy()
    reg = reg[pd.to_datetime(reg["rcvdt"], errors="coerce").dt.year == anio].copy()
    if reg.empty:
        return None

    nombre = str(compras["vndname"].iloc[0]).strip()
    rfc = rfc_de_compras(reg)
    edi_antes = int(pd.to_numeric(reg["ctonto_edi"], errors="coerce").fillna(0).ne(0).sum())

    fila = {
        "Proveedor": vendor,
        "Nombre": nombre,
        "RFC": rfc,
        "Anio": anio,
        "Renglones de compras": len(reg),
        "Con CFDI encontrado": 0,
        "  por serie + folio": 0,
        "  por folio (respaldo)": 0,
        "Sin CFDI": len(reg),
        "% de cruce": 0.0,
        "Celdas vacias rellenadas": 0,
        "CFDI en conflicto (no usados)": 0,
        "Difieren en IVA": 0,
        "Difieren en IEPS": 0,
        "Cobertura EDI antes": edi_antes,
        "Cobertura EDI despues": edi_antes,
        "Renglones ganados": 0,
        "Tiene CPA descargada": "No",
    }

    if not rfc:
        return fila

    cpa = cargar_cpa(rfc, PARQUET, barcodes={solo_digitos(b) for b in reg["codbarra"]})
    if cpa.empty:
        return fila

    fila["Tiene CPA descargada"] = "Si"
    # AQUI esta la diferencia con beneficio_cpa: se conserva el resultado del cruce, que es
    # el objeto que trae las cifras que la aplicacion imprime en pantalla.
    resultado = cruzar(reg, cpa, en_sitio=True)

    edi_despues = int(pd.to_numeric(reg["ctonto_edi"], errors="coerce").fillna(0).ne(0).sum())
    fila.update({
        "Con CFDI encontrado": resultado.cruzados,
        "  por serie + folio": resultado.cruzados_por_serie,
        "  por folio (respaldo)": resultado.cruzados_por_folio,
        "Sin CFDI": resultado.renglones - resultado.cruzados,
        "% de cruce": round(resultado.tasa_cruce, 4),
        "Celdas vacias rellenadas": resultado.celdas_llenadas,
        "CFDI en conflicto (no usados)": resultado.descartados_ambiguos,
        "Difieren en IVA": resultado.discrepancias_iva,
        "Difieren en IEPS": resultado.discrepancias_ieps,
        "Cobertura EDI despues": edi_despues,
        "Renglones ganados": edi_despues - edi_antes,
    })
    return fila


def resumen_por_proveedor(detalle: pd.DataFrame) -> pd.DataFrame:
    """Una fila por proveedor: la suma de sus anios, con los porcentajes recalculados.

    Los porcentajes se recalculan sobre los totales; promediar los porcentajes de cada anio
    daria un numero distinto y equivocado (cada anio pesa diferente).
    """
    if detalle.empty:
        return detalle
    sumas = {
        "Renglones de compras": "sum", "Con CFDI encontrado": "sum",
        "  por serie + folio": "sum", "  por folio (respaldo)": "sum", "Sin CFDI": "sum",
        "Celdas vacias rellenadas": "sum", "CFDI en conflicto (no usados)": "sum",
        "Difieren en IVA": "sum", "Difieren en IEPS": "sum",
        "Cobertura EDI antes": "sum", "Cobertura EDI despues": "sum",
        "Renglones ganados": "sum",
    }
    agrupado = detalle.groupby(["Proveedor", "Nombre", "RFC"], as_index=False).agg(sumas)
    agrupado["Anios cubiertos"] = (
        detalle.groupby(["Proveedor", "Nombre", "RFC"])["Anio"]
        .apply(lambda s: " ".join(str(a) for a in sorted(s)))
        .values
    )
    total = agrupado["Renglones de compras"].replace(0, pd.NA)
    agrupado["% de cruce"] = (agrupado["Con CFDI encontrado"] / total).fillna(0).round(4)
    agrupado["% cobertura EDI antes"] = (agrupado["Cobertura EDI antes"] / total).fillna(0).round(4)
    agrupado["% cobertura EDI despues"] = (agrupado["Cobertura EDI despues"] / total).fillna(0).round(4)
    agrupado["Mejora (puntos)"] = (
        agrupado["% cobertura EDI despues"] - agrupado["% cobertura EDI antes"]
    ).round(4)
    return agrupado.sort_values("Proveedor")


def escribir_excel(detalle: pd.DataFrame, destino: Path) -> None:
    """Dos hojas: el resumen por proveedor primero (es lo que se consulta)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    resumen = resumen_por_proveedor(detalle)
    columnas_resumen = [
        "Proveedor", "Nombre", "RFC", "Anios cubiertos", "Renglones de compras",
        "Con CFDI encontrado", "% de cruce", "Sin CFDI", "Celdas vacias rellenadas",
        "Cobertura EDI antes", "% cobertura EDI antes",
        "Cobertura EDI despues", "% cobertura EDI despues",
        "Renglones ganados", "Mejora (puntos)",
        "CFDI en conflicto (no usados)", "Difieren en IVA", "Difieren en IEPS",
    ]
    with pd.ExcelWriter(destino, engine="xlsxwriter") as writer:
        resumen[[c for c in columnas_resumen if c in resumen.columns]].to_excel(
            writer, sheet_name="Resumen por proveedor", index=False
        )
        detalle.sort_values(["Proveedor", "Anio"]).to_excel(
            writer, sheet_name="Detalle por proveedor-anio", index=False
        )
        libro = writer.book
        porcentaje = libro.add_format({"num_format": "0.0%"})
        millar = libro.add_format({"num_format": "#,##0"})
        for hoja, tabla in (("Resumen por proveedor", resumen),
                            ("Detalle por proveedor-anio", detalle)):
            ws = writer.sheets[hoja]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(tabla), max(0, len(tabla.columns) - 1))
            for i, nombre in enumerate(tabla.columns):
                if nombre.startswith("%") or nombre.startswith("Mejora"):
                    ws.set_column(i, i, 16, porcentaje)
                elif tabla[nombre].dtype.kind in "if":
                    ws.set_column(i, i, 16, millar)
                else:
                    ws.set_column(i, i, 30 if nombre == "Nombre" else 14)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vendors", nargs="*", type=int,
                    help="Numeros de proveedor. Vacio = todos los que ya tienen entregable")
    ap.add_argument("--excluir", nargs="*", type=int, default=[],
                    help="Proveedores a saltar. Sirve para dejar los gigantes para otra "
                         "corrida: son pocos y se llevan la mayor parte del tiempo")
    ap.add_argument("--rehacer", action="store_true", help="Ignora el avance guardado")
    ap.add_argument("--salida", default=str(SALIDA))
    ap.add_argument("--sin-consolidar", action="store_true",
                    help="No alimenta el reporte oficial; solo deja el detalle por anio")
    args = ap.parse_args()

    entregados = proveedores_ya_entregados()
    objetivo = args.vendors or sorted(entregados)
    if args.excluir:
        antes = len(objetivo)
        objetivo = [v for v in objetivo if v not in set(args.excluir)]
        print(f"Excluidos: {antes - len(objetivo)} proveedor(es)")
    if not objetivo:
        raise SystemExit("No se encontro ningun proveedor con entregable.")

    previas = pd.DataFrame()
    if AVANCE.exists() and not args.rehacer:
        previas = pd.read_csv(AVANCE)
        ya_hechos = set(previas["Proveedor"].astype(int))
        objetivo = [v for v in objetivo if v not in ya_hechos]
        print(f"Avance previo: {len(ya_hechos)} proveedores ya calculados.")

    print(f"Por calcular: {len(objetivo)} proveedores · {datetime.now():%H:%M:%S}")
    filas = list(previas.to_dict("records")) if not previas.empty else []

    for n, vendor in enumerate(objetivo, start=1):
        nombre = entregados.get(vendor, "")
        print(f"[{n}/{len(objetivo)}] {vendor} {nombre[:40]}", flush=True)
        nuevas = []
        for anio in ANIOS:
            try:
                fila = metricas_de_un_anio(vendor, anio)
            except Exception as exc:  # noqa: BLE001 — un proveedor no debe tumbar el lote
                print(f"    ! {anio}: {exc}")
                continue
            if fila:
                nuevas.append(fila)
                print(f"    {anio}: {fila['Con CFDI encontrado']:,} de "
                      f"{fila['Renglones de compras']:,} cruzados · "
                      f"{fila['Celdas vacias rellenadas']:,} celdas")
        filas.extend(nuevas)
        # Se guarda el avance despues de CADA proveedor: la corrida es larga y no se puede
        # perder por un corte.
        pd.DataFrame(filas).to_csv(AVANCE, index=False)

    detalle = pd.DataFrame(filas)
    if detalle.empty:
        raise SystemExit("No se obtuvo ninguna metrica.")

    destino = Path(args.salida)
    escribir_excel(detalle, destino)
    print(f"\nProveedores: {detalle['Proveedor'].nunique()} · filas: {len(detalle)}")
    print(f"Detalle por anio -> {destino}")

    # Ademas se alimenta el reporte OFICIAL, el mismo que actualizan las ejecuciones nuevas
    # (por terminal o por la GUI), para que no haya dos archivos con la misma informacion.
    # Ahi va UNA fila por proveedor, con sus anios sumados y marcada como "reconstruido".
    if not args.sin_consolidar:
        oficial = registrar_en_reporte_oficial(detalle)
        if oficial:
            print(f"Reporte oficial  -> {oficial}")


def registrar_en_reporte_oficial(detalle: pd.DataFrame) -> Path | None:
    """Vuelca una fila por proveedor al historico comun `Historico_Cruce_CPA.parquet`."""
    from automation_costos.metricas_cruce import registrar

    filas = []
    for (prov, nombre, rfc), grupo in detalle.groupby(["Proveedor", "Nombre", "RFC"], dropna=False):
        renglones = int(grupo["Renglones de compras"].sum())
        cruzados = int(grupo["Con CFDI encontrado"].sum())
        filas.append({
            "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Proveedor": str(prov),
            "Nombre": nombre,
            "RFC": rfc,
            # Los anios que de verdad trajeron renglones, no el rango pedido.
            "Periodo": " ".join(str(a) for a in sorted(grupo["Anio"].unique())),
            "Renglones de compras": renglones,
            "Con CFDI encontrado": cruzados,
            "% de cruce": round(cruzados / renglones, 4) if renglones else 0.0,
            "por serie + folio": int(grupo["  por serie + folio"].sum()),
            "por folio (respaldo)": int(grupo["  por folio (respaldo)"].sum()),
            "Sin CFDI": renglones - cruzados,
            "Celdas vacias rellenadas": int(grupo["Celdas vacias rellenadas"].sum()),
            "CFDI en conflicto (no usados)": int(grupo["CFDI en conflicto (no usados)"].sum()),
            "Difieren en IVA": int(grupo["Difieren en IVA"].sum()),
            "Difieren en IEPS": int(grupo["Difieren en IEPS"].sum()),
            # Se marca distinto de las ejecuciones reales: estas cifras se recalcularon
            # despues, con el acervo CPA de hoy, no con el que habia al generar el entregable.
            "Origen": "reconstruido",
        })
    return registrar(filas)


if __name__ == "__main__":
    main()
