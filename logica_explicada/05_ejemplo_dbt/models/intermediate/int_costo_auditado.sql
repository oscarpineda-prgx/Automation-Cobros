-- =============================================================================
-- MODELO 2 (intermediate) — EL CORAZON: el costo auditado y lo que se debio pagar
-- Equivalente real: automation_costos/calculations.py :: recalculate_dataframe
-- =============================================================================
--
-- Este es el modelo que justifica todo el ejercicio. Aqui vive LA REGLA. Fijate en
-- tres cosas mientras lo lees:
--
--   1. Es un SELECT. No hay CREATE, no hay INSERT, no hay orden de ejecucion escrito
--      en ningun lado. dbt lo deduce del `ref()` de abajo.
--   2. Esta materializado como TABLA, porque es caro y lo consultan varios modelos.
--      Cambiar 'table' por 'view' es la unica edicion necesaria para cambiar eso.
--   3. La regla queda en UN lugar. Hoy vive en Python y se replica a mano en las
--      guias para Data Services; aqui seria una sola definicion.

{{ config(materialized='table') }}

with compras as (

    -- `ref()` = "el modelo stg_compras". Esto y solo esto es lo que le dice a dbt
    -- que stg_compras va ANTES que este modelo.
    select * from {{ ref('stg_compras') }}

),

marcado as (

    select
        *,

        -- ¿ESTE RENGLON CRUZO CON UN CFDI?
        -- Se detecta por PRESENCIA, no por valor distinto de cero: un CFDI puede
        -- traer IVA/IEPS = 0 legitimamente (producto exento) y ese 0 debe respetarse.
        -- Acuerdo con Monica/Perla, reunion 2026-07-31.
        case
            when uuid_cfdi is not null or costo_unitario_facturado is not null
            then 1 else 0
        end as cruzo_cpa

    from compras

),

auditado as (

    select
        *,

        -- COSTO AUDITADO: el menor de los dos, pero nunca cero.
        -- Si cruzo y el costo del CFDI es valido (>0) y menor al del sistema, gana
        -- el del CFDI. En cualquier otro caso, el del sistema.
        case
            when cruzo_cpa = 1
             and costo_unitario_facturado > 0
             and costo_unitario_facturado < costo_unitario_sistema
            then costo_unitario_facturado
            else costo_unitario_sistema
        end as cto_aud,

        -- IMPUESTOS AUDITADOS: si cruzo, mandan los del CFDI (aunque sean 0).
        case when cruzo_cpa = 1 then iva_facturado  else iva_sistema  end as iva_aud,
        case when cruzo_cpa = 1 then ieps_facturado else ieps_sistema end as ieps_aud

    from marcado

)

select
    *,

    -- IMPORTE AUDITADO del renglon: costo x cantidad, con impuestos compuestos.
    -- Ojo: los impuestos se MULTIPLICAN encadenados, no se suman.
    cto_aud
        * cantidad_recibida
        * (1 + iva_aud)
        * (1 + ieps_aud)                                    as imp_aud,

    -- LO QUE SE DEBIO PAGAR POR LA NOTA COMPLETA.
    -- La diferencia se reclama por nota de entrada, no por renglon, asi que el
    -- importe auditado se suma sobre todos los renglones del mismo folio.
    sum(
        cto_aud * cantidad_recibida * (1 + iva_aud) * (1 + ieps_aud)
    ) over (partition by folio)                             as debio_pagar_nota

from auditado
