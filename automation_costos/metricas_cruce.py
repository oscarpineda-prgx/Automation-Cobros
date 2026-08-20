"""Deja por escrito las metricas del cruce CPA Vision -> Compras de cada ejecucion.

El resumen que la aplicacion imprime al terminar la Etapa 2 ("Celdas vacias rellenadas: N",
"Con CFDI encontrado: N") solo vivia en la ventana: al cerrarla se perdia, y no habia forma
de saber despues con cuanta cobertura se genero un entregable. Lo pregunto Monica el
2026-08-19.

Ahora cada ejecucion —por terminal o por la GUI— anota su renglon aqui y se regenera un solo
Excel consolidado junto a los entregables.

Diseño
------
- **Almacen append-only** (`Historico_Cruce_CPA.parquet`): nunca se reescribe una fila. Si el
  mismo proveedor se vuelve a ejecutar, se agrega otro renglon con su fecha; asi se puede ver
  como mejoro la cobertura conforme entraron mas descargas de CPA. Mismo criterio que
  `Historico_Diferencias.parquet`.
- **Excel derivado** (`Reporte_Cruce_CPA.xlsx`): se regenera completo desde el almacen. La
  hoja principal trae la ejecucion MAS RECIENTE de cada proveedor, que es lo que se consulta;
  el historico completo queda en la segunda hoja.
- **Nunca lanza.** Es un reporte accesorio: el entregable del proveedor ya esta escrito y es
  lo que importa. Cualquier fallo aqui se avisa y se sigue.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

import config

NOMBRE_REPORTE = "Reporte_Cruce_CPA.xlsx"
NOMBRE_HISTORICO = "Historico_Cruce_CPA.parquet"

COLUMNAS = [
    "Fecha",
    "Proveedor",
    "Nombre",
    "RFC",
    "Periodo",
    "Renglones de compras",
    "Con CFDI encontrado",
    "% de cruce",
    "por serie + folio",
    "por folio (respaldo)",
    "Sin CFDI",
    "Celdas vacias rellenadas",
    "CFDI en conflicto (no usados)",
    "Difieren en IVA",
    "Difieren en IEPS",
    "Origen",
]

# Columnas que se muestran en la hoja principal. Las dos de "Difieren en..." se dejan fuera
# a proposito: son un control tecnico interno (comparan el impuesto copiado del CFDI contra
# despejarlo del total de la factura) y difieren SIEMPRE que la factura mezcla tasas, asi que
# leidas sin contexto parecen una alarma enorme. Siguen en la hoja de historico.
COLUMNAS_VISIBLES = [c for c in COLUMNAS if not c.startswith("Difieren")]


def fila_desde_resultado(
    resultado,
    *,
    proveedor: str,
    nombre: str = "",
    rfc: str = "",
    periodo: str = "",
    origen: str = "ejecucion",
) -> dict:
    """Convierte un `ResultadoCruce` en el renglon que se guarda."""
    return {
        "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Proveedor": str(proveedor),
        "Nombre": nombre,
        "RFC": rfc,
        "Periodo": periodo,
        "Renglones de compras": int(resultado.renglones),
        "Con CFDI encontrado": int(resultado.cruzados),
        "% de cruce": round(float(resultado.tasa_cruce), 4),
        "por serie + folio": int(resultado.cruzados_por_serie),
        "por folio (respaldo)": int(resultado.cruzados_por_folio),
        "Sin CFDI": int(resultado.renglones - resultado.cruzados),
        "Celdas vacias rellenadas": int(resultado.celdas_llenadas),
        "CFDI en conflicto (no usados)": int(resultado.descartados_ambiguos),
        "Difieren en IVA": int(resultado.discrepancias_iva),
        "Difieren en IEPS": int(resultado.discrepancias_ieps),
        "Origen": origen,
    }


def fila_desde_varios(
    resultados: list,
    *,
    proveedor: str,
    nombre: str = "",
    rfc: str = "",
    periodo: str = "",
    origen: str = "ejecucion",
) -> dict | None:
    """Suma los `ResultadoCruce` de un proveedor procesado por partes (los gigantes).

    El camino por trimestres cruza cada intervalo por separado, así que hay un resultado por
    trimestre. Los conteos se suman; el porcentaje se recalcula sobre el total, porque
    promediar los porcentajes de cada trimestre daría un número distinto y equivocado
    (cada trimestre pesa diferente).
    """
    if not resultados:
        return None

    renglones = sum(int(r.renglones) for r in resultados)
    cruzados = sum(int(r.cruzados) for r in resultados)
    return {
        "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Proveedor": str(proveedor),
        "Nombre": nombre,
        "RFC": rfc,
        "Periodo": periodo,
        "Renglones de compras": renglones,
        "Con CFDI encontrado": cruzados,
        "% de cruce": round(cruzados / renglones, 4) if renglones else 0.0,
        "por serie + folio": sum(int(r.cruzados_por_serie) for r in resultados),
        "por folio (respaldo)": sum(int(r.cruzados_por_folio) for r in resultados),
        "Sin CFDI": renglones - cruzados,
        "Celdas vacias rellenadas": sum(int(r.celdas_llenadas) for r in resultados),
        "CFDI en conflicto (no usados)": sum(int(r.descartados_ambiguos) for r in resultados),
        "Difieren en IVA": sum(int(r.discrepancias_iva) for r in resultados),
        "Difieren en IEPS": sum(int(r.discrepancias_ieps) for r in resultados),
        "Origen": origen,
    }


def registrar(
    filas: list[dict] | dict,
    raiz: Path | str | None = None,
    *,
    log: Callable[[str], None] = print,
) -> Path | None:
    """Anota las filas en el historico y regenera el Excel. NUNCA lanza."""
    try:
        return _registrar(filas, raiz)
    except Exception as exc:  # noqa: BLE001 — el entregable ya esta escrito
        log(f"[Metricas cruce] no se pudo actualizar el reporte ({exc})")
        return None


def _registrar(filas: list[dict] | dict, raiz: Path | str | None) -> Path | None:
    if isinstance(filas, dict):
        filas = [filas]
    if not filas:
        return None

    raiz = Path(raiz) if raiz else config.ENTREGABLES_DIR
    raiz.mkdir(parents=True, exist_ok=True)
    ruta_historico = raiz / NOMBRE_HISTORICO

    nuevas = pd.DataFrame(filas).reindex(columns=COLUMNAS)
    if ruta_historico.exists():
        previo = pd.read_parquet(ruta_historico)
        historico = pd.concat([previo, nuevas], ignore_index=True)
    else:
        historico = nuevas
    historico.to_parquet(ruta_historico, index=False)

    return escribir_excel(historico, raiz / NOMBRE_REPORTE)


def escribir_excel(historico: pd.DataFrame, destino: Path) -> Path:
    """Hoja 1: la ejecucion mas reciente de cada proveedor. Hoja 2: todo el historico."""
    historico = historico.copy()
    historico["Proveedor"] = historico["Proveedor"].astype(str)

    # La ultima ejecucion de cada proveedor: se ordena por fecha y se toma la de abajo.
    ultimo = (
        historico.sort_values("Fecha")
        .drop_duplicates(subset=["Proveedor"], keep="last")
        .sort_values("Proveedor", key=lambda s: pd.to_numeric(s, errors="coerce"))
    )

    # Se escribe a un temporal y se mueve encima: si el Excel esta abierto, el bueno queda
    # intacto en vez de terminar a medias.
    temporal = destino.with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(temporal, engine="xlsxwriter") as writer:
        ultimo[COLUMNAS_VISIBLES].to_excel(writer, sheet_name="Cobertura por proveedor", index=False)
        historico.sort_values(["Proveedor", "Fecha"]).to_excel(
            writer, sheet_name="Historico de ejecuciones", index=False
        )
        libro = writer.book
        porcentaje = libro.add_format({"num_format": "0.0%"})
        millar = libro.add_format({"num_format": "#,##0"})
        encabezado = libro.add_format({"bold": True, "bg_color": "#00FD28", "border": 1})

        for hoja, tabla in (("Cobertura por proveedor", ultimo[COLUMNAS_VISIBLES]),
                            ("Historico de ejecuciones", historico)):
            ws = writer.sheets[hoja]
            for i, nombre in enumerate(tabla.columns):
                ws.write(0, i, nombre, encabezado)
                if nombre == "% de cruce":
                    ws.set_column(i, i, 12, porcentaje)
                elif tabla[nombre].dtype.kind in "if":
                    ws.set_column(i, i, 18, millar)
                else:
                    ws.set_column(i, i, 34 if nombre == "Nombre" else 20)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(tabla), max(0, len(tabla.columns) - 1))

    temporal.replace(destino)
    return destino
