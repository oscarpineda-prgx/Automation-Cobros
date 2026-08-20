"""Une los Compras trimestrales de PEPSICO (76034) en UN solo libro, con menos columnas.

Encargo puntual de Óscar (2026-08-14), **de una sola vez**: no forma parte del pipeline.
No recalcula nada — copia tal cual los valores que ya están en los archivos.

Por qué así
-----------
- **Lectura con calamine**: los 24 archivos suman 5.7 GB. Con openpyxl serían ~2.6 h; con
  calamine (lector en Rust) son ~20 min. Se lee un archivo a la vez y se suelta.
- **Escritura en streaming** (`constant_memory`): los ~10 M de renglones nunca están todos
  en memoria.
- **Varias hojas**: Excel topa en 1,048,576 renglones por hoja, así que el consolidado se
  continúa en "Compras (2)", "Compras (3)"... Es un solo archivo, como se pidió.

Uso:
    python scripts/consolidar_pepsico.py
    python scripts/consolidar_pepsico.py --sin-edi   # quita las columnas EDI salvo totfactura
"""

from __future__ import annotations

import argparse
import gc
import sys
import time
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

CARPETA = (
    config.ENTREGABLES_DIR / "76034_COMERCIALIZADORA PEPSICO MEXICO S D E RL DE CV"
)
SALIDA = CARPETA / "Compras_Consolidado_76034_PEPSICO.xlsx"

# Las 26 columnas pedidas, en el orden pedido.
COLUMNAS = [
    "concaten", "invnbr", "codbarra", "itmdesc", "poitmcspck", "poitmsz", "fact_empaq",
    "poqty", "rcvqty", "invqty", "can_rec", "poitmgrscst", "poitmnetcst", "ctouni", "imp",
    "compra_bruta", "compra_bruta mas impuestos", "compra_neta", "compra neta mas impuestos",
    "canfac_edi", "factem_edi", "impart_edi", "prieps_edi", "imieps_edi", "poriva_edi",
    "totfactura",
]
# Columnas EDI prescindibles si el archivo pesa de más. `totfactura` se conserva siempre.
EDI_PRESCINDIBLES = ["canfac_edi", "factem_edi", "impart_edi", "prieps_edi", "imieps_edi", "poriva_edi"]

FILA_ENCABEZADO = 6  # 0-indexed: los datos del Compras empiezan en la fila 8 de Excel
TOPE_HOJA = 1_048_576

MONEDA = {
    "poitmgrscst", "poitmnetcst", "ctouni", "imp", "compra_bruta",
    "compra_bruta mas impuestos", "compra_neta", "compra neta mas impuestos",
    "impart_edi", "imieps_edi", "totfactura",
}
PORCENTAJE = {"prieps_edi", "poriva_edi"}
ANCHOS = {"concaten": 18, "invnbr": 16, "codbarra": 16, "itmdesc": 32}


class LibroPorHojas:
    """Escribe renglones abriendo una hoja nueva al llegar al tope de Excel."""

    def __init__(self, wb, columnas: list[str], titulo: str) -> None:
        self.wb = wb
        self.columnas = columnas
        self.titulo = titulo
        self.fmts = {
            "titulo": wb.add_format({"bold": True, "font_size": 14, "align": "center"}),
            "hdr": wb.add_format({"bold": True, "bg_color": "#00FD28", "border": 1,
                                  "align": "center", "valign": "vcenter", "text_wrap": True}),
            "money": wb.add_format({"num_format": "#,##0.00"}),
            "pct": wb.add_format({"num_format": "0.00%"}),
        }
        self.parte = 0
        self.fila = 0
        self.total = 0
        self.ws = None
        self._nueva_hoja()

    def _nueva_hoja(self) -> None:
        nombre = "Compras" if self.parte == 0 else f"Compras ({self.parte + 1})"
        ws = self.wb.add_worksheet(nombre)
        ws.hide_gridlines(2)
        logo = config.RESOURCE_DIR / "templates" / "Soriana-Logo.png"
        if logo.exists():
            ws.insert_image(1, 0, str(logo), {"x_scale": 0.5, "y_scale": 0.5})
        ws.merge_range(1, 3, 1, 11, "Tiendas Soriana, S.A. de C.V.", self.fmts["titulo"])
        ws.merge_range(2, 3, 2, 11, "76034 - COMERCIALIZADORA PEPSICO MEXICO S DE RL DE CV",
                       self.fmts["titulo"])
        ws.merge_range(3, 3, 3, 11, self.titulo, self.fmts["titulo"])
        for i, col in enumerate(self.columnas):
            ws.write(FILA_ENCABEZADO, i, col, self.fmts["hdr"])
            fmt = self.fmts["money"] if col in MONEDA else self.fmts["pct"] if col in PORCENTAJE else None
            ws.set_column(i, i, ANCHOS.get(col, 14), fmt)
        ws.freeze_panes(FILA_ENCABEZADO + 1, 0)
        ws.autofilter(FILA_ENCABEZADO, 0, FILA_ENCABEZADO, len(self.columnas) - 1)
        self.ws = ws
        self.fila = FILA_ENCABEZADO + 1

    def escribir(self, df: pd.DataFrame) -> None:
        for renglon in df.itertuples(index=False, name=None):
            if self.fila >= TOPE_HOJA:
                self.parte += 1
                self._nueva_hoja()
            self.ws.write_row(self.fila, 0, [_limpiar(v) for v in renglon])
            self.fila += 1
            self.total += 1


def _limpiar(valor):
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%Y-%m-%d")
    if hasattr(valor, "isoformat"):
        return valor.isoformat()[:10]
    return valor


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sin-edi", action="store_true", help="Quita las columnas EDI salvo totfactura")
    p.add_argument("--por-anio", action="store_true", help="Un archivo por año en vez de uno solo")
    p.add_argument("--salida", default=str(SALIDA))
    args = p.parse_args()

    columnas = [c for c in COLUMNAS if not (args.sin_edi and c in EDI_PRESCINDIBLES)]
    archivos = sorted(CARPETA.glob("Compras_76034_*.xlsx"))
    if not archivos:
        raise SystemExit(f"No se encontraron Compras en {CARPETA}")

    # El año va en el nombre del trimestral ("..._2020-T1.xlsx"). Agrupar por ahí evita
    # leer el contenido para saber a qué archivo pertenece cada renglón.
    grupos: dict[str, list[Path]] = {}
    for ruta in archivos:
        anio = ruta.stem.rsplit("_", 1)[-1].split("-")[0] if args.por_anio else "TODO"
        grupos.setdefault(anio, []).append(ruta)

    print(f"Carpeta : {CARPETA}")
    print(f"Archivos: {len(archivos)}  ·  columnas: {len(columnas)}")
    print(f"Salida  : {'un archivo por año' if args.por_anio else Path(args.salida).name}\n", flush=True)

    import xlsxwriter

    inicio = time.time()
    total = 0
    n = 0
    for anio, rutas in grupos.items():
        salida = (
            CARPETA / f"Compras_Consolidado_76034_PEPSICO_{anio}.xlsx"
            if args.por_anio
            else Path(args.salida)
        )
        etiqueta = f"Compras consolidado {anio}" if args.por_anio else "Compras consolidado 2020 - 2026"
        wb = xlsxwriter.Workbook(str(salida), {"constant_memory": True, "use_zip64": True})
        try:
            libro = LibroPorHojas(wb, columnas, etiqueta)
            for ruta in rutas:
                n += 1
                t = time.time()
                df = pd.read_excel(
                    ruta, sheet_name=0, engine="calamine",
                    skiprows=FILA_ENCABEZADO, usecols=columnas, dtype_backend="numpy_nullable",
                )
                df = df.reindex(columns=columnas)
                libro.escribir(df)
                print(f"  [{n}/{len(archivos)}] {ruta.name[-16:]:16s} {len(df):>9,} renglones "
                      f"· {time.time() - t:5.0f}s", flush=True)
                del df
                gc.collect()
            wb.close()
        except BaseException:
            try:
                wb.close()
            except BaseException:
                pass
            salida.unlink(missing_ok=True)
            raise
        total += libro.total
        mb = salida.stat().st_size / 1048576
        print(f"     -> {salida.name}  {libro.total:,} renglones · "
              f"{libro.parte + 1} hoja(s) · {mb:,.0f} MB\n", flush=True)

    print(f"Listo: {total:,} renglones · {len(grupos)} archivo(s) · "
          f"{(time.time() - inicio) / 60:.0f} min")
    print(f"Carpeta: {CARPETA}")


if __name__ == "__main__":
    main()
