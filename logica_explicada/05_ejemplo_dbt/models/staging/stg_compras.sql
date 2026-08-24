-- =============================================================================
-- MODELO 1 (staging) — Compras de Soriana, limpias y con folio
-- Equivalente real: automation_costos/calculations.py :: add_derived_base_columns
-- =============================================================================
--
-- Un modelo de STAGING no aplica reglas de negocio. Solo: renombra, castea, y arma
-- las llaves. La regla vive mas adelante, en `int_costo_auditado`.
--
-- `config()` le dice a dbt COMO materializar esto. Aqui es vista: se recalcula sola
-- y no ocupa disco. `int_costo_auditado` en cambio si sera tabla, porque es caro.

{{ config(materialized='view') }}

with origen as (

    -- `source()` apunta a una tabla declarada en sources.yml. La diferencia contra
    -- escribir el nombre a pelo es que dbt sabe de donde viene el dato y lo dibuja
    -- en el linaje.
    select * from {{ source('soriana', 'compras') }}

),

limpio as (

    select
        cast(vndnbr as varchar(20))     as proveedor,
        cast(strnbr as varchar(10))     as tienda,
        cast(rcvnbr as varchar(20))     as nota_entrada,
        cast(invnbr as varchar(40))     as factura,
        cast(codbarra as varchar(20))   as codigo_barras,
        cast(rcvdt as date)             as fecha_recibo,

        -- cantidad y costo del sistema (SAP)
        cast(can_rec as decimal(18,4))     as cantidad_recibida,
        cast(ctouni as decimal(18,6))      as costo_unitario_sistema,

        -- tasas de impuesto del sistema
        cast(iva_t007s as decimal(9,6))    as iva_sistema,
        cast(ieps_t007s as decimal(9,6))   as ieps_sistema,

        -- lo que ya venia del EDI en origen (puede venir vacio: lo llena el cruce)
        cast(ctonto_edi as decimal(18,6))  as costo_unitario_facturado,
        cast(poriva_edi as decimal(9,6))   as iva_facturado,
        cast(prieps_edi as decimal(9,6))   as ieps_facturado,
        cast(uuid as varchar(40))          as uuid_cfdi,

        cast(tot_pagado_ne as decimal(18,4)) as total_pagado_nota

    from origen
    -- Solo renglones AUDITABLES: los que traen nota de entrada.
    -- Ver docs/LOGICA_NEGOCIO.md 5.1
    where rcvnbr is not null

)

select
    *,

    -- EL FOLIO: la llave de toda la auditoria.
    --   '11004' + tienda a 4 digitos + nota a 8 digitos
    -- Equivalente real: automation_costos/utils.py :: make_folio
    -- Es la misma llave con la que filtramos los Compras de ARCA.
    '11004'
        + right('0000' + tienda, 4)
        + right('00000000' + nota_entrada, 8)   as folio

from limpio
