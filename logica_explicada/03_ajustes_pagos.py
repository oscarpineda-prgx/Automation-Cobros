"""
===============================================================================
PASO 3 de 4 — LOS AJUSTES: devoluciones que anulan diferencias ya detectadas
===============================================================================

QUE RESUELVE ESTE PASO
----------------------
El paso 2 encontro que Soriana pago 100 de mas en una nota de entrada. Pero puede que el
proveedor YA haya devuelto ese dinero, por su cuenta, meses despues. Si no lo tomamos en
cuenta, le estariamos reclamando algo que ya reintegro.

Este paso busca esas devoluciones y las descuenta.

Es la diferencia entre "diferencia detectada" y "diferencia a reclamar":

    diferencia detectada     1,020,510,983    <- lo que encontro el paso 2
    menos devoluciones        -169,239,436    <- lo que el proveedor ya devolvio
    ------------------------------------------
    diferencia A RECLAMAR      851,271,547    <- lo que de verdad se le cobra

Modulo real equivalente: automation_costos/ajustes_pagos.py
"""

import pandas as pd


# =============================================================================
# 1. DE DONDE SALEN LAS DEVOLUCIONES
# =============================================================================
#
# De la tabla de pagos de Soriana (F_APV2), filtrando dos tipos de movimiento:
#
#   MR8M   -> se identifica por el campo DOC_TEXT = "MR8M"
#   KG-14  -> se identifica por COD_TYPE_CODE = "KG"
#             Y ADEMAS el campo BSAK_BSIK_XREF3 debe EMPEZAR EN "14"
#
# En los dos casos el importe tiene que ser NEGATIVO: es una devolucion, dinero que
# regresa. Un importe positivo con esas claves es otra cosa y no aplica.

PERIODO_INICIO = "2020-01-01"
PERIODO_FIN = "2026-03-31"

# ATENCION AL CORTE: el periodo llega hasta MARZO DE 2026, no hasta diciembre de 2025.
# Esto no es un descuido, es necesario. Una compra de 2025 puede devolverse en enero de
# 2026, y esa devolucion cuenta.
#
# Con el corte anterior (31-dic-2025) se perdian TODAS las devoluciones de 2026. Se
# detecto en el proveedor FRABEL: una nota con un KG-14 de $136,906.68 del 20-ene-2026
# que nunca se aplicaba. Solo en ese proveedor se perdian 254 movimientos y $8.9 millones.
#
# Ampliar el corte es seguro: una devolucion solo surte efecto si coincide con una nota
# que YA esta en el resultado del paso 2, y ese esta acotado al periodo auditado. Lo que
# no cruza, no hace nada.


# --- El filtro del XREF3 que empieza en "14" es una PROTECCION, no un capricho ---------
#
# Sin ese filtro entrarian movimientos KG que NO son devoluciones de mercancia: son
# asientos contables globales ("VIAJES BACK HAUL", "DESCTO X MANIOBR", "APORTACION ECOM"),
# partidas de hasta -47 millones sin relacion con una nota de entrada concreta.
#
# Se evaluo cruzar esos por factura y se DESCARTO con datos: habrian borrado diferencias
# reales y legitimas. El filtro "14" es justo lo que nos protege de ellos.


def clasificar_devoluciones(movimientos_de_pago):
    """Deja solo las devoluciones MR8M y KG-14 aplicables."""
    texto_documento = texto(movimientos_de_pago, "DOC_TEXT").str.upper()
    codigo_tipo = texto(movimientos_de_pago, "COD_TYPE_CODE").str.upper()
    referencia = texto(movimientos_de_pago, "BSAK_BSIK_XREF3")
    importe = pd.to_numeric(movimientos_de_pago["GrsInvAmt"], errors="coerce").fillna(0)

    es_mr8m = texto_documento.eq("MR8M") & importe.lt(0)
    es_kg14 = codigo_tipo.eq("KG") & referencia.str.startswith("14") & importe.lt(0)

    devoluciones = movimientos_de_pago[es_mr8m | es_kg14].copy()
    devoluciones["tipo"] = ""
    devoluciones.loc[es_mr8m, "tipo"] = "MR8M"
    devoluciones.loc[es_kg14, "tipo"] = "KG"

    # COMPENSADA o NO: lo decide el numero de cheque (ChkNbr).
    #   con numero de cheque -> el dinero ya se movio  -> se RESTA
    #   sin numero de cheque -> esta autorizada pero no ejecutada -> NO se resta, se avisa
    devoluciones["ya_se_ejecuto"] = texto(devoluciones, "ChkNbr").ne("")
    return devoluciones


def texto(tabla, columna):
    """Lee una columna como texto limpio, aunque no exista."""
    if columna not in tabla.columns:
        return pd.Series([""] * len(tabla), index=tabla.index)
    return tabla[columna].fillna("").astype(str).str.strip()


# =============================================================================
# 2. COMO SE LIGA CADA TIPO — son llaves DISTINTAS
# =============================================================================
#
# Este es el punto mas facil de equivocar al replicar la logica:
#
#   MR8M  ->  proveedor + FACTURA
#             No trae nota de entrada ni tienda, asi que no se puede ser mas preciso.
#             Como una factura puede cubrir varias notas, un MR8M puede cruzar VARIOS
#             renglones a la vez (ver el reparto en cascada, seccion 3).
#
#   KG-14 ->  proveedor + NOTA DE ENTRADA + TIENDA
#             Es exactamente el folio, asi que cruza un solo renglon.


def encontrar_renglones_que_cruzan(resultado_auditoria, devolucion):
    """Que renglones del resultado toca esta devolucion."""
    mismo_proveedor = resultado_auditoria["Proveedor"] == normalizar(devolucion.vndnbr)

    if devolucion.tipo == "MR8M":
        misma_factura = (
            resultado_auditoria["Factura"].map(normalizar_factura)
            == normalizar_factura(devolucion.invnbr)
        )
        return mismo_proveedor & misma_factura

    # KG-14: nota de entrada + tienda.
    misma_nota = resultado_auditoria["Nota Entrada"] == normalizar(devolucion.rcpnbr)
    misma_tienda = resultado_auditoria["Tienda/CEDIS"] == normalizar(devolucion.strnbr)
    return mismo_proveedor & misma_nota & misma_tienda


# =============================================================================
# 3. EL REPARTO EN CASCADA — la parte delicada
# =============================================================================
#
# Cuando una devolucion cruza VARIOS renglones (tipico del MR8M por factura), hay que
# repartir su monto entre ellos. Dos reglas:
#
#   A) Nunca se descuenta mas de lo que ese renglon tiene de diferencia.
#      Si el renglon tiene 100 de diferencia y la devolucion es de 500, se le quitan 100.
#
#   B) El sobrante pasa al siguiente renglon, hasta agotar la devolucion.
#
# Sin la regla A, una devolucion grande dejaria diferencias NEGATIVAS, como si el
# proveedor hubiera devuelto de mas, y el total a reclamar saldria mal.
#
#   Devolucion de 250 sobre tres renglones con diferencias 100, 100 y 100:
#
#       renglon 1: tenia 100 -> se le quitan 100 -> queda 0    (restan 150)
#       renglon 2: tenia 100 -> se le quitan 100 -> queda 0    (restan  50)
#       renglon 3: tenia 100 -> se le quitan  50 -> queda 50   (restan   0)


def aplicar_devoluciones(resultado_auditoria, devoluciones):
    """Descuenta las devoluciones. Devuelve (resultado_ajustado, bitacora)."""
    resultado = resultado_auditoria.reset_index(drop=True).copy()
    diferencia = pd.to_numeric(resultado["Diferencia"], errors="coerce").fillna(0)

    resultado["Tipo Ajuste"] = ""
    resultado["Ajuste Pagos"] = 0.0            # cuanto se descontó (negativo)
    resultado["Compensado"] = ""               # bandera de alerta
    resultado["Conteo No Compensados"] = 0
    resultado["Monto No Compensado"] = 0.0

    # Cuanto le queda de diferencia a cada renglon, conforme se va consumiendo.
    # Nunca baja de cero: esa es la regla A.
    disponible_por_renglon = diferencia.clip(lower=0).tolist()

    bitacora = []

    for devolucion in devoluciones.itertuples(index=False):
        cruzan = encontrar_renglones_que_cruzan(resultado, devolucion)
        indices = list(resultado.index[cruzan])
        if not indices:
            continue  # esta devolucion no corresponde a nada auditado: se ignora

        monto = abs(devolucion.importe)

        # --- CASO 1: autorizada pero NO ejecutada ---------------------------------------
        # No se resta nada. Solo se marca, para que el auditor sepa que hay una devolucion
        # en camino que todavia no se refleja en los pagos.
        if not devolucion.ya_se_ejecuto:
            for i in indices:
                resultado.at[i, "Conteo No Compensados"] += 1
                resultado.at[i, "Monto No Compensado"] += monto
                resultado.at[i, "Compensado"] = "No compensado/ejecutado"
                resultado.at[i, "Tipo Ajuste"] = devolucion.tipo
                bitacora.append(fila_bitacora(resultado, i, devolucion, aplicado=0, pendiente=monto))
            continue

        # --- CASO 2: ejecutada -> se consume en cascada ---------------------------------
        por_repartir = monto
        for i in indices:
            if por_repartir <= 0.005:      # ya se repartio todo (medio centavo de holgura)
                break
            disponible = disponible_por_renglon[i]
            if disponible <= 0.005:        # este renglon ya no tiene diferencia que anular
                continue

            se_toma = min(disponible, por_repartir)   # <- REGLA A
            disponible_por_renglon[i] = disponible - se_toma
            por_repartir -= se_toma                   # <- REGLA B

            resultado.at[i, "Ajuste Pagos"] -= se_toma
            resultado.at[i, "Tipo Ajuste"] = devolucion.tipo
            bitacora.append(fila_bitacora(resultado, i, devolucion, aplicado=-se_toma, pendiente=0))

    # La diferencia final, ya neta de devoluciones. ESTA es la que se reclama.
    resultado["Diferencia Ajustada"] = (
        diferencia + pd.to_numeric(resultado["Ajuste Pagos"], errors="coerce").fillna(0)
    ).round(2)

    return resultado, pd.DataFrame(bitacora)


# =============================================================================
# 4. QUE PASA CON LOS RENGLONES QUE QUEDARON EN CERO
# =============================================================================
#
# Un renglon cuya diferencia quedo completamente anulada por la devolucion SALE del
# entregable principal y queda registrado en la bitacora de ajustes.
#
# No se borra ni se esconde: se mueve. Sigue siendo trazable, pero ya no se reclama.
#
# Cuidado con la lectura: un proveedor cuyas diferencias fueron TODAS anuladas no es un
# proveedor "sin hallazgos". Es un proveedor "100% compensado": si se le encontraron
# diferencias, y ya las devolvio. Se etiqueta distinto a proposito, porque decir
# "sin diferencias" se leia como que no se le encontro nada.


def quitar_los_totalmente_compensados(resultado, umbral=1.0):
    """Saca del entregable los renglones que la devolucion dejo en ~0."""
    diferencia_final = pd.to_numeric(resultado["Diferencia Ajustada"], errors="coerce").fillna(0)
    hubo_ajuste = resultado["Ajuste Pagos"].abs() > 0.005
    quedo_en_cero = diferencia_final <= umbral

    totalmente_compensado = hubo_ajuste & quedo_en_cero
    return resultado[~totalmente_compensado].reset_index(drop=True)


# =============================================================================
# 5. UTILIDADES
# =============================================================================


def normalizar(codigo):
    """Codigos como texto limpio, sin el '.0' que Excel agrega a los numeros."""
    if codigo is None or pd.isna(codigo):
        return ""
    texto_codigo = str(codigo).strip()
    if texto_codigo.endswith(".0"):
        texto_codigo = texto_codigo[:-2]
    return texto_codigo.lstrip("0")


def normalizar_factura(valor):
    """Misma normalizacion de factura del paso 1: mayusculas, solo letras y numeros."""
    import re
    if valor is None or pd.isna(valor):
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(valor).upper())


def fila_bitacora(resultado, i, devolucion, *, aplicado, pendiente):
    """Un renglon de la bitacora de ajustes, para que todo quede trazable."""
    return {
        "Proveedor": resultado.at[i, "Proveedor"],
        "Tienda/CEDIS": resultado.at[i, "Tienda/CEDIS"],
        "Nota Entrada": resultado.at[i, "Nota Entrada"],
        "Factura": resultado.at[i, "Factura"],
        "Diferencia Original": resultado.at[i, "Diferencia"],
        "Tipo Ajuste": devolucion.tipo,
        "Compensado": "Si" if devolucion.ya_se_ejecuto else "No compensado/ejecutado",
        "Ajuste Aplicado": aplicado,
        "Monto No Compensado": pendiente,
        "Documento Pago": devolucion.chknbr,
        "Fecha Pago": devolucion.chkdt,
    }


# =============================================================================
# RESUMEN DE ESTE PASO
# =============================================================================
#
# Lo que hay que respetar al replicarlo:
#
#   1. MR8M se liga por proveedor + FACTURA; KG-14 por proveedor + NOTA + TIENDA.
#   2. El KG-14 exige que XREF3 empiece en "14" (protege de asientos globales enormes).
#   3. El importe debe ser NEGATIVO.
#   4. El periodo llega a MARZO 2026, no a diciembre 2025.
#   5. Sin numero de cheque NO se resta: solo se marca.
#   6. El reparto es en cascada y nunca deja una diferencia negativa.
#
# SIGUE -> 04_validacion_condiciones.py
