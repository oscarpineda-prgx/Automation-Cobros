"""Agrega una entrada fechada a docs/BITACORA.md.

La fecha y hora se toman siempre del reloj del sistema con datetime.now(),
nunca se escriben a mano.

Uso:
    python scripts/log_cambio.py --tipo codigo \
        --titulo "Conecta CPA Vision con el exportador" \
        --detalle "Se agrega cpa_parquet.leer_lote() para alimentar main.py" \
        --archivos automation_cobros/cpa_parquet.py main.py
"""

import argparse
from datetime import datetime
from pathlib import Path

BITACORA = Path(__file__).resolve().parent.parent / "docs" / "BITACORA.md"

TIPOS = {
    "codigo": "CÓDIGO",
    "decision": "DECISIÓN",
    "reunion": "REUNIÓN",
    "dato": "DATO",
    "bug": "BUG",
}


def construir_entrada(tipo, titulo, detalle, archivos):
    ahora = datetime.now()
    partes = [
        f"### {ahora.strftime('%Y-%m-%d %H:%M:%S')} — [{TIPOS[tipo]}] {titulo}",
        "",
        detalle,
    ]
    if archivos:
        partes += ["", "**Archivos:** " + ", ".join(f"`{a}`" for a in archivos)]
    partes += ["", "---", ""]
    return "\n".join(partes)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tipo", choices=TIPOS, required=True)
    p.add_argument("--titulo", required=True)
    p.add_argument("--detalle", required=True)
    p.add_argument("--archivos", nargs="*", default=[])
    args = p.parse_args()

    entrada = construir_entrada(args.tipo, args.titulo, args.detalle, args.archivos)

    contenido = BITACORA.read_text(encoding="utf-8")
    marca = "<!-- NUEVAS ENTRADAS ARRIBA -->\n"
    if marca not in contenido:
        raise SystemExit(f"No se encontró el marcador en {BITACORA}")

    # Las entradas más recientes quedan hasta arriba.
    contenido = contenido.replace(marca, marca + "\n" + entrada, 1)
    BITACORA.write_text(contenido, encoding="utf-8")

    print(f"Entrada agregada a {BITACORA}")


if __name__ == "__main__":
    main()
