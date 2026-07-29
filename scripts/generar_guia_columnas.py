"""Genera una guía en Word con el significado y el cálculo de cada columna clave.

Documento de referencia para el auditor: qué columna es llave, cuáles se copian del CFDI
(CPA Vision), cuáles se toman del propio Compras, cuáles se calculan, y cómo se calculan
las columnas de auditoría.

Uso:
    python scripts/generar_guia_columnas.py
Deja `Guia_Columnas_Compras.docx` en la raíz del proyecto.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

SALIDA = Path(__file__).resolve().parent.parent / "Guia_Columnas_Compras.docx"

VERDE = RGBColor(0x00, 0xB0, 0x50)
AMARILLO = RGBColor(0xBF, 0x90, 0x00)
NARANJA = RGBColor(0xC5, 0x50, 0x00)
AZUL = RGBColor(0x1F, 0x4E, 0x78)


def _titulo(doc, texto, color=AZUL, size=15):
    p = doc.add_paragraph()
    run = p.add_run(texto)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = color
    return p


def _tabla(doc, encabezados, filas):
    t = doc.add_table(rows=1, cols=len(encabezados))
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(encabezados):
        celda = t.rows[0].cells[i]
        celda.text = ""
        run = celda.paragraphs[0].add_run(h)
        run.bold = True
        run.font.size = Pt(9)
    for fila in filas:
        cells = t.add_row().cells
        for i, valor in enumerate(fila):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(valor))
            run.font.size = Pt(9)
    return t


def main() -> None:
    doc = Document()

    h = doc.add_heading("Guía de columnas — Compras / Cruce CPA Vision", level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("Automation Cobros · PRGX · Soriana Audit Suite")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()

    intro = doc.add_paragraph()
    intro.add_run(
        "Soriana pagó a cada proveedor según el costo de su sistema (SAP). El cruce trae lo "
        "que el proveedor realmente facturó en sus CFDI (facturas electrónicas, descargadas "
        "de CPA Vision) y llena las columnas EDI vacías del Compras. Luego el recálculo "
        "compara ambos costos y calcula la diferencia a reclamar."
    ).font.size = Pt(10)

    # Leyenda de origen
    _titulo(doc, "Origen de cada columna (código de color)", size=13)
    leyenda = doc.add_paragraph()
    for texto, color in (
        ("● Copiada del CFDI (CPA Vision)   ", AMARILLO),
        ("● Del propio Compras   ", VERDE),
        ("● Calculada   ", NARANJA),
    ):
        r = leyenda.add_run(texto)
        r.bold = True
        r.font.color.rgb = color
        r.font.size = Pt(10)
    doc.add_paragraph()

    # 1. Llave del cruce
    _titulo(doc, "1. Llave del cruce (cómo se emparejan Compras y CPA Vision)", size=13)
    _tabla(
        doc,
        ["Concepto", "En Compras", "En CPA Vision", "Nota"],
        [
            ["Número de factura", "invnbr", "Folio", "Se normaliza (quita serie/guiones): FN-21226 → 21226"],
            ["Código de barras", "codbarra", "noIdentificacion", "Se leen solo dígitos; NO usar la columna upc"],
            ["Proveedor", "vndnbr / cnpj (RFC)", "RFC (partición)", "El RFC se detecta solo desde el Compras"],
        ],
    )
    doc.add_paragraph()

    # 2. Copiadas del CFDI
    _titulo(doc, "2. Columnas que se COPIAN del CFDI (CPA Vision)", AMARILLO, size=13)
    doc.add_paragraph(
        "Se copian tal cual, solo en las celdas que venían vacías en Compras.",
    ).runs[0].font.size = Pt(9)
    _tabla(
        doc,
        ["Columna en Compras", "Viene de (CPA Vision)", "Qué es"],
        [
            ["canfac_edi", "Cantidad", "Cantidad facturada por el proveedor"],
            ["ctonto_edi", "Valor Unitario", "Costo unitario que el proveedor facturó"],
            ["poriva_edi", "TASA IVA", "Porcentaje de IVA (0.16, 0.08, 0...)"],
            ["impiva_edi", "IVA", "Importe de IVA del renglón (en pesos)"],
            ["prieps_edi", "TASA IEPS", "Porcentaje de IEPS"],
            ["imieps_edi", "IEPS", "Importe de IEPS del renglón (en pesos)"],
            ["totfactura", "Total", "Total de TODA la factura (se repite en cada renglón)"],
            ["uuid", "UUID", "Folio fiscal único del CFDI (SAT)"],
        ],
    )
    doc.add_paragraph()

    # 3. Del propio Compras
    _titulo(doc, "3. Columna que se toma del propio Compras", VERDE, size=13)
    _tabla(
        doc,
        ["Columna", "Se toma de", "Qué es"],
        [["factem_edi", "fact_empaq", "Factor de empaque: unidades por caja. Ya viene en Compras, NO del CFDI"]],
    )
    doc.add_paragraph()

    # 4. EDI calculadas
    _titulo(doc, "4. Columnas EDI que se CALCULAN", NARANJA, size=13)
    _tabla(
        doc,
        ["Columna", "Fórmula", "Ejemplo"],
        [
            ["ctobto_edi", "ctonto_edi × factem_edi", "11 × 20 = 220 (costo por caja)"],
            ["impart_edi", "ctobto_edi × canfac_edi × (1 + poriva_edi)", "220 × 320 × 1 = 70,400"],
        ],
    )
    doc.add_paragraph()

    # 5. Auditoría
    _titulo(doc, "5. Columnas de AUDITORÍA (el corazón del cálculo)", NARANJA, size=13)
    doc.add_paragraph(
        "Aquí se compara lo que Soriana pagó (ctouni, su sistema) contra lo que el proveedor "
        "facturó (ctonto_edi, del CFDI). Regla conservadora: solo corrige a la baja."
    ).runs[0].font.size = Pt(9)
    _tabla(
        doc,
        ["Columna", "Cálculo", "Significado"],
        [
            [
                "cto_aud",
                "Si hay EDI y ctonto_edi < ctouni → ctonto_edi; si no → ctouni",
                "Costo auditado: el menor entre lo pagado y lo facturado",
            ],
            [
                "iva_aud",
                "Si hay EDI → poriva_edi; si no → iva_t007s (tasa SAP)",
                "Tasa de IVA que se aplica al cálculo",
            ],
            [
                "ieps_aud",
                "Si hay EDI → prieps_edi; si no → ieps_t007s (tasa SAP)",
                "Tasa de IEPS que se aplica",
            ],
            [
                "imp_aud",
                "cto_aud × can_rec × (1 + iva_aud) × (1 + ieps_aud)",
                "Importe auditado con impuestos, por renglón",
            ],
            [
                "debio_pagar_ne",
                "Suma de imp_aud por FOLIO (nota de entrada)",
                "Lo que Soriana DEBIÓ pagar por esa nota de entrada",
            ],
            [
                "tot_pagado_ne",
                "Máximo de paynetamt por FOLIO",
                "Lo que Soriana pagó por esa nota (máx, no suma: viene repetido)",
            ],
            [
                "dif_det_ne",
                "tot_pagado_ne − debio_pagar_ne",
                "Diferencia a nivel nota de entrada. Positiva = se pagó de más = a cobrar",
            ],
            [
                "debio_pagar_inv",
                "Suma de imp_aud por FACTURA (vndnbr|strnbr|invnbr)",
                "Lo que se debió pagar, agrupado por factura",
            ],
            [
                "tot_pagado_inv",
                "Máximo de paynetamt por FACTURA",
                "Lo pagado a nivel factura",
            ],
            [
                "dif_det_inv",
                "tot_pagado_inv − debio_pagar_inv",
                "Diferencia a nivel factura",
            ],
        ],
    )
    doc.add_paragraph()

    nota = doc.add_paragraph()
    nota.add_run("Nota sobre los dos niveles: ").bold = True
    nota.add_run(
        "hay dos cortes del mismo dato. 'NE' agrupa por nota de entrada (folio = tienda + "
        "nota); 'inv' agrupa por factura. El 'pagado' usa MÁXIMO y no suma porque el monto "
        "viene repetido en cada renglón del grupo."
    ).font.size = Pt(9)

    doc.add_paragraph()
    pie = doc.add_paragraph()
    pie.add_run(
        "Generado automáticamente desde scripts/generar_guia_columnas.py. "
        "Fuente: docs/MAPEO_CRUCE_CPA_COMPRAS.md, docs/LOGICA_NEGOCIO.md y "
        "automation_cobros/calculations.py."
    )
    pie.runs[0].italic = True
    pie.runs[0].font.size = Pt(8)

    doc.save(SALIDA)
    print(f"Guía generada: {SALIDA}")


if __name__ == "__main__":
    main()
