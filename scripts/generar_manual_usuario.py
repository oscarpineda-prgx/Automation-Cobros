"""Genera el manual de uso de la aplicacion, en Word, para el auditor.

Es el documento que acompaña al ejecutable. Esta escrito para alguien que **no sabe nada
del proyecto ni de programacion**: no menciona Python, ni rutas del repositorio, ni
subcomandos. Si una instruccion no se puede seguir con el raton, no va aqui.

Deja huecos marcados para pegar capturas de pantalla: cada uno es un recuadro con el texto
de que se espera ver ahi. Se sustituyen en Word (clic dentro del recuadro -> Insertar ->
Imagen) sin tocar el resto del documento.

Uso:
    .venv/Scripts/python.exe scripts/generar_manual_usuario.py
Deja `Manual_Automation_Costos.docx` en docs/manuales/.

⚠ OJO: SOBRESCRIBE el archivo. El manual que hay en la raiz ya lleva las capturas de
pantalla pegadas a mano, y regenerarlo LAS BORRA. Este script se mantiene al dia para que
el contenido no se pierda, pero para cambios puntuales conviene editar el .docx y no
volver a correrlo. Si hay que regenerarlo, hay que volver a pegar las imagenes.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "manuales" / "Manual_Automation_Costos.docx"

MORADO = RGBColor(0x61, 0x1E, 0xEC)   # el acento PRGX
AZUL = RGBColor(0x1F, 0x4E, 0x78)
GRIS = RGBColor(0x80, 0x80, 0x80)
ROJO = RGBColor(0xC0, 0x00, 0x00)
VERDE = RGBColor(0x00, 0x70, 0x30)


# ---------------------------------------------------------------------------------------
# Piezas de formato
# ---------------------------------------------------------------------------------------

def _titulo(doc, texto, color=MORADO, size=15):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(texto)
    r.bold = True
    r.font.size = Pt(size)
    r.font.color.rgb = color
    return p


def _subtitulo(doc, texto):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(texto)
    r.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = AZUL
    return p


def _parrafo(doc, texto, size=10, italic=False, color=None, bold=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(texto)
    r.font.size = Pt(size)
    r.italic = italic
    r.bold = bold
    if color is not None:
        r.font.color.rgb = color
    return p


def _vinneta(doc, texto, size=10):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(texto)
    r.font.size = Pt(size)
    return p


def _paso(doc, numero, texto, detalle=""):
    """Un paso numerado, con el numero destacado. Es la unidad del manual."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    n = p.add_run(f"{numero}. ")
    n.bold = True
    n.font.size = Pt(11)
    n.font.color.rgb = MORADO
    r = p.add_run(texto)
    r.bold = True
    r.font.size = Pt(11)
    if detalle:
        d = doc.add_paragraph()
        d.paragraph_format.left_indent = Pt(18)
        d.paragraph_format.space_after = Pt(4)
        rd = d.add_run(detalle)
        rd.font.size = Pt(10)
    return p


def _aviso(doc, texto, color=ROJO, etiqueta="Importante"):
    """Recuadro de una celda para llamar la atencion sobre algo que suele salir mal."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    celda = t.rows[0].cells[0]
    celda.text = ""
    p = celda.paragraphs[0]
    e = p.add_run(f"{etiqueta}: ")
    e.bold = True
    e.font.size = Pt(10)
    e.font.color.rgb = color
    r = p.add_run(texto)
    r.font.size = Pt(10)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def _hueco_imagen(doc, descripcion, alto_lineas=8):
    """Marco vacio donde el usuario pega una captura.

    Es una tabla de una celda con varios parrafos vacios dentro: en Word se hace clic
    dentro y se inserta la imagen, y el marco se ajusta solo. Se deja escrito QUE deberia
    verse en esa captura, para que no haya dudas al armarlo.
    """
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    celda = t.rows[0].cells[0]
    celda.text = ""

    p = celda.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"[ Captura: {descripcion} ]")
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = GRIS

    for _ in range(alto_lineas):
        vacio = celda.add_paragraph()
        vacio.alignment = WD_ALIGN_PARAGRAPH.CENTER
        vacio.paragraph_format.space_after = Pt(0)

    pie = doc.add_paragraph()
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pie.paragraph_format.space_after = Pt(10)
    rp = pie.add_run("Haz clic dentro del marco y usa Insertar › Imagen para colocar la captura.")
    rp.italic = True
    rp.font.size = Pt(8)
    rp.font.color.rgb = GRIS
    return t


def _tabla(doc, encabezados, filas, anchos_pt=None):
    t = doc.add_table(rows=1, cols=len(encabezados))
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(encabezados):
        t.rows[0].cells[i].text = ""
        run = t.rows[0].cells[i].paragraphs[0].add_run(h)
        run.bold = True
        run.font.size = Pt(9)
    for fila in filas:
        cells = t.add_row().cells
        for i, valor in enumerate(fila):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(str(valor))
            run.font.size = Pt(9)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


# ---------------------------------------------------------------------------------------
# El documento
# ---------------------------------------------------------------------------------------

def main() -> None:
    doc = Document()
    for seccion in doc.sections:
        seccion.left_margin = seccion.right_margin = Pt(56)

    # -- Portada -------------------------------------------------------------------
    h = doc.add_heading("Manual de uso", level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("Automation Costos")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rs = sub.runs[0]
    rs.bold = True
    rs.font.size = Pt(16)
    rs.font.color.rgb = MORADO
    pie = doc.add_paragraph("PRGX · Auditoría de Costos Soriana")
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pie.runs[0].font.size = Pt(11)
    pie.runs[0].font.color.rgb = GRIS
    doc.add_paragraph()

    _parrafo(
        doc,
        "Esta aplicación genera los archivos de la auditoría de costos: el archivo de "
        "Compras y la Validación de Condiciones que se entrega. También descarga del portal "
        "CPA Vision las facturas electrónicas que faltan, para completar la información.",
        size=11,
    )
    _parrafo(
        doc,
        "No necesitas saber programar ni instalar nada: todo se hace con el ratón.",
        size=11, italic=True,
    )

    _hueco_imagen(doc, "la ventana principal recién abierta", alto_lineas=12)

    doc.add_page_break()

    # -- 1. Abrir --------------------------------------------------------------------
    _titulo(doc, "1. Abrir la aplicación")

    _paso(doc, 1, "Descomprime la carpeta que te entregaron.",
          "Haz clic derecho en el archivo .zip y elige «Extraer todo». Queda una carpeta "
          "llamada AutomationCostos.")
    _paso(doc, 2, "Entra en esa carpeta y haz doble clic en AutomationCostos.",
          "Es el archivo con el icono de PRGX. Tarda unos segundos en abrir la primera vez.")

    _aviso(
        doc,
        "no saques el programa de su carpeta ni lo copies solo al escritorio. Necesita la "
        "carpeta «_internal» que está junto a él; sin ella no arranca. Si quieres un acceso "
        "rápido, haz clic derecho sobre el programa y elige «Crear acceso directo».",
    )

    _hueco_imagen(doc, "el contenido de la carpeta: _internal y AutomationCostos", alto_lineas=6)

    # -- 2. La pantalla --------------------------------------------------------------
    _titulo(doc, "2. Cómo está organizada la pantalla")

    _parrafo(doc, "Arriba hay tres pestañas. Se elige según cuántos proveedores vas a trabajar:")
    _tabla(
        doc,
        ["Pestaña", "Para qué sirve"],
        [
            ["Un proveedor", "El trabajo del día: un proveedor, paso a paso."],
            ["Por lotes", "Varios proveedores seguidos, sin estar pendiente."],
            ["Ajustes", "Tu usuario del portal y las carpetas. Se configura una vez."],
        ],
    )
    _parrafo(
        doc,
        "Abajo del todo está la BITÁCORA DE EJECUCIÓN: ahí el programa va contando lo que "
        "hace. Cuando algo falle, ese texto es lo primero que hay que mirar.",
    )

    _hueco_imagen(doc, "las tres pestañas y la bitácora de la parte inferior", alto_lineas=10)

    # -- 3. Primera vez --------------------------------------------------------------
    _titulo(doc, "3. La primera vez: configurar Ajustes")

    _parrafo(doc, "Esto se hace una sola vez. Entra en la pestaña Ajustes.")

    _paso(doc, 1, "Escribe tu usuario y contraseña de CPA Vision.",
          "Son los mismos con los que entras al portal desde el navegador.")
    _paso(doc, 2, "Comprueba que la contraseña quedó bien escrita.",
          "Mantén pulsado el símbolo ◉ que está a la derecha del campo: mientras lo sostengas "
          "verás la contraseña, y al soltar se vuelve a ocultar.")
    _paso(doc, 3, "Revisa la carpeta de Salida (entregables).",
          "Es donde se guardarán los archivos que generes. Si no sabes cuál poner, pregunta "
          "antes de cambiarla: normalmente ya viene puesta la correcta.")
    _paso(doc, 4, "Pulsa «Probar conexión».",
          "Si dice «Conexión correcta», ya puedes trabajar.")

    _hueco_imagen(doc, "la pestaña Ajustes con las credenciales y las carpetas", alto_lineas=10)

    _aviso(
        doc,
        "la casilla «Descargar sin ventana» hace que el portal trabaje por detrás, sin abrir "
        "el navegador. Déjala marcada: es más rápida y no te roba el teclado mientras "
        "trabajas en otra cosa.",
        color=VERDE, etiqueta="Consejo",
    )

    doc.add_page_break()

    # -- 4. Un proveedor de principio a fin ------------------------------------------
    _titulo(doc, "4. Trabajar un proveedor de principio a fin")

    _parrafo(
        doc,
        "Es la forma más rápida y la que usarás casi siempre. Entra en la pestaña "
        "«Un proveedor».",
    )

    _paso(doc, 1, "Escribe el número de proveedor y el periodo.",
          "Por ejemplo: Proveedor 741, Desde 2020-01-01, Hasta 2025-12-31. Las fechas se "
          "escriben con guiones, en ese orden: año-mes-día.")
    _paso(doc, 2, "Pulsa el botón grande «GENERAR TODO».",
          "El programa hace todo solo: busca las compras, descarga del portal lo que falte, "
          "cruza las facturas y genera los archivos finales.")
    _paso(doc, 3, "Espera.",
          "En la barra de abajo verás el reloj avanzando y lo que está haciendo. Un proveedor "
          "pequeño tarda unos minutos; uno muy grande puede tardar horas. Puedes seguir "
          "usando el equipo mientras tanto.")
    _paso(doc, 4, "Cuando termine, abre la carpeta de salida.",
          "Ahí tendrás una carpeta con el nombre del proveedor y, dentro, sus archivos.")

    _hueco_imagen(doc, "la pestaña «Un proveedor» con el botón GENERAR TODO", alto_lineas=11)

    _aviso(
        doc,
        "si necesitas parar, usa el botón «Detener» de la barra inferior. No se corta al "
        "instante: el programa termina el paso que está haciendo para no dejar un archivo de "
        "Excel a medio escribir. Espera a que se apague solo.",
    )

    # -- 5. Los cinco pasos ----------------------------------------------------------
    _titulo(doc, "5. Los cinco pasos, uno por uno")

    _parrafo(
        doc,
        "Debajo del botón grande hay una lista numerada. Sirve cuando no quieres hacerlo "
        "todo de golpe: por ejemplo, cuando necesitas revisar el archivo de Compras en Excel "
        "antes de generar la Validación.",
    )
    _parrafo(
        doc,
        "Cada renglón te dice en qué punto vas: ✓ ya se hizo · ▶ es el siguiente · "
        "· todavía no toca. Ningún paso te obliga a hacer el anterior.",
    )

    _tabla(
        doc,
        ["Paso", "Qué hace"],
        [
            ["1. Generar Compras preliminar", "Saca de la base el archivo de compras del proveedor."],
            ["2. Descargar de CPA Vision", "Baja del portal las facturas electrónicas del proveedor."],
            ["3. Rellenar EDI con los CFDI",
             "Completa el archivo con los datos de esas facturas. Deja un archivo terminado "
             "en _EDI: ese es el que se revisa y se corrige."],
            ["4. Recalcular el Compras editado", "Vuelve a hacer las cuentas tomando tus correcciones."],
            ["5. Generar Validación de Condiciones", "Produce el archivo que se entrega."],
        ],
    )

    _hueco_imagen(doc, "la lista de los cinco pasos numerados", alto_lineas=9)

    doc.add_page_break()

    # -- 6. Editar y regenerar -------------------------------------------------------
    _titulo(doc, "6. Corregir el archivo de Compras y volver a generar")

    _parrafo(
        doc,
        "Este es el caso más habitual del día a día: revisas el archivo de Compras, corriges "
        "lo que haga falta y vuelves a sacar la Validación con tus correcciones.",
    )

    _paso(doc, 1, "Abre en Excel el archivo del proveedor.",
          "Si ya hiciste el cruce con CPA Vision (paso 3), abre el que termina en _EDI: es el "
          "que trae los datos de las facturas.")
    _paso(doc, 2, "Corrige solo las tres columnas de color piel.",
          "Los títulos están en la fila 7 y los datos empiezan en la 8. No muevas ni renombres "
          "columnas ni hojas.")
    # El codigo de color es la regla acordada con Monica el 2026-09-11 (LOGICA_NEGOCIO 3.0):
    # el auditor corrige el RESULTADO auditado, nunca el dato de origen.
    _tabla(
        doc,
        ["Color del título", "Qué contiene", "¿Lo corriges?"],
        [
            ["Verde oscuro", "Los datos de la factura del proveedor",
             "No. Llegan del sistema y de CPA Vision"],
            ["Piel", "cto_aud · iva_aud · ieps_aud", "Sí. Es lo único que corriges"],
            ["Verde claro", "El resultado del cálculo",
             "No. Se recalcula solo con lo que corrijas"],
        ],
    )
    _parrafo(
        doc,
        "El color te dice qué hacer con cada columna. Las de color piel son el costo, el IVA y "
        "el IEPS de auditoría: ahí escribes lo que debió ser. Todo lo verde claro —el importe, "
        "lo que debió pagarse y las diferencias— se vuelve a calcular solo a partir de eso, así "
        "que cambiarlo a mano no sirve de nada.",
    )
    _paso(doc, 3, "Cierra el archivo de Excel.",
          "Si lo dejas abierto, el programa no puede leerlo.")
    _paso(doc, 4, "Vuelve al programa y selecciona el archivo en «Compras editado».")
    _paso(doc, 5, "Pulsa el paso 4, «Recalcular el Compras editado».")
    _paso(doc, 6, "Pulsa el paso 5, «Generar Validación de Condiciones».",
          "Si ya existía una Validación de ese proveedor, te preguntará si quieres "
          "reemplazarla. Al aceptar, el reporte general de diferencias se actualiza solo con "
          "tus cifras nuevas.")

    _hueco_imagen(doc, "el selector «Compras editado» y los pasos 4 y 5", alto_lineas=9)

    _aviso(
        doc,
        "la columna «concepto» cambia el resultado del entregable. Si la dejas vacía, entran "
        "todas las notas con diferencia. En cuanto escribes una clasificación en cualquier "
        "renglón, el entregable pasa a llevar SOLO las notas que tengan al menos un renglón "
        "marcado como «dif costos». Es así a propósito, pero conviene saberlo para no pensar "
        "que el archivo salió vacío por error.",
    )

    # -- 7. Varios proveedores -------------------------------------------------------
    _titulo(doc, "7. Trabajar varios proveedores seguidos")

    _parrafo(
        doc,
        "La pestaña «Por lotes» sirve para dejar una tanda trabajando sola, por ejemplo al "
        "terminar la jornada.",
    )

    _paso(doc, 1, "Escribe el número de proveedor y el periodo, y pulsa «+ Agregar».",
          "El programa busca el nombre del proveedor y lo muestra en la lista. Si el nombre "
          "no es el que esperabas, te equivocaste de número: quítalo y vuelve a intentarlo.")
    _paso(doc, 2, "Elige en «Qué hacer» lo que quieres para ese proveedor.")

    _tabla(
        doc,
        ["Opción", "Qué hace"],
        [
            ["Solo descargar", "Baja las facturas del portal. No genera ningún Excel."],
            ["Descargar y generar", "Baja las facturas y además produce los archivos finales."],
            ["Generar con lo ya descargado", "No baja nada; usa lo que ya se descargó antes."],
            ["Generar sin cruce de CPA", "Genera los archivos sin usar facturas del portal."],
        ],
    )

    _paso(doc, 3, "Repite para los demás proveedores.")
    _paso(doc, 4, "Pulsa «EJECUTAR LA COLA».",
          "Primero hace todas las descargas y después todos los archivos. Cada renglón va "
          "cambiando de estado: en espera, en curso, listo.")

    _hueco_imagen(doc, "la pestaña «Por lotes» con varios proveedores en la lista", alto_lineas=11)

    _aviso(
        doc,
        "la lista se guarda sola. Puedes cerrar el programa y al abrirlo seguirá ahí.",
        color=VERDE, etiqueta="Consejo",
    )

    doc.add_page_break()

    # -- 8. Qué archivos salen -------------------------------------------------------
    _titulo(doc, "8. Qué archivos produce y dónde quedan")

    _parrafo(
        doc,
        "Dentro de la carpeta de salida se crea una carpeta por proveedor, con su número y "
        "su nombre. Todo lo de ese proveedor queda ahí, lo hagas de un clic o paso a paso:",
    )
    _tabla(
        doc,
        ["Archivo", "Qué es"],
        [
            ["Validacion_….xlsx", "El entregable. Es el archivo que se envía."],
            ["Compras_….xlsx", "El detalle completo, para consultar y revisar."],
            ["cpa vision soportes", "Las descargas del portal que respaldan el resultado."],
        ],
    )
    _parrafo(
        doc,
        "Un proveedor muy grande puede tener varios archivos de Compras (uno por año), pero "
        "la Validación siempre es un solo archivo.",
    )

    _hueco_imagen(doc, "la carpeta de un proveedor con sus archivos", alto_lineas=7)

    # -- 9. Si algo sale mal ---------------------------------------------------------
    _titulo(doc, "9. Si algo sale mal")

    _parrafo(
        doc,
        "Lo primero, siempre: lee la línea roja de la bitácora, abajo. Suele decir "
        "exactamente qué pasó. Estos son los casos más frecuentes:",
    )

    _tabla(
        doc,
        ["Lo que ves", "Qué significa y qué hacer"],
        [
            ["Usuario o contraseña incorrectos",
             "El portal no aceptó tus datos. Revísalos en Ajustes con el ojo ◉. Si están "
             "bien, la contraseña pudo haber cambiado: pregunta antes de seguir "
             "intentando, porque varios intentos fallidos pueden bloquear la cuenta."],
            ["Sin valores en el portal",
             "No es un error. Significa que ese proveedor no tiene facturas en ese periodo. "
             "El programa pasa al siguiente."],
            ["No se pudo conectar a la base",
             "Problema de red o de permisos. Prueba «Probar conexión» en Ajustes y avisa a "
             "soporte si sigue fallando."],
            ["El proveedor no tiene compras en el periodo",
             "Revisa el número de proveedor y las fechas."],
        ],
    )

    _parrafo(
        doc,
        "Si tienes que reportar un problema, dentro de la carpeta del programa hay una "
        "carpeta «logs» con el detalle y, cuando el fallo es del portal, una imagen de lo que "
        "vio el programa. Adjuntar eso ayuda mucho a resolverlo.",
    )

    _hueco_imagen(doc, "un mensaje de error en la bitácora", alto_lineas=6)

    # -- Cierre ----------------------------------------------------------------------
    doc.add_paragraph()
    cierre = doc.add_paragraph()
    cierre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rc = cierre.add_run("¿Dudas? Contacta a Óscar Pineda.")
    rc.font.size = Pt(10)
    rc.font.color.rgb = GRIS

    doc.save(SALIDA)
    print(f"Manual generado: {SALIDA}")


if __name__ == "__main__":
    main()
