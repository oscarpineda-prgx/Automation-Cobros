"""
===============================================================================
PASO 2 de 4 — EL CALCULO AUDITADO: cuanto se debio pagar y cuanto se pago de mas
===============================================================================

ESTE ES EL CORAZON DE TODA LA AUDITORIA.

Despues del cruce (paso 1), cada renglon de compra tiene DOS versiones del costo:

    costo_unitario_sistema    lo que Soriana pago,      segun SAP
    costo_unitario_facturado  lo que el proveedor facturo, segun su CFDI

Este paso decide cual de los dos es el correcto, lo multiplica por la cantidad recibida,
le suma los impuestos, lo suma por nota de entrada y lo compara contra lo que realmente
se pago. Esa resta es la diferencia que se le reclama al proveedor.

Modulo real equivalente: automation_costos/calculations.py
"""

import numpy as np
import pandas as pd


# =============================================================================
# 1. LA PREGUNTA PREVIA: ¿ESTE RENGLON CRUZO CON UN CFDI?
# =============================================================================
#
# Todo el calculo depende de esta bandera, asi que hay que entenderla bien.
#
# "Cruzo" NO significa "el valor es distinto de cero".
# "Cruzo" significa "existe la factura electronica para este renglon".
#
# La diferencia importa muchisimo. Un CFDI puede traer IVA = 0 de forma legitima:
# los alimentos basicos estan exentos. Si midieramos "cruzo" como "valor != 0",
# a esos productos les pondriamos la tasa del sistema (16%) y les inventariamos un
# impuesto que nunca existio.
#
# Por eso se mide por PRESENCIA del dato, no por su valor.
#
# Regla acordada con Monica y Perla el 2026-07-31:
#   - Si el renglon cruzo -> los tres campos auditados toman lo del CFDI, AUNQUE SEA 0.
#   - Si no cruzo         -> se deja lo del sistema. Nunca se pone 0 al costo.


def este_renglon_cruzo_con_cfdi(compras):
    """True donde el renglon tiene factura electronica asociada."""
    tiene_uuid = tiene_dato(compras["uuid"])
    tiene_costo_del_cfdi = tiene_dato(compras["costo_unitario_facturado"])
    return tiene_uuid | tiene_costo_del_cfdi


def tiene_dato(columna):
    """True donde la celda trae algo real (no nulo, no cadena vacia)."""
    return ~(columna.isna() | (columna.astype(str).str.strip().isin(["", "None", "nan"])))


# =============================================================================
# 2. EL COSTO AUDITADO — la regla central
# =============================================================================
#
#   Se toma el MENOR de los dos costos, pero nunca cero.
#
# En palabras: si el proveedor facturo mas barato de lo que Soriana pago, el correcto
# es el del proveedor (y hay diferencia a favor de Soriana). Si facturo igual o mas caro,
# se respeta el del sistema y no hay nada que reclamar por este renglon.
#
#   costo_sistema = 12.00 , costo_cfdi = 11.00  ->  auditado = 11.00  (hay diferencia)
#   costo_sistema = 12.00 , costo_cfdi = 15.00  ->  auditado = 12.00  (sin diferencia)
#   costo_sistema = 12.00 , costo_cfdi =  0.00  ->  auditado = 12.00  (0 no es un costo)
#   costo_sistema = 12.00 , no cruzo            ->  auditado = 12.00
#
# El "nunca cero" no es un detalle menor: un cero se colaria como "el proveedor no cobro
# nada" y generaria una diferencia enorme y falsa.


def calcular_costo_auditado(compras, cruzo):
    """El costo unitario correcto segun la auditoria."""
    costo_sistema = a_numero(compras["costo_unitario_sistema"])
    costo_facturado = a_numero(compras["costo_unitario_facturado"])

    gana_el_del_cfdi = (
        cruzo                          # existe factura electronica
        & costo_facturado.gt(0)        # y el costo facturado es valido (no cero)
        & costo_facturado.lt(costo_sistema)  # y es MENOR que el del sistema
    )
    return np.where(gana_el_del_cfdi, costo_facturado, costo_sistema).round(4)


# =============================================================================
# 3. LAS TASAS DE IMPUESTO AUDITADAS
# =============================================================================
#
# Misma logica, pero SIN la condicion de "mayor que cero": aqui el cero SI es un valor
# legitimo (producto exento). Si el renglon cruzo, manda la tasa del CFDI tal cual.


def calcular_tasas_auditadas(compras, cruzo):
    """Devuelve (tasa_iva_auditada, tasa_ieps_auditada)."""
    # Del CFDI (lo que el proveedor declaro al SAT).
    tasa_iva_cfdi = a_numero(compras["tasa_iva"])
    tasa_ieps_cfdi = a_numero(compras["tasa_ieps"])

    # Del sistema de Soriana (tabla de impuestos T007S de SAP).
    tasa_iva_sistema = a_numero(compras["tasa_iva_sistema"])
    tasa_ieps_sistema = a_numero(compras["tasa_ieps_sistema"])

    tasa_iva = np.where(cruzo, tasa_iva_cfdi, tasa_iva_sistema).round(6)
    tasa_ieps = np.where(cruzo, tasa_ieps_cfdi, tasa_ieps_sistema).round(6)
    return tasa_iva, tasa_ieps


# =============================================================================
# 4. EL IMPORTE AUDITADO POR RENGLON
# =============================================================================
#
#   importe = costo_auditado x cantidad_recibida x (1 + IVA) x (1 + IEPS)
#
# Ojo con dos cosas al replicar:
#
#  a) La cantidad es la RECIBIDA (lo que entro a la tienda), no la facturada.
#     Se paga por lo que se recibe.
#
#  b) Los impuestos se aplican MULTIPLICANDO en cascada, no sumando las tasas.
#     Es decir (1+iva) x (1+ieps), no (1 + iva + ieps).


def calcular_importe_auditado(costo_auditado, cantidad_recibida, tasa_iva, tasa_ieps):
    """Lo que debio costar este renglon, con impuestos."""
    return (
        costo_auditado
        * cantidad_recibida
        * (1 + tasa_iva)
        * (1 + tasa_ieps)
    ).round(4)


# =============================================================================
# 5. EL FOLIO: la unidad a la que se reclama
# =============================================================================
#
# Una compra no se reclama renglon por renglon: se reclama por NOTA DE ENTRADA, que es
# el documento con el que la mercancia entro a la tienda. El folio es su identificador.
#
#   folio = prefijo + tienda (4 digitos) + nota de entrada (8 digitos)
#
# Los dos campos se rellenan con ceros a la izquierda y se recortan a su longitud, para
# que "5537" y "05537" no generen dos folios distintos.
#
# En SQL Server:  RIGHT('0000' + CAST(tienda AS varchar), 4)


PREFIJO_FOLIO = "11004"


def construir_folio(tienda, nota_entrada):
    """Arma el folio de agrupacion."""
    tienda_texto = tienda.astype(str).str.strip().str.zfill(4).str[-4:]
    nota_texto = nota_entrada.astype(str).str.strip().str.zfill(8).str[-8:]
    return PREFIJO_FOLIO + tienda_texto + nota_texto


# =============================================================================
# 6. LOS DOS NIVELES DE AGREGACION
# =============================================================================
#
# El calculo se cierra en DOS niveles distintos, porque el pago no siempre coincide con
# la nota de entrada:
#
#   NIVEL 1 — NOTA DE ENTRADA (folio)   <- es el que manda para reclamar
#   NIVEL 2 — FACTURA                    <- control, para casos de facturas cruzadas
#
# En ambos la mecanica es la misma:
#
#   debio_pagar = SUMA de los importes auditados del grupo
#   total_pagado = MAXIMO del monto pagado del grupo   <-- ojo, MAXIMO, no suma
#   diferencia   = total_pagado - debio_pagar
#
# ¿POR QUE EL MAXIMO Y NO LA SUMA?
# Porque el monto pagado viene REPETIDO en cada renglon del grupo: es un dato a nivel
# documento que el sistema replica en cada linea. Sumarlo multiplicaria el pago por el
# numero de articulos, inflando el resultado de forma absurda.
#
#   3 renglones, cada uno con "pagado = 1,500"  ->  se pago 1,500, no 4,500.
#
# En SQL Server:  MAX(monto_pagado) OVER (PARTITION BY folio)


def calcular_por_nota_de_entrada(compras):
    """Nivel 1: agrupa por folio (tienda + nota de entrada). ES EL QUE SE RECLAMA."""
    compras["debio_pagar_nota"] = (
        compras.groupby("folio", dropna=False)["importe_auditado"].transform("sum").round(4)
    )
    compras["total_pagado_nota"] = (
        compras.groupby("folio", dropna=False)["monto_pagado"].transform("max").round(4)
    )
    # POSITIVA = Soriana pago de mas = hay que reclamar.
    compras["diferencia_nota"] = (
        compras["total_pagado_nota"] - compras["debio_pagar_nota"]
    ).round(4)
    return compras


def calcular_por_factura(compras):
    """Nivel 2: lo mismo, agrupando por factura. Es informacion de control.

    Existe porque hay pagos que cubren varias notas de entrada de una misma factura.
    Cuando eso pasa, el nivel de nota puede repartir mal y este nivel sirve de contraste.
    """
    llave_factura = (
        compras["numero_proveedor"].astype(str) + "|"
        + compras["tienda"].astype(str) + "|"
        + compras["numero_factura"].astype(str)
    )
    compras["debio_pagar_factura"] = (
        compras.groupby(llave_factura, dropna=False)["importe_auditado"].transform("sum").round(4)
    )
    compras["total_pagado_factura"] = (
        compras.groupby(llave_factura, dropna=False)["monto_pagado"].transform("max").round(4)
    )
    compras["diferencia_factura"] = (
        compras["total_pagado_factura"] - compras["debio_pagar_factura"]
    ).round(4)
    return compras


# =============================================================================
# 7. EL CALCULO COMPLETO, DE PRINCIPIO A FIN
# =============================================================================


def recalcular(compras):
    """Aplica toda la logica de auditoria sobre las compras ya cruzadas.

    ENTRA: compras con las columnas EDI llenas (salida del paso 1).
    SALE : las mismas compras + las columnas de auditoria y la diferencia.
    """
    # -- 7.1 ¿Cruzo con CFDI? ------------------------------------------------------------
    cruzo = este_renglon_cruzo_con_cfdi(compras)

    # -- 7.2 El costo correcto -----------------------------------------------------------
    compras["costo_auditado"] = calcular_costo_auditado(compras, cruzo)

    # -- 7.3 Las tasas correctas ---------------------------------------------------------
    tasa_iva, tasa_ieps = calcular_tasas_auditadas(compras, cruzo)
    compras["tasa_iva_auditada"] = tasa_iva
    compras["tasa_ieps_auditada"] = tasa_ieps

    # -- 7.4 El importe por renglon ------------------------------------------------------
    compras["importe_auditado"] = calcular_importe_auditado(
        a_numero(compras["costo_auditado"]),
        a_numero(compras["cantidad_recibida"]),
        a_numero(compras["tasa_iva_auditada"]),
        a_numero(compras["tasa_ieps_auditada"]),
    )

    # -- 7.5 El folio de agrupacion ------------------------------------------------------
    compras["folio"] = construir_folio(compras["tienda"], compras["nota_entrada"])

    # -- 7.6 Los dos niveles -------------------------------------------------------------
    compras = calcular_por_nota_de_entrada(compras)
    compras = calcular_por_factura(compras)

    return compras


def a_numero(columna):
    """Convierte a numero lo que se pueda; lo que no, queda en 0."""
    return pd.to_numeric(columna, errors="coerce").fillna(0.0)


# =============================================================================
# EJEMPLO COMPLETO, CON NUMEROS
# =============================================================================
#
# Una nota de entrada con 2 articulos:
#
#   ARTICULO A
#     costo sistema  : 12.00      costo CFDI : 11.00   -> auditado 11.00 (gana el CFDI)
#     cantidad recibida: 100      IVA: 16%   IEPS: 0%
#     importe auditado = 11.00 x 100 x 1.16 x 1.00 = 1,276.00
#
#   ARTICULO B
#     costo sistema  :  5.00      costo CFDI :  7.00   -> auditado  5.00 (gana el sistema)
#     cantidad recibida:  50      IVA: 0%    IEPS: 0%   (alimento exento)
#     importe auditado =  5.00 x  50 x 1.00 x 1.00 =   250.00
#
#   POR LA NOTA DE ENTRADA
#     debio pagar  = 1,276.00 + 250.00 = 1,526.00
#     total pagado =                     1,626.00   (MAXIMO del grupo, no suma)
#     DIFERENCIA   = 1,626.00 - 1,526.00 =  100.00  -> se reclaman 100.00
#
# Note que el articulo B no aporto diferencia (su costo de sistema era el bueno) pero SI
# entra al calculo: la nota se evalua completa, no articulo por articulo.
#
# SIGUE -> 03_ajustes_pagos.py  (esos 100.00 aun pueden anularse si el proveedor
#                                 ya devolvio el dinero)
