-- =============================================================================
-- MODELO 3 (mart) — El Consolidado de la Validacion de Condiciones
-- Equivalente real: automation_costos/validation_exporter.py
-- =============================================================================
--
-- Un modelo MART es el que consume el negocio. Esta es, columna por columna, la
-- hoja "Consolidado" del entregable: una fila por folio con diferencia.
--
-- Es tambien la tabla contra la que filtramos los Compras de ARCA: los 75,717
-- folios salieron justo de un SELECT como este.

{{ config(materialized='table') }}

with renglones as (

    select * from {{ ref('int_costo_auditado') }}

),

por_folio as (

    select
        folio,
        proveedor,
        tienda,
        nota_entrada,
        min(factura)        as factura,
        min(fecha_recibo)   as fecha_recibo,

        -- Ya venia calculado como window function; aqui basta con tomarlo.
        max(debio_pagar_nota) as debio_pagar,
        max(total_pagado_nota) as total_pagado,

        count(*)            as renglones

    from renglones
    group by folio, proveedor, tienda, nota_entrada

)

select
    *,
    total_pagado - debio_pagar as diferencia

from por_folio

-- EL UMBRAL. Solo entra al entregable lo que supera 1 peso.
--
-- Este numero es `config.VALIDATION_DIFFERENCE_THRESHOLD` y es EL pendiente abierto
-- con negocio (ver docs/ESTADO_ACTUAL.md): para proveedores grandes deja pasar mucho
-- centavo de redondeo. En dbt seria una variable del proyecto, no un literal:
--
--     where total_pagado - debio_pagar > {{ var('umbral_diferencia') }}
--
-- ...y cambiarlo seria una linea en dbt_project.yml, con el cambio versionado en git
-- y visible en el diff. Hoy hay que tocar config.py.
where total_pagado - debio_pagar > 1.0
