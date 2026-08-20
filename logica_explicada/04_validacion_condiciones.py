"""
===============================================================================
PASO 4 de 4 — LA VALIDACION DE CONDICIONES: el entregable
===============================================================================

QUE RESUELVE ESTE PASO
----------------------
Los pasos 1 a 3 dejaron, para cada renglon de compra, cuanto se debio pagar y cuanta
diferencia hay. Este paso decide QUE SE RECLAMA y lo presenta en el archivo que se le
entrega al cliente.

No todo lo que tiene diferencia se reclama: hay un filtro. Entender ese filtro es lo mas
importante de este archivo.

Modulo real equivalente: automation_costos/validation_exporter.py
"""

import pandas as pd


# =============================================================================
# 1. LAS CUATRO HOJAS DEL ENTREGABLE
# =============================================================================
#
#   RESUMEN         una sola cifra: el total a reclamar al proveedor
#   CONSOLIDADO     una fila por NOTA DE ENTRADA con diferencia  <- lo que se reclama
#   AJUSTES         las devoluciones del paso 3 (solo si las hay)
#   DETALLE PAGOS   una fila por ARTICULO de esas notas          <- el sustento
#
# La logica de los dos niveles (nota y articulo) es deliberada: el auditor negocia por
# nota de entrada, pero tiene que poder demostrar articulo por articulo de donde sale.


# =============================================================================
# 2. EL FILTRO: que notas de entrada entran
# =============================================================================
#
# Hay DOS caminos posibles, y el sistema elige automaticamente segun los datos que traiga.

UMBRAL_DIFERENCIA = 1.00   # un peso


def hay_clasificacion_del_auditor(compras):
    """¿Los datos vienen ya clasificados por un auditor?

    Existe una columna "concepto" donde el auditor (o un proceso previo) marca cada
    renglon como "dif costos", "sin diferencia", "sobrepago" o "faltante".
    Si viene poblada, esa clasificacion MANDA sobre el calculo automatico.
    """
    if "concepto" not in compras.columns:
        return False
    conceptos = compras["concepto"].fillna("").astype(str).str.lower().str.strip()
    con_valor = conceptos[conceptos.ne("") & conceptos.ne("nan")]
    return con_valor.isin({"dif costos", "sin diferencia", "sobrepago", "faltante"}).any()


def filtrar_notas_que_se_reclaman(compras):
    """Devuelve solo los renglones cuya nota de entrada entra al entregable."""

    # --- CAMINO A: hay clasificacion del auditor ----------------------------------------
    # Entra la nota que tenga AL MENOS UN renglon marcado como "dif costos".
    # Basta con uno: si un solo articulo de la nota tiene diferencia de costos, la nota
    # completa entra (y su detalle se muestra entero, para que se vea el contexto).
    if hay_clasificacion_del_auditor(compras):
        es_diferencia_de_costos = (
            compras["concepto"].fillna("").astype(str).str.lower().str.strip() == "dif costos"
        )
        notas_con_diferencia = compras.loc[es_diferencia_de_costos, "folio"].unique()
        return compras[compras["folio"].isin(notas_con_diferencia)]

    # --- CAMINO B: no hay clasificacion -> se usa el calculo -----------------------------
    # Entra la nota cuya diferencia supere el umbral.
    diferencia = pd.to_numeric(compras["diferencia_nota"], errors="coerce").fillna(0)
    return compras[diferencia > UMBRAL_DIFERENCIA]


# NOTA IMPORTANTE SOBRE EL UMBRAL (pendiente de decidir con el negocio):
#
# Un peso es un umbral muy bajo para proveedores grandes. En Empacadora Celaya produjo
# 26,326 notas con una mediana de diferencia de $6.86 y un primer cuartil de $2.48: la
# enorme mayoria son centavos de redondeo, no cobros indebidos reales.
#
# Se dejo en 1 peso a proposito, para no descartar nada por cuenta propia, pero conviene
# revisarlo. Si ustedes lo replican, hagan el umbral CONFIGURABLE, no fijo.


# --- Otro filtro, que se aplica antes -----------------------------------------------------
# Los renglones SIN NOTA DE ENTRADA no son auditables y quedan fuera desde el principio.
# Sin nota de entrada no hay recepcion de mercancia que auditar, y ademas no se les puede
# construir el folio de agrupacion.


# =============================================================================
# 3. HOJA CONSOLIDADO — una fila por nota de entrada
# =============================================================================
#
# Es la hoja que se negocia con el proveedor. Cada fila responde:
# "por esta entrega, se pago X, se debio pagar Y, la diferencia es X - Y".


COLUMNAS_CONSOLIDADO = [
    "Proveedor",
    "Folio",                  # tienda + nota de entrada
    "Tienda/CEDIS",
    "Negocio",
    "Fecha Pedido",
    "Pedido",
    "Fec Recibo",
    "Nota Entrada",
    "Factura",
    "Total Pagado",           # lo que Soriana pago     (paso 2)
    "Debio Pagar",            # lo que debio pagar      (paso 2)
    "Diferencia",             # Total Pagado - Debio Pagar
    "Observaciones Auditor",  # se entrega en blanco, para que el auditor escriba
    "Fecha Pago",
    "Documento de Pago",
]

# Cuando el proveedor tiene devoluciones (paso 3) se agregan 6 columnas mas:
COLUMNAS_EXTRA_CUANDO_HAY_DEVOLUCIONES = [
    "Tipo Ajuste",             # MR8M, KG o ambos
    "Ajuste Pagos",            # cuanto se descontó (negativo)
    "Diferencia Ajustada",     # Diferencia + Ajuste Pagos  <- LA CIFRA QUE SE RECLAMA
    "Compensado",              # alerta de devoluciones autorizadas pero no ejecutadas
    "Conteo No Compensados",
    "Monto No Compensado",
]


def construir_consolidado(compras):
    """Una fila por nota de entrada, de las que pasaron el filtro."""
    renglones_que_califican = filtrar_notas_que_se_reclaman(compras)

    filas = []
    for folio, articulos_de_la_nota in renglones_que_califican.groupby("folio"):
        # Todos los articulos de una nota comparten los datos de cabecera y los totales
        # (recuerde del paso 2: "debio pagar" y "total pagado" son valores por grupo,
        # repetidos en cada renglon). Por eso basta tomar el primero.
        primero = articulos_de_la_nota.iloc[0]

        filas.append({
            "Proveedor": primero["numero_proveedor"],
            "Folio": folio,
            "Tienda/CEDIS": primero["tienda"],
            "Negocio": primero.get("organizacion") or "SORIANA",
            "Fecha Pedido": primero["fecha_pedido"],
            "Pedido": primero["numero_pedido"],
            "Fec Recibo": primero["fecha_recibo"],
            "Nota Entrada": primero["nota_entrada"],
            "Factura": primero["numero_factura"],
            "Total Pagado": primero["total_pagado_nota"],
            "Debio Pagar": primero["debio_pagar_nota"],
            "Diferencia": primero["diferencia_nota"],
            "Observaciones Auditor": "",
            "Fecha Pago": primero["fecha_pago"],
            "Documento de Pago": primero["documento_pago"],
        })

    return pd.DataFrame(filas, columns=COLUMNAS_CONSOLIDADO)


# =============================================================================
# 4. HOJA DETALLE PAGOS — una fila por articulo
# =============================================================================
#
# Es el sustento del Consolidado: para cada nota reclamada, que articulos la componen y
# como se llego a su importe. Aqui se ven lado a lado el costo del sistema y el auditado,
# que es lo que le permite al proveedor verificar el hallazgo.

COLUMNAS_DETALLE = [
    "Folio_Pedido", "FecPed", "Folio_NE", "FecRecibo", "Factura",
    "Tienda/CEDIS", "Division", "Categoria", "GciaCateg",
    "Material", "CodBarra", "Descripcion",
    "FactEmpaqu", "CantRec",
    "CtoUnitario_sistema",       # lo que Soriana pago      <-- se comparan
    "Costo Unitario correcto",   # el costo auditado        <-- estas dos
    "Porc_IEPS", "IEPS_Aud", "Porc_IVA", "IVA_Aud",
    "Debio Pagar correcto",      # importe auditado del renglon
]


def construir_detalle(compras, folios_del_consolidado):
    """El desglose por articulo, SOLO de las notas que entraron al Consolidado."""
    return compras[compras["folio"].isin(folios_del_consolidado)]


# =============================================================================
# 5. HOJA RESUMEN — la cifra
# =============================================================================


def calcular_total_a_reclamar(consolidado):
    """La suma que se le presenta al proveedor.

    Si hubo devoluciones se suma la "Diferencia Ajustada" (ya neta); si no, la
    "Diferencia" a secas. Nunca las dos: seria contar dos veces.
    """
    if "Diferencia Ajustada" in consolidado.columns:
        columna = "Diferencia Ajustada"
    else:
        columna = "Diferencia"
    return pd.to_numeric(consolidado[columna], errors="coerce").fillna(0).sum()


# =============================================================================
# 6. EL PERIODO AUDITADO VA EN EL ENCABEZADO
# =============================================================================
#
# Cada hoja lleva, bajo el nombre del proveedor:
#
#     "Validacion de Condiciones - Periodo 2020-2025"
#     "Validacion de Condiciones - Periodo 2020, 2022, 2025"
#
# El guion solo se usa cuando los años son CONSECUTIVOS. Si hay huecos se listan todos.
#
# La razon: un "2020-2025" en un entregable al que le falta 2022 se leeria como que ese
# año se reviso y no tuvo diferencias, cuando en realidad ni se miro. Hay proveedores
# cuya planeacion pide solo algunos años (los demas ya estaban cerrados).


def formatear_periodo(anios):
    """2020-2025 si son seguidos; 2020, 2022, 2025 si hay huecos."""
    anios = sorted(set(int(a) for a in anios))
    if not anios:
        return ""
    if len(anios) == 1:
        return str(anios[0])
    son_consecutivos = anios == list(range(anios[0], anios[-1] + 1))
    if son_consecutivos:
        return f"{anios[0]}-{anios[-1]}"
    return ", ".join(str(a) for a in anios)


# =============================================================================
# 7. EL ARMADO COMPLETO
# =============================================================================


def generar_validacion(compras_ya_calculadas, devoluciones=None):
    """Arma el entregable completo a partir del resultado de los pasos 1 y 2.

    ENTRA : compras con costo auditado y diferencias (paso 2)
            devoluciones del proveedor, si las tiene (paso 3)
    SALE  : las cuatro hojas del entregable
    """
    # -- 7.1 Filtrar y consolidar por nota de entrada ------------------------------------
    consolidado = construir_consolidado(compras_ya_calculadas)

    # -- 7.2 Aplicar las devoluciones ----------------------------------------------------
    bitacora_ajustes = pd.DataFrame()
    if devoluciones is not None and not devoluciones.empty:
        from importlib import import_module
        ajustes = import_module("03_ajustes_pagos")  # ver el paso 3
        consolidado, bitacora_ajustes = ajustes.aplicar_devoluciones(consolidado, devoluciones)
        consolidado = ajustes.quitar_los_totalmente_compensados(consolidado, UMBRAL_DIFERENCIA)

    # -- 7.3 El detalle, solo de lo que quedo --------------------------------------------
    folios = set(consolidado["Folio"])
    detalle = construir_detalle(compras_ya_calculadas, folios)

    # -- 7.4 El total --------------------------------------------------------------------
    total = calcular_total_a_reclamar(consolidado)

    return {
        "Resumen": total,
        "Consolidado": consolidado,
        "Ajustes": bitacora_ajustes,
        "Detalle PAGOS": detalle,
    }


# =============================================================================
# RESUMEN DE ESTE PASO
# =============================================================================
#
# Lo que hay que respetar al replicarlo:
#
#   1. Si hay clasificacion del auditor, esa manda sobre el calculo automatico.
#   2. Basta UN renglon "dif costos" para que entre la nota completa.
#   3. Sin clasificacion, entra lo que supere el umbral (hoy 1 peso; haganlo configurable).
#   4. El detalle solo lleva las notas que quedaron en el consolidado.
#   5. Si hubo devoluciones, la cifra que se reclama es "Diferencia Ajustada", no
#      "Diferencia".
#   6. Los renglones que la devolucion dejo en cero salen del consolidado y quedan en
#      la hoja Ajustes.
#
# ---------------------------------------------------------------------------------------
# FIN DEL RECORRIDO
#
#   01_cruce_cpa.py            emparejar compras con facturas electronicas
#   02_calculo_auditado.py     el costo correcto y la diferencia
#   03_ajustes_pagos.py        restar lo que el proveedor ya devolvio
#   04_validacion_condiciones  decidir que se reclama y presentarlo
#
# Dudas: Oscar Pineda.
