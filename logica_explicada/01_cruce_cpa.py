"""
===============================================================================
PASO 1 de 4 — EL CRUCE: emparejar las compras de Soriana con los CFDI del proveedor
===============================================================================

QUE RESUELVE ESTE PASO
----------------------
Soriana tiene sus compras en SAP: que compro, a que costo lo pago, en que tienda.
El proveedor tiene sus facturas electronicas (CFDI): que vendio y a que costo lo facturo.

Son dos versiones del mismo hecho. El cruce las pone lado a lado, renglon por renglon,
para poder compararlas en el paso 2.

El resultado del cruce son las llamadas "columnas EDI" del archivo de Compras: columnas
que quedan vacias hasta que se encuentra el CFDI correspondiente y se llenan con lo que
el proveedor realmente facturo.

    Compras (SAP)              CFDI (CPA Vision)           Resultado
    ---------------            -----------------           ---------
    producto X                 producto X                  costo Soriana : 12.00
    costo pagado 12.00    +    costo facturado 11.00  =    costo CFDI    : 11.00
                                                           -> hay 1.00 de diferencia

Modulo real equivalente: automation_costos/cruce_cpa.py
"""

import re

import pandas as pd


# =============================================================================
# 1. QUE COLUMNAS SE LLENAN
# =============================================================================

# --- Se COPIAN tal cual del CFDI -------------------------------------------------------
# A la izquierda el nombre en el archivo de Compras, a la derecha el nombre en el CFDI.
COLUMNAS_QUE_SE_COPIAN_DEL_CFDI = {
    "cantidad_facturada":      "Cantidad",        # cuantas piezas facturo el proveedor
    "costo_unitario_facturado": "Valor Unitario", # a que costo unitario las facturo
    "tasa_ieps":               "TASA IEPS",       # porcentaje de IEPS (0.08, 0.53, 0...)
    "importe_ieps":            "IEPS",            # importe de IEPS en pesos
    "tasa_iva":                "TASA IVA",        # porcentaje de IVA (0.16, 0.08, 0...)
    "importe_iva":             "IVA",             # importe de IVA en pesos
    "total_factura":           "Total",           # total de TODA la factura
    "uuid":                    "UUID",            # folio fiscal unico del SAT
}

# --- Se toma del propio archivo de Compras ---------------------------------------------
# El factor de empaque (piezas por caja) NO viene en el CFDI: Soriana ya lo tiene.
COLUMNA_QUE_VIENE_DEL_PROPIO_COMPRAS = {"factor_empaque_edi": "factor_empaque"}

# --- Se CALCULAN a partir de las anteriores --------------------------------------------
COLUMNAS_QUE_SE_CALCULAN = ("costo_bruto_facturado", "importe_por_articulo")


# IMPORTANTE — decision de negocio verificada sobre 66 millones de renglones:
# el IVA y el IEPS se COPIAN del CFDI, NO se despejan del total de la factura.
# Despejarlos daba resultados incorrectos porque el total de la factura incluye
# productos con tasas distintas (0%, 8%, 16%) mezclados en el mismo documento.


# =============================================================================
# 2. LA LLAVE DEL CRUCE
# =============================================================================
#
# Para saber que renglon de Compras corresponde a que concepto del CFDI se usan
# TRES datos:
#
#   1. RFC del proveedor      -> ya viene filtrado: cada descarga es de un solo RFC
#   2. Codigo de barras       -> identifica el PRODUCTO
#   3. Numero de factura      -> identifica el DOCUMENTO
#
# El problema esta en el numero de factura: en el sistema de Soriana se capturo de
# forma inconsistente. En un mismo proveedor conviven:
#
#       "FN-21226"      "FN21226"      "-21226"      "0021226"
#
# Todas se refieren a la misma factura. Por eso el cruce se hace en DOS PASADAS.

EXPRESION_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]")
EXPRESION_NO_DIGITO = re.compile(r"\D")


def normalizar_factura_con_serie(valor):
    """Pasada 1: deja mayusculas y quita todo lo que no sea letra o numero.

    CONSERVA la serie, que es la parte que distingue facturas de distintas sucursales
    o series del proveedor.

        "FN-21226"  ->  "FN21226"
        "fn 21226"  ->  "FN21226"
    """
    if valor is None or pd.isna(valor):
        return ""
    return EXPRESION_NO_ALFANUMERICO.sub("", str(valor).upper())


def normalizar_factura_solo_numeros(valor):
    """Pasada 2 (respaldo): deja SOLO los digitos y quita los ceros de la izquierda.

    Es mas laxa porque ignora la serie. Por eso se usa unicamente sobre lo que no
    cruzo en la pasada 1.

        "FN-21226"  ->  "21226"
        "0021226"   ->  "21226"
    """
    if valor is None or pd.isna(valor):
        return ""
    return EXPRESION_NO_DIGITO.sub("", str(valor)).lstrip("0")


# En SQL Server, el equivalente de estas dos normalizaciones seria una funcion escalar
# o una columna calculada persistida. Conviene indexarla: el cruce se hace millones de
# veces y comparar cadenas sin indice es el cuello de botella.


# =============================================================================
# 3. LAS DOS REGLAS DE SEGURIDAD
# =============================================================================
#
# REGLA A — SOLO SE RELLENAN CELDAS VACIAS
#   Si el archivo de Compras ya traia un dato en una columna EDI, el cruce NO lo pisa.
#   Lo que un auditor capturo a mano siempre gana. Esto hace que el proceso se pueda
#   volver a correr sin miedo: nunca destruye trabajo previo.
#
# REGLA B — LOS CFDI EN CONFLICTO SE DESCARTAN
#   Si una misma llave (producto + factura) apunta a varios conceptos del CFDI con
#   valores DISTINTOS, no se elige ninguno: se deja vacio y se reporta.
#   Preferimos no llenar a llenar mal.
#
#   Ojo con el matiz: si las lineas repetidas tienen valores IDENTICOS, no hay conflicto
#   y se colapsan en una sola. Es lo normal (medido en Nestle: 99.94% de las llaves
#   repetidas coinciden en todo). El descarte aplica solo cuando de verdad difieren.


def dejar_un_solo_concepto_por_llave(cfdi, columnas_llave):
    """Aplica la REGLA B: un concepto por llave, descartando los conflictos reales.

    Devuelve (conceptos_unicos, cuantos_se_descartaron).
    """
    # Solo sirven las filas que tienen la llave completa.
    llave_completa = (cfdi[columnas_llave] != "").all(axis=1)
    conceptos = cfdi.loc[llave_completa]

    # Paso 1: colapsar las lineas identicas (mismo valor en todo lo que se copia).
    #         Estas son duplicados inofensivos.
    columnas_copiadas = list(COLUMNAS_QUE_SE_COPIAN_DEL_CFDI.values())
    conceptos = conceptos.drop_duplicates(subset=columnas_llave + columnas_copiadas)

    # Paso 2: lo que SIGA repetido en la llave es un conflicto real de valores.
    #         keep=False elimina TODAS las copias, no deja ninguna.
    conceptos_unicos = conceptos.drop_duplicates(subset=columnas_llave, keep=False)

    descartados_por_conflicto = len(conceptos) - len(conceptos_unicos)
    return conceptos_unicos.set_index(columnas_llave), descartados_por_conflicto


# En SQL Server esto es: agrupar por la llave, contar los valores DISTINTOS de las
# columnas que se copian, y quedarse solo con los grupos que tienen exactamente uno.
#
#   SELECT llave FROM conceptos
#   GROUP BY llave
#   HAVING COUNT(DISTINCT CONCAT(cantidad, costo, tasa_iva, ...)) = 1


# =============================================================================
# 4. EL CRUCE, PASO A PASO
# =============================================================================


def cruzar_compras_con_cfdi(compras, cfdi):
    """Llena las columnas EDI de `compras` con los datos de `cfdi`.

    `compras` : un renglon por articulo comprado (de SAP)
    `cfdi`    : un renglon por concepto facturado (de CPA Vision)
    """
    conteo = {
        "renglones_totales": len(compras),
        "cruzados_pasada_1": 0,
        "cruzados_pasada_2": 0,
        "celdas_llenadas": 0,
        "descartados_por_conflicto": 0,
    }

    # -- 4.1 Preparar las llaves en ambos lados ------------------------------------------
    compras["llave_producto"] = compras["codigo_barras"].map(normalizar_factura_solo_numeros)
    compras["llave_factura_con_serie"] = compras["numero_factura"].map(normalizar_factura_con_serie)
    compras["llave_factura_solo_numeros"] = compras["numero_factura"].map(normalizar_factura_solo_numeros)

    cfdi["llave_producto"] = cfdi["noIdentificacion"].map(normalizar_factura_solo_numeros)
    cfdi["llave_factura_con_serie"] = (
        cfdi["Serie"].fillna("").astype(str) + cfdi["Folio"].fillna("").astype(str)
    ).map(normalizar_factura_con_serie)
    cfdi["llave_factura_solo_numeros"] = cfdi["Folio"].map(normalizar_factura_solo_numeros)

    # NOTA: para el codigo de barras se usa la misma funcion de "solo numeros" porque el
    # codigo de barras es numerico y a veces trae ceros a la izquierda o notacion
    # cientifica al pasar por Excel (7.50102E+12). Normalizarlo evita ese problema.

    # -- 4.2 Armar los dos indices de busqueda (aplicando la REGLA B) --------------------
    indice_pasada_1, descartados_1 = dejar_un_solo_concepto_por_llave(
        cfdi, ["llave_producto", "llave_factura_con_serie"]
    )
    indice_pasada_2, descartados_2 = dejar_un_solo_concepto_por_llave(
        cfdi, ["llave_producto", "llave_factura_solo_numeros"]
    )
    conteo["descartados_por_conflicto"] = descartados_1 + descartados_2

    # -- 4.3 PASADA 1: la principal, con serie -------------------------------------------
    datos_encontrados = buscar_en_indice(
        compras, indice_pasada_1, ["llave_producto", "llave_factura_con_serie"]
    )
    columnas_copiadas = list(COLUMNAS_QUE_SE_COPIAN_DEL_CFDI)
    sin_cruzar = datos_encontrados[columnas_copiadas].isna().all(axis=1)
    conteo["cruzados_pasada_1"] = int((~sin_cruzar).sum())

    # -- 4.4 PASADA 2: respaldo, SOLO sobre lo que quedo sin cruzar ----------------------
    # Es mas laxa (ignora la serie), asi que va en segundo lugar y solo sobre el resto.
    # El riesgo de emparejar mal queda acotado porque la busqueda ya viene restringida
    # por RFC y por codigo de barras.
    if sin_cruzar.any():
        datos_respaldo = buscar_en_indice(
            compras.loc[sin_cruzar], indice_pasada_2,
            ["llave_producto", "llave_factura_solo_numeros"],
        )
        datos_encontrados.loc[sin_cruzar] = datos_respaldo
        conteo["cruzados_pasada_2"] = int(
            (~datos_respaldo[columnas_copiadas].isna().all(axis=1)).sum()
        )

    # -- 4.5 Copiar los valores, aplicando la REGLA A ------------------------------------
    este_renglon_cruzo = datos_encontrados[columnas_copiadas].notna().any(axis=1)

    for columna in COLUMNAS_QUE_SE_COPIAN_DEL_CFDI:
        celda_vacia = esta_vacia(compras[columna]) & datos_encontrados[columna].notna()
        compras.loc[celda_vacia, columna] = datos_encontrados.loc[celda_vacia, columna]
        conteo["celdas_llenadas"] += int(celda_vacia.sum())

    # El factor de empaque se copia desde el propio Compras, pero SOLO en los renglones
    # que cruzaron: sin CFDI no hay nada que completar.
    for destino, origen in COLUMNA_QUE_VIENE_DEL_PROPIO_COMPRAS.items():
        celda_vacia = esta_vacia(compras[destino]) & este_renglon_cruzo
        compras.loc[celda_vacia, destino] = compras.loc[celda_vacia, origen]
        conteo["celdas_llenadas"] += int(celda_vacia.sum())

    # -- 4.6 Calcular las columnas derivadas ---------------------------------------------
    calcular_columnas_derivadas(compras)

    return compras, conteo


def buscar_en_indice(compras, indice, columnas_llave):
    """Trae del CFDI los valores que corresponden a cada renglon de compras.

    Equivale a un LEFT JOIN: los renglones sin CFDI quedan en nulo.
    """
    encontrado = indice.reindex(pd.MultiIndex.from_frame(compras[columnas_llave]))
    encontrado.index = compras.index
    # Renombra las columnas del CFDI al nombre que llevan en Compras.
    return encontrado.rename(
        columns={origen: destino for destino, origen in COLUMNAS_QUE_SE_COPIAN_DEL_CFDI.items()}
    )


def esta_vacia(columna):
    """True donde la celda no tiene dato: nulo, cadena vacia o texto basura de Excel."""
    return columna.isna() | (columna.astype(str).str.strip().isin(["", "None", "nan"]))


# =============================================================================
# 5. LAS DOS COLUMNAS QUE SE CALCULAN
# =============================================================================


def calcular_columnas_derivadas(compras):
    """Calcula el costo bruto facturado y el importe por articulo.

    Solo se escriben donde estaban vacias Y donde hay insumo (es decir, donde el cruce
    encontro el costo unitario del CFDI). Asi no se inventan ceros en renglones que
    nunca tuvieron factura electronica.
    """
    costo_unitario = pd.to_numeric(compras["costo_unitario_facturado"], errors="coerce").fillna(0)
    factor_empaque = pd.to_numeric(compras["factor_empaque_edi"], errors="coerce").fillna(0)
    cantidad = pd.to_numeric(compras["cantidad_facturada"], errors="coerce").fillna(0)
    tasa_iva = pd.to_numeric(compras["tasa_iva"], errors="coerce").fillna(0)

    hay_insumo = ~esta_vacia(compras["costo_unitario_facturado"])

    # Costo por CAJA = costo por pieza x piezas por caja.
    costo_bruto = costo_unitario * factor_empaque

    # Importe del articulo, con IVA incluido.
    importe = costo_bruto * cantidad * (1 + tasa_iva)

    for columna, valores in (("costo_bruto_facturado", costo_bruto),
                             ("importe_por_articulo", importe)):
        hueco = esta_vacia(compras[columna]) & hay_insumo
        compras.loc[hueco, columna] = valores[hueco]


# =============================================================================
# 6. CONTROL DE CALIDAD: LA DOBLE VALIDACION DE IMPUESTOS
# =============================================================================


def validar_importes_de_impuesto(compras):
    """Compara el impuesto COPIADO del CFDI contra el impuesto DESPEJADO del total.

    No corrige nada: solo cuenta discrepancias, como termometro de calidad de datos.
    El valor bueno es SIEMPRE el copiado del CFDI.

    Se conserva porque fue lo que permitio demostrar, sobre 66 millones de renglones,
    que despejar el impuesto desde el total de la factura da resultados incorrectos
    cuando la factura mezcla productos con tasas distintas.
    """
    total_factura = pd.to_numeric(compras["total_factura"], errors="coerce").fillna(0)
    discrepancias = {}

    for columna_importe, columna_tasa in (("importe_iva", "tasa_iva"),
                                          ("importe_ieps", "tasa_ieps")):
        tasa = pd.to_numeric(compras[columna_tasa], errors="coerce").fillna(0)

        # Formula clasica de "sacar el impuesto de un monto que ya lo incluye".
        # Si la tasa es 0 el impuesto es 0 (no se divide entre 1).
        impuesto_despejado = (total_factura / (1 + tasa) * tasa).where(tasa > 0, 0.0)

        importe_real = pd.to_numeric(compras[columna_importe], errors="coerce").fillna(0)
        difieren = (importe_real - impuesto_despejado).abs() > 0.02  # tolerancia 2 centavos
        discrepancias[columna_importe] = int(difieren.sum())

    return discrepancias


# =============================================================================
# RESUMEN DE ESTE PASO
# =============================================================================
#
# ENTRA : compras de SAP (con las columnas EDI vacias) + conceptos de CFDI
# SALE  : las mismas compras, con las columnas EDI llenas donde se encontro el CFDI
#
# Lo que hay que respetar al replicarlo:
#   1. Dos pasadas: primero con serie, luego solo numeros sobre lo que sobro.
#   2. Solo rellenar celdas vacias.
#   3. Descartar las llaves con valores en conflicto.
#   4. Copiar los impuestos del CFDI, no despejarlos del total.
#
# SIGUE -> 02_calculo_auditado.py
