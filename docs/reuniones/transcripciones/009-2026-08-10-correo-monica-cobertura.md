# Transcripción — Correo de Mónica (2026-08-10)

> Respaldo sin editar del correo original. La nota analizada está en
> [../009-2026-08-10-enfoque-cobertura-90-monica.md](../009-2026-08-10-enfoque-cobertura-90-monica.md).

---

Buen dia Oscar, espero que te encuentres muy bien.

El motivo de este correo es compartirte una actualización respecto a la actividad de descarga
de información de CPA Vision para el proyecto de COSTOS.

En el archivo adjunto se incluye el porcentaje de población actual de EDI (factura electrónica),
utilizando la información inicialmente proporcionada por el cliente. Derivado de la última
llamada de seguimiento que tuvimos relacionada con este proyecto, validamos con Héctor y
determinamos que requerimos enfocar los esfuerzos en aquellos proveedores y periodos que
presentan una cobertura inferior al 90%.

Por lo anterior, agradecemos tu apoyo para realizar la descarga de información únicamente de los
proveedores y periodos identificados con un porcentaje de población menor al 90%.

El archivo adjunto contempla los mismos 760 proveedores considerados en la planeación. En la
columna "acción" se indica cuáles requieren complementar la información mediante descarga de
CPA Vision y cuáles pueden ejecutarse directamente al contar con una cobertura suficiente.

La información que descarguemos de ahora en adelante la vamos a compartir con el depto. de data
services.

Asimismo, solicito tu apoyo para llevar un control del beneficio obtenido al complementar la
información mediante las descargas de CPA Vision. En el ejemplo adjunto se muestra el porcentaje
de mejora calculado a nivel consolidado del periodo 2020-2024; sin embargo, agradeceríamos que
este indicador pudiera generarse de forma desagregada por año, con el fin de medir con mayor
precisión el incremento en la cobertura de información y el impacto de las descargas realizadas.

Ruta del archivo:
"X:\Soriana\00 - AUDITORIA 2020 - 2024\00 - Auditores\Oscar\Proyectos Python\Automation-Costos\Planeacion vs %EDI poblado Soriana.xlsx"

---

## Notas de Óscar sobre organización de carpetas (contexto del chat)

- Las descargas de CPA se están pegando también en:
  "X:\Soriana\00 - AUDITORIA 2020 - 2024\Proceso Validación de condiciones (Oscar Pineda)\cpa_vision"
- Decisión: mantener `outputs/cpa_vision/parquet` como **única fuente de verdad** y **copiar**
  a esa ruta compartida; no fragmentar el parquet.
- Los proveedores ya descargados que quedaron ≥90% **no se eliminan**.

## Confirmaciones de Óscar (respuestas a las 2 preguntas de planeación)

1. El `%` del archivo es el estado **inicial** de la base, **sin** el cruce CPA.
2. Se mantiene la misma prioridad (mayor a menor compra, TOP, Perla), acotada a las 416 filas.
