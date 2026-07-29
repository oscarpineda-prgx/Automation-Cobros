# Bitácora del proyecto

> Registro fechado de cada cambio de código y cada decisión de lógica.
> Entradas más recientes arriba. **La fecha y hora siempre se generan con Python**, nunca
> se escriben a mano:
>
> ```bash
> python scripts/log_cambio.py --tipo codigo --titulo "..." --detalle "..." --archivos a.py b.py
> ```
>
> Tipos: `codigo` · `decision` · `reunion` · `dato` · `bug`

<!-- NUEVAS ENTRADAS ARRIBA -->

### 2026-07-29 08:02:42 — [DECISIÓN] Entregables van a la carpeta de auditores; outputs/ del proyecto solo guarda cpa_vision

El share X:/Soriana se lleno (cuota) porque los entregables quedaban DUPLICADOS: en outputs/ del proyecto y en la carpeta de auditores donde Oscar los pega para el equipo: 'X:/Soriana/00 - AUDITORIA 2020 - 2024/Proceso Validacion de condiciones (Oscar Pineda)'. DECISION de Oscar (2026-07-29): generar los entregables DIRECTO en la carpeta de auditores (con --output-dir a esa ruta) y NO duplicar en el proyecto. Se BORRARON del proyecto outputs/ las 6 carpetas de proveedor (391250 Arca, 76034 Pepsico, 73692 Celaya, 5462 Nestle, 741 Selecta, 80622 3M) tras verificar que la carpeta de auditores ya las tiene completas; libero ~12.6GB (outputs/ de 17GB a 4.4GB). Se CONSERVA outputs/cpa_vision (4.4GB: ZIPs descargados + dataset Parquet) porque es la materia prima de todos los cruces y NO esta en la carpeta de auditores. De aqui en adelante: cruces/datos en el proyecto (outputs/cpa_vision), entregables (Compras/Validacion/soportes) en la carpeta de auditores via --output-dir. Las descargas de CPA Vision siguen a outputs/cpa_vision (--download-dir). HALLAZGO del dia: de los 59 prioritarios del master (col X), solo 6 tienen CPA descargada y son exactamente los 6 urgentes; 53 pendientes. Se armo descarga_prioritarios_lote1.xlsx con los primeros 10 pendientes (RFC+FECHAS) para el comando cpa-batch-vendors. Ademas: Arca ya tiene sus 24 Compras (Oscar corrio cpa-compras-grande hoy, funciono y fue resumible).

**Archivos:** `descarga_prioritarios_lote1.xlsx`, `docs/ESTADO_ACTUAL.md`

---

### 2026-07-28 09:15:54 — [CÓDIGO] Subcomando cpa-compras-grande: Compras de gigantes por trimestre/mes, resumible

Oscar pidio generar SOLO los archivos de Compras pendientes de los gigantes (Arca 2022-2025; ya tenia 2020-2021 de un intento anterior) por comando en terminal, sin re-hacer lo ya hecho, por trimestre (o mes). Nuevo pipeline_streaming.generar_compras_grande: UNA pasada por intervalo, trae el intervalo COMPLETO (todos los renglones, no solo auditables — el Compras es referencia completa), cruza con CPA (ya filtrada por factura, lo que lo hace caber), y escribe Compras_<base>_<etiqueta>.xlsx. RESUMIBLE: resuelve el base desde la carpeta existente y SALTA los intervalos cuyo archivo ya existe, sin re-consultar SQL (no se pierde el trabajo hecho). NO escribe Validacion -> no acumula nada -> pico acotado a un intervalo (~5.5GB un trimestre de Arca). Soporta --por-mes (nuevo _intervalos_mes, 72 meses) para proveedores donde un trimestre no quepa (Pepsico si hace falta). Nota: los totales por folio del Compras quedan POR INTERVALO (para los ~0.3% de folios que cruzan intervalo difieren del global; el numero exacto vive en la Validacion, que si es global). Subcomando main.py cpa-compras-grande --vendor --start --end --parquet --output-dir [--por-mes]. VERIFICADO en Selecta: genera por trimestre y en un 2do run salta los existentes. Arca tiene 8 Compras (2020-2021) + Validacion + soporte; el comando generara 2022-2025 (16 trimestres). Comando Arca: python main.py cpa-compras-grande --vendor 391250 --start 2020-01-01 --end 2025-12-31 --parquet outputs/cpa_vision/parquet --output-dir outputs

**Archivos:** `automation_cobros/pipeline_streaming.py`, `main.py`

---

### 2026-07-27 19:33:13 — [DATO] Pepsico entregado: los 6 urgentes cerrados

Pepsico (76034) Validacion generada con el filtro por factura: 446,489 folios auditables, 123,742 con diferencia > 1 peso (27.7%), monto total 160,600,953.85, Detalle 1,917,582 renglones en 2 hojas (completo), soporte 619617 (el request completo, no el duplicado). RAM estable ~3GB, sin OOM. Con esto los 6 urgentes estan listos: Selecta, Celaya, Nestle, 3M (Compras+Validacion) y Arca (157,433 folios, 170.6M) + Pepsico (123,742 folios, 160.6M) con Validacion (los 2 gigantes por el camino ligero, sin Compras por decision de Oscar 'Validacion primero'). PENDIENTE con negocio: validar si el ~28-38% de diferencias y los montos (~160-170M cada uno) son reales o si el umbral de 1 peso necesita ajuste (Monica/Luis).

**Archivos:** `outputs`

---

### 2026-07-27 18:05:05 — [CÓDIGO] cargar_cpa filtra tambien por factura + Detalle en varias hojas + Arca entregado

Pepsico (16M de CPA) reventaba aun por trimestre: unos pocos codigos de barra matchean ~9GB de conceptos CPA y la memoria no se liberaba entre trimestres. FIX: cargar_cpa acepta facturas=(series_folios, folios) y filtra la CPA a las facturas presentes en el lote, con las DOS llaves del cruce (serie+folio normalizado y solo digitos, con OR) replicadas en SQL. pipeline_streaming._salida_intervalo calcula esas llaves de raw.invnbr y las pasa. RESULTADO: Pepsico 3 trimestres seguidos pico 2.7GB (antes 9), sin OOM. SEGURIDAD VERIFICADA: el filtro solo quita conceptos de CPA cuya factura NO esta en las compras (no podian cruzar); Selecta con filtro vs sin filtro da Validacion IDENTICA (Consolidado 188/188, Detalle 1119/1119, 0 columnas difieren). Otros fixes de esta vuelta: (1) validation_exporter._dump_tabla parte el Detalle en varias hojas cuando pasa de 1,048,576 (antes se truncaba en silencio; Arca tenia 4.29M de detalle). (2) subcomando main.py cpa-validacion-grande y scripts/correr_validaciones_grandes.py corre cada proveedor en PROCESO PROPIO (memoria limpia). ARCA ENTREGADO: Validacion 510MB, Consolidado 157,433 folios con diferencia, monto total 170,642,809.25, Detalle 4,296,801 renglones en 5 hojas, soporte copiado. Pepsico corriendo con el filtro (RAM 2.9GB). Pendiente negocio: validar con Monica/Luis si el ~40% de diferencias / el monto es real o si el umbral de 1 peso necesita ajuste.

**Archivos:** `automation_cobros/cruce_cpa.py`, `automation_cobros/pipeline_streaming.py`, `automation_cobros/validation_exporter.py`, `main.py`, `scripts/correr_validaciones_grandes.py`

---

### 2026-07-27 13:50:15 — [CÓDIGO] Validacion de gigantes: camino ligero (Validacion-solo, filtrado y motor rapido)

Arca (11.5M) y Pepsico (10.1M) fallaban aun por trimestre: el pipeline acumulaba en RAM las filas con diferencia para la Validacion final y reventaba al cargar la CPA del siguiente (ArrowMemoryError en cargar_cpa). Ademas se midio que Arca marca 3.7%-42.6% de diferencias por trimestre (muchos hallazgos reales donde el CFDI < sistema), asi que openpyxl no aguanta el volumen. Oscar pidio analizar que se puede FILTRAR y priorizar la Validacion. Analisis: (1) los ~3.5M renglones 'sin fecha' son en realidad SIN NOTA DE ENTRADA (rcvnbr nulo, ~30%): no auditables a nivel folio, caen en un folio degenerado que nunca se marca -> excluirlos NO cambia la Validacion (verificado). (2) la Validacion solo usa ~31 de las 105 columnas. Solucion: nuevo pipeline_streaming.generar_validacion_grande - UNA pasada por trimestre trayendo solo auditables (fetch_compras ahora acepta filtro_filas='rcvnbr IS NOT NULL'), cruza, prepara, se queda con las columnas fuente, acumula debio/pagado por folio GLOBAL y vuelca a disco (pickle por trimestre, no acumula en RAM); al final filtra folios con diferencia, pega totales globales y escribe con motor RAPIDO. Nuevo validation_exporter.write_validation_rapida (xlsxwriter en streaming) + build_detalle_rapido (vectorizado, sin iterrows) que aguantan millones de renglones. cruzar() ahora soporta en_sitio y cargar_cpa limita la memoria de DuckDB (memory_limit 4GB + spill). NO escribe el Compras (Validacion primero, decision de Oscar). VERIFICADO IDENTICO al camino normal: Selecta 2020-2025 por generar_validacion_grande da Consolidado 188 y Detalle 1119, 0 diferencias. Arca y Pepsico corriendo por scripts/correr_validaciones_grandes.py: pico RAM 4.5GB, ~2.5 min/trimestre.

**Archivos:** `automation_cobros/pipeline_streaming.py`, `automation_cobros/validation_exporter.py`, `automation_cobros/database.py`, `automation_cobros/cruce_cpa.py`, `scripts/correr_validaciones_grandes.py`

---

### 2026-07-27 09:21:44 — [CÓDIGO] Proveedores gigantes: procesamiento por TRIMESTRE (un año no cabe en RAM)

Al correr Arca/Pepsico por el camino por año fallaron con MemoryError: un año completo (Arca 2025: 1.6M compras + 2.9M conceptos de CPA -230 codigos de barra pero matchean 2.9M filas-) sube a 12GB y no cabe en los ~13GB libres. Tres cambios: (1) cruzar() ahora acepta en_sitio=True y el pipeline por intervalos lo usa: no copia el df del intervalo (ahorra ~5GB en un año). (2) cargar_cpa limita la memoria de DuckDB (memory_limit 4GB + temp_directory) para que use disco al materializar los millones de conceptos de CPA en vez de reventar. (3) LO PRINCIPAL: pipeline_streaming ahora procesa por TRIMESTRE, no por año (decision de Oscar: Compras por trimestre + Validacion consolidada). Nuevo _intervalos_trimestre (24 trimestres para 2020-2025); _Anio->_Intervalo, _salida_anio->_salida_intervalo; escribe un Compras_<base>_<año>-T<n>.xlsx por trimestre (~24 por proveedor) reusando escribir_libro_compras (con su Pendientes_EDI); la Validacion sigue consolidada en 1 archivo (agregacion global por folio/factura a traves de todos los trimestres). MEDIDO: un trimestre de Arca (2025-T4, 421,151 renglones) pico 5.5GB, 193s -> cabe holgado. VALIDADO que con trimestres el resultado es IDENTICO al camino normal: Selecta 2020-2025 (58,558 filas, 0 columnas difieren, Validacion 188/1119 identica). Se agrego gc.collect() entre trimestres. gan y Pepsico relanzados por scripts/correr_grandes_pendientes.ps1 (ya con trimestres).

**Archivos:** `automation_cobros/pipeline_streaming.py`, `automation_cobros/cruce_cpa.py`, `automation_cobros/pipeline.py`

---

### 2026-07-26 21:23:39 — [CÓDIGO] Pipeline por año (streaming) para proveedores que no caben en memoria

Arca (11.5M renglones) y Pepsico (10.1M) morian con MemoryError en fetch_compras: el DataFrame completo no cabe en 24GB (Celaya 1.24M ya usaba 13GB). Solucion pedida por Oscar: NO tocar la funcion SQL F_COMPRAS; procesar por intervalos (año por año) y consolidar. Nuevo modulo automation_cobros/pipeline_streaming.py (generar_salida_proveedor_por_anios) en DOS PASADAS: (1) por año llama F_COMPRAS(vendor, año-01-01, año-12-31) tal cual, cruza con CPA, prepara, y acumula por folio (nota de entrada) y por factura: suma de imp_aud (debio pagar), suma de impaud display (dpagar), max de tot_pagado_ne/tot_pagado_inv (pagado); descarta los renglones. (2) totales GLOBALES por folio/factura (asi los ~0.3% de folios que cruzan un año salen exactos). (3) re-cruza cada año, pega los totales globales y escribe Compras_<base>_<año>.xlsx. (4) junta solo las filas de folios con diferencia y reusa write_validation_from_dataframe -> UNA sola Validacion. Pico de memoria acotado a un año (~1.4M). generar_salida_proveedor ahora es un dispatcher: hace un COUNT barato (nueva database.contar_compras) y si supera MAX_FILAS_EN_MEMORIA=2.5M usa el camino por año, si no el normal (_generar_salida_en_memoria, intacto). Nuevo excel_exporter.escribir_libro_compras (publico) para escribir un df ya preparado. ResultadoPipeline.cruce ahora opcional (None en el camino por año). HALLAZGO clave: los 3.5M 'sin fecha' de Arca son en realidad 'sin nota de entrada' (rcvnbr nulo); entre folios reales solo 0.28% cruzan año. VALIDADO que el camino por año da resultados IDENTICOS al normal: Selecta 2020-2025 (58,558 filas, 0 columnas difieren, Validacion 188/1119 identica) y Nestle 2020-2021 (266,478 filas con folios que cruzan año, 0 difieren, Validacion 7410/114255 identica); mas test unitario de la suma por folio que cruza año. Arca y Pepsico lanzados por scripts/correr_grandes_pendientes.ps1.

**Archivos:** `automation_cobros/pipeline_streaming.py`, `automation_cobros/pipeline.py`, `automation_cobros/database.py`, `automation_cobros/excel_exporter.py`, `scripts/correr_grandes_pendientes.ps1`

---

### 2026-07-25 15:37:00 — [CÓDIGO] Compras de proveedores grandes: un archivo por año (>1M filas)

Oscar pidio que los proveedores muy grandes (Arca, Pepsico) generen varios archivos de Compras en vez de uno gigante (Celaya quedo en 682MB). Decidido: un ARCHIVO POR AÑO, y solo para los grandes; los chicos siguen en un solo archivo con hojas por año. Implementado en excel_exporter.write_compras_files (nueva funcion orquestadora): si len<=UMBRAL_PARTIR_POR_ANIO (1,000,000 filas) escribe un solo Compras_<base>.xlsx; si es mayor, escribe Compras_<base>_2020.xlsx, _2021.xlsx, ... cada uno con su Compras <año> y su propio Pendientes_EDI de ese año. Se corta en limites de año (via _grupos_por_anio), asi una nota de entrada nunca queda partida entre archivos y no se afecta ningun calculo. Se refactorizo write_compras_workbook: _preparar_para_escritura (prepare + apply_display_formula_values + reorden) y _escribir_libro (abre el xlsx con use_zip64 y escribe hojas+pendientes, borra el archivo si algo falla); write_compras_workbook (usado por recalc y proveedores chicos) y write_compras_files comparten estos helpers. LA VALIDACION SIGUE SIENDO UN SOLO ARCHIVO (es el entregable real, chica, se arma del DataFrame en memoria). ResultadoPipeline ahora expone compras_paths (lista); compras_path queda como el primero para la GUI. main.py imprime todos los archivos. VERIFICADO en datos reales (Selecta, umbral forzado a 10k): 6 archivos por año que suman 58,558 filas exactas, cada uno con su Pendientes_EDI; Validacion IDENTICA a la entregada (0 columnas difieren, 188/1119 filas); read_compras_workbook relee un archivo-año OK (23,637 filas, 105 cols). Caso chico: 1 archivo. La particion nocturna de Arca/Pepsico se activara sola. Selecta y Celaya NO se tocan.

**Archivos:** `automation_cobros/excel_exporter.py`, `automation_cobros/pipeline.py`, `main.py`

---

### 2026-07-24 17:00:22 — [CÓDIGO] Script correr_urgentes.ps1 para lote nocturno de proveedores

Se creo scripts/correr_urgentes.ps1 que corre por cpa-salida los 4 urgentes restantes uno tras otro, ordenados de menor a mayor: 80622 3M (solo 2025), 5462 Nestle, 391250 Arca, 76034 Pepsico. Cada proveedor es independiente: si uno falla se registra y sigue con el siguiente (ErrorActionPreference Continue, se captura LASTEXITCODE). Genera un log por proveedor en outputs/logs/<vendor>_<stamp>.log y un resumen urgentes_<stamp>.resumen.txt con estado y duracion. Usa el python del venv y PYTHONIOENCODING=utf-8. Verificado contra el Parquet (regla 4.4) que los 4 RFC estan: Pepsico CPM110719SG3 15.96M filas 2 req, Nestle MNE0409226K9 1.33M 2 req, Arca DJB850527F30 7.85M 1 req, 3M TMM720509PYA 25,555 solo 2025. Sintaxis PowerShell validada. RIESGO documentado: Arca y sobre todo Pepsico son los mas pesados en memoria (Celaya 1.24M compras uso 13.4GB de 24GB); si alguno se queda sin memoria el log lo mostrara y los demas terminan igual.

**Archivos:** `scripts/correr_urgentes.ps1`

---

### 2026-07-24 16:53:54 — [CÓDIGO] Compras: una hoja por año (rcvdt) en vez de por tope de filas

Oscar pidio que el Compras agrupe las hojas por AÑO (2020, 2021, ...) segun rcvdt, en vez del corte por tope de filas. Cambios: (1) excel_exporter._write_compras_sheets ahora agrupa por año de rcvdt y nombra las hojas 'Compras 2020', 'Compras 2021', ...; si un año rebasa el tope de Excel se parte en 'Compras 2020 (2)', (3)... El agrupado es SOLO presentacion: reordena en que hoja cae cada renglon, no cambia ningun valor calculado (todo viene precalculado por renglon y por grupo). (2) Nueva _anio_agrupacion: las filas sin fecha (NaT) NO van a una hoja aparte; heredan el año de su mismo grupo, en orden nota de entrada (concaten) -> factura (invnbr) -> vecino en el orden original (ffill/bfill). Asi ninguna se pierde ni se aisla. (3) BUG LATENTE ARREGLADO: read_compras_workbook (recalculate.py) y leer_compras (cruce_cpa.py) leian solo la hoja 'Compras', perdiendo las filas de las hojas de continuacion; ahora leen TODAS las hojas 'Compras*' y concatenan. Ese bug NO afecto los entregables de Selecta/Celaya porque el pipeline arma Compras y Validacion desde el DataFrame en memoria (write_validation_from_dataframe), nunca releyendo el archivo; VERIFICADO: la Validacion de Celaya cubre los 6 años con 35,762 filas de 2025 que viven en la 2a hoja del Compras. VERIFICACION del cambio con Selecta real a directorio temporal: Compras con 6 hojas por año (2020..2025) suman 58,558 renglones sin perder ninguno, NaT repartidos; Validacion IDENTICA a la entregada (0 columnas difieren, mismas 188/1119 filas), probando que no afecta calculos; leer_compras recupera las 58,558 filas y el RFC. Selecta y Celaya NO se regeneraron: sus archivos actuales quedan como estan (Oscar lo pidio explicitamente). El cambio aplica de ahora en adelante.

**Archivos:** `automation_cobros/excel_exporter.py`, `automation_cobros/recalculate.py`, `automation_cobros/cruce_cpa.py`

---

### 2026-07-24 15:43:05 — [CÓDIGO] Soporte CPA Vision: una sola descarga por proveedor, sin duplicar

Oscar pidio que si un proveedor se descargo dos veces, la carpeta de soportes NO tenga la informacion duplicada sino un solo request_id. Se reemplazo request_ids_de_rfc (que devolvia el conjunto deduplicado por año y en teoria podia dar mas de un request) por request_id_principal, que elige UNA sola descarga: la de mayor cobertura (mas años distintos y, a igualdad, mas filas). Nueva dataclass SoporteRequest(principal, anios_principal, anios_totales, redundantes, cobertura_completa). copiar_soportes_cpa ahora copia solo el ZIP del request principal (incluidas sus partes _1.zip/_2.zip, que son una sola descarga en pedazos, no duplicado), avisa por log las descargas redundantes ignoradas, y lanza un AVISO fuerte si el principal no cubriera todos los años (caso que hoy no ocurre; nunca descarta años en silencio). VERIFICADO con los 2 proveedores que se bajaron dos veces: Pepsico CPM110719SG3 principal=619617 (6 años) ignora 619939 (solo 2025); Nestle MNE0409226K9 principal=618728 ignora 620512; ambos cobertura_completa=True. Prueba funcional: aunque en cpa_vision/ existen los dos ZIP de Pepsico, en la carpeta de soportes cae uno solo (619617, 380MB), cero de 619939. Selecta y Celaya sin cambio (un solo request). Compila e importa OK.

**Archivos:** `automation_cobros/cruce_cpa.py`, `automation_cobros/pipeline.py`

---

### 2026-07-24 15:26:17 — [CÓDIGO] Salida por proveedor en carpeta propia + copia de soportes ZIP de CPA Vision

Oscar pidio estandarizar la salida: una carpeta por proveedor con formato numero_nombre y dentro una subcarpeta 'cpa vision soportes' con los ZIP de CPA Vision que respaldan el entregable. (1) generar_salida_proveedor ahora crea output_dir/<numero>_<nombre>/ y escribe ahi el Compras y la Validacion (antes planos en output_dir); la GUI y el CLI solo usan las rutas que devuelve, no se rompe nada. (2) Nueva funcion copiar_soportes_cpa en pipeline.py: copia (no mueve) a la subcarpeta los ZIP cuyos request_id alimentaron el cruce; es idempotente (si el ZIP ya esta con el mismo tamaño no recopia) y NO fatal (si falta el ZIP o hay error de permisos/disco avisa y sigue, el entregable ya esta escrito). (3) La correspondencia dato<->soporte es exacta: se extrajo el CTE de deduplicacion de cargar_cpa a la constante compartida _CTE_ELEGIDO y se agrego request_ids_de_rfc(rfc, parquet) que reusa esa misma logica; asi para Pepsico/Nestle (que tienen 2 request cada uno, uno de solo-2025 que se descarta) copia SOLO el request que se uso -verificado: CPM110719SG3->619617, MNE0409226K9->618728, no los descartados-. (4) ResultadoPipeline ahora expone proveedor_dir y soportes; el CLI imprime la carpeta y cuantos ZIP. Constante SUBCARPETA_SOPORTES='cpa vision soportes' (con espacios, como se acordo nombrarla). MANUAL: se copiaron ya los ZIP de los 2 urgentes listos: Selecta 741 (641815, 992KB) y Celaya 73692 (641727, 33MB), verificados por sha256 identicos al original en outputs/cpa_vision. Compila e importa OK (incluida la GUI).

**Archivos:** `automation_cobros/pipeline.py`, `automation_cobros/cruce_cpa.py`, `main.py`

---

### 2026-07-24 14:26:14 — [DATO] Celaya (73692) generado completo: Compras 682 MB en 2 hojas, 1,244,498 renglones

Con los tres fixes (memoria en_sitio, use_zip64, vectorizacion) el proveedor que reventaba salio completo. Compras_73692 = 682 MB, tres hojas: Compras (1,048,569 filas, el tope de Excel), Compras (2) (195,929 filas, el resto) y Pendientes_EDI (385,554). Total 1,244,498 renglones, cuadra al renglon con lo que trajo SQL; RFC ECE830923MJ2 en A8. Esto confirma el requisito original de Oscar: proveedor grande partido en varias hojas sin perder renglones. Validacion 41.5 MB (Consolidado 26,326 folios, Detalle 322,294 filas). Tiempos aprox: SQL+cruce 6 min, Validacion 14 min (openpyxl con 322k filas de detalle es el paso lento ahora), Compras 26 min. Memoria pico ~13 GB, estable. NOTA para negocio: el Consolidado de Celaya tiene 26k folios pero la mediana de diferencia es 6.86 pesos y el Q1 es 2.48 -> casi todo son centavos de redondeo; el umbral VALIDATION_DIFFERENCE_THRESHOLD=1 peso deja pasar demasiado en proveedores grandes. Decision de umbral pendiente con Oscar/Monica, documentada en ESTADO_ACTUAL.md.

**Archivos:** `outputs`

---

### 2026-07-24 12:55:15 — [DECISIÓN] R25: de SORIANA_2025_PROJECTS solo se toma 2025 (sus años previos estan incompletos)

Oscar aclaro que la informacion anterior a 2025 que devuelve SORIANA_2025_PROJECTS NO es del todo correcta: en ocasiones esta incompleta. Instruccion explicita: de esa base solo se toma 2025, y de SORIANA_PROJECTS todo el resto del periodo. Esto es exactamente lo que ya hacia FUENTES_COMPRAS en database.py, asi que NO hubo cambio funcional; lo que faltaba era dejar constancia del porque para que nadie amplie esos rangos creyendo que corrige algo. Se documento como regla R25 en LOGICA_NEGOCIO.md, con advertencia en el comentario de FUENTES_COMPRAS, en PLANEACION.md y en ESTADO_ACTUAL.md. El riesgo de ampliar el rango no es solo duplicar renglones (Selecta mostro 2022/2023/2024 con conteos identicos en ambas bases): es meter datos parciales en la auditoria.

**Archivos:** `automation_cobros/database.py`, `docs/LOGICA_NEGOCIO.md`, `docs/PLANEACION.md`, `docs/ESTADO_ACTUAL.md`

---

### 2026-07-24 12:44:20 — [DATO] SORIANA_2025_PROJECTS no contiene solo 2025

Al verificar Selecta 741 se encontro que la base SORIANA_2025_PROJECTS tambien trae 2022, 2023 y 2024, con los MISMOS conteos que SORIANA_PROJECTS (3570, 5443, 5572). Hoy no hay duplicacion porque fetch_compras recorta el periodo pedido contra el rango de años de cada fuente (FUENTES_COMPRAS) y solo le pide 2025 a esa base, pero si alguien amplia ese rango se duplicarian los renglones en silencio. CONFIRMADO de paso que Selecta 741 esta completo 2020-2025: 21962+12726+3570+5443+5572 de 2020-2024 mas 3183 de 2025 mas 6102 con rcvdt nulo = 58,558 renglones, que es exactamente lo que tienen los archivos de outputs/.

**Archivos:** `automation_cobros/database.py`, `docs/PLANEACION.md`

---

### 2026-07-24 12:44:18 — [BUG] Compras de proveedor gigante: ZIP64 obligatorio en xlsxwriter

Con el problema de memoria ya resuelto, Celaya llego hasta el cierre del libro y ahi murio con zipfile.LargeZipFile / xlsxwriter FileSizeError: 'Filesize would require ZIP64 extensions'. Un .xlsx es un ZIP y el de 1.24M filas x 105 columnas rebasa los limites del ZIP clasico. Fix: Workbook(..., {'constant_memory': True, 'use_zip64': True}) en excel_exporter.write_compras_workbook. Ademas, si la escritura falla ahora se borra el .xlsx trunco en vez de dejar un archivo de 1 KB que parece una salida buena. Verificado que use_zip64 no altera la salida de archivos normales (zipfile solo activa las extensiones cuando hacen falta).

**Archivos:** `automation_cobros/excel_exporter.py`

---

### 2026-07-24 12:43:49 — [CÓDIGO] Memoria del pipeline: proveedores de mas de un millon de renglones

Empacadora Celaya (73692, 1,244,498 renglones) reventaba con numpy ArrayMemoryError en prepare_compras_dataframe. Causa: la cadena de preparacion hacia CINCO copias completas encadenadas del DataFrame (prepare -> recalculate -> add_derived_base_columns -> _recalculate_invoice_level -> apply_display_formula_values) mas tres en la Validacion, y arrastraba las columnas sobrantes de F_COMPRAS; con 1.24M filas x 105 columnas object cada copia son ~9 GB. Cambios: (1) parametro en_sitio=True en toda la cadena de calculations.py, una sola copia; (2) recorte de columnas sobrantes ANTES de calcular; (3) clean_code, make_folio y normalize_date_columns vectorizados en utils.py (clean_code_series, make_folio_series, _normalize_date_series) - eran bucles Python de 1.2M iteraciones que ademas construian listas de strings; (4) la Validacion copia solo sus 31 columnas fuente en vez de las 105, no recalcula folio tres veces, y prefiltra los folios que califican de forma vectorizada en vez de recorrer ~100k grupos en Python; (5) build_pending_edi_dataframe acumula la mascara columna a columna en vez de materializar df[EDI].astype(str); (6) fetch_compras lee con fetchmany en lotes de 100k en vez de fetchall; (7) el pipeline genera la Validacion ANTES del Compras - es el entregable real y es chica, asi sale aunque el Compras gigante falle. EQUIVALENCIA VERIFICADA: re-corrido Selecta 741 completo, el Compras salio identico celda a celda (58,558 x 105 columnas, 0 diferencias) y la Validacion tambien (Consolidado 188 filas, Detalle 1,119, todas las sumas iguales). Tambien se verificaron una a una clean_code_series vs clean_code, make_folio_series vs make_folio, normalize_date_columns vectorizado vs el apply escalar, la mascara de pendientes y el prefiltro de folios. Resultado en Celaya: memoria estable en 13.4 GB (antes reventaba), el pipeline llego hasta el final.

**Archivos:** `automation_cobros/calculations.py`, `automation_cobros/utils.py`, `automation_cobros/validation_exporter.py`, `automation_cobros/database.py`, `automation_cobros/pipeline.py`

---

### 2026-07-24 10:34:32 — [BUG] main.py: import perezoso de la GUI

run_app (customtkinter) se importaba en el tope de main.py, rompiendo TODOS los subcomandos de terminal si customtkinter no esta en el interprete usado. Se movio el import dentro de la rama gui, como los demas imports pesados. Ademas: el pipeline debe correrse con .venv/Scripts/python.exe (tiene xlsxwriter, duckdb, customtkinter); el Python global no. Re-ejecutado Selecta 741 completo 2020-2025: 58,558 filas (3,183 de 2025), 30.6% con CFDI, Consolidado 195 filas.

**Archivos:** `main.py`

---

### 2026-07-24 10:22:55 — [CÓDIGO] Compras 2025 desde SORIANA_2025_PROJECTS

F_COMPRAS esta partido por año en dos bases del mismo servidor: SORIANA_PROJECTS (2020-2024) y SORIANA_2025_PROJECTS (2025). fetch_compras() ahora recorta el periodo pedido contra el rango de cada fuente (FUENTES_COMPRAS) y concatena; un periodo 2020-2025 hace dos consultas, uno de un solo rango hace una. Verificado con Selecta 741: 2024=6949, 2025=3183, completo=58558 filas. Se levanta el bloqueo de REVISAR 2025.

**Archivos:** `automation_cobros/database.py`, `config.py`, `docs/PLANEACION.md`

---

### 2026-07-24 09:13:58 — [DATO] BLOQUEO: SQL Server no tiene compras de 2025; el periodo 2025 no se puede auditar aun

Al validar si Selecta (741) estaba completo segun la planeacion se descubrio que F_COMPRAS (SQL Server SORIANA_PROJECTS) solo tiene compras cargadas hasta 2024. Verificado: fetch_compras('741','2025-01-01','2025-12-31') = 0 renglones; 2024 = 6,949. El Compras/Validacion generado de Selecta cubre SOLO 2020-2024 (confirmado por las tres fechas podt/rcvdt/invdt, ninguna tiene 2025). Mismo patron ya visto en Nestle (enero 2025 daba 0). CONSECUENCIA: la parte REVISAR 2025 de la planeacion esta BLOQUEADA para todos los proveedores hasta que se carguen las compras de 2025 en SQL Server; aunque los CFDI de 2025 ya estan descargados en CPA Vision, no hay compras 2025 contra que cruzarlos. Selecta segun la planeacion NO esta completo: le falta 2025. Se puede avanzar todo lo de 2020-2024 mientras tanto. Documentado en docs/PLANEACION.md.

**Archivos:** `docs/PLANEACION.md`

---

### 2026-07-24 08:35:30 — [DATO] Guia en Word de la Validacion de Condiciones (Guia_Validacion_Condiciones.docx)

Oscar pidio un Word con tablas que explique como se calcula la Validacion de Condiciones. Se creo scripts/generar_guia_validacion.py que genera Guia_Validacion_Condiciones.docx en la raiz. Contiene 6 tablas: las 3 hojas del archivo, el filtro (que renglones entran: si el auditor clasifico concepto entran solo dif costos, si no entran los de dif_det_ne>1), hoja Resumen, hoja Consolidado (15 columnas con su origen: Total Pagado=max paynetamt por folio, Debio Pagar=suma imp_aud por folio, Diferencia=resta), hoja Detalle PAGOS (21 columnas), y el calculo de la diferencia en 4 pasos. HALLAZGO documentado como nota a verificar: en el Detalle la columna CtoUnitario_sistema se llena con ctonto_edi (costo del proveedor) y no con ctouni (costo del sistema); rotulo/origen a confirmar con Luis/Monica. El script es reproducible.

**Archivos:** `scripts/generar_guia_validacion.py`, `Guia_Validacion_Condiciones.docx`

---

### 2026-07-24 08:13:58 — [DATO] Guia de columnas en Word para el auditor (Guia_Columnas_Compras.docx)

Oscar pidio una tabla de referencia de las columnas principales con su origen y calculo, en Word. Se instalo python-docx y se creo scripts/generar_guia_columnas.py que genera Guia_Columnas_Compras.docx en la raiz. Contiene 5 tablas: (1) llave del cruce (invnbr<->Folio, codbarra<->noIdentificacion, vndnbr/RFC), (2) 8 columnas copiadas del CFDI, (3) factem_edi del propio Compras, (4) 2 columnas EDI calculadas (ctobto_edi, impart_edi), (5) 10 columnas de auditoria (cto_aud, iva_aud, ieps_aud, imp_aud, debio_pagar_ne, tot_pagado_ne, dif_det_ne, debio_pagar_inv, tot_pagado_inv, dif_det_inv) con su calculo y significado. Incluye leyenda de color por origen y nota de los dos niveles de agregacion (NE por nota de entrada, inv por factura, pagado con MAX no suma). El script es reproducible; la fuente son docs/MAPEO_CRUCE_CPA_COMPRAS.md, LOGICA_NEGOCIO.md y calculations.py.

**Archivos:** `scripts/generar_guia_columnas.py`, `Guia_Columnas_Compras.docx`

---

### 2026-07-24 07:14:40 — [CÓDIGO] Validacion de Condiciones alineada a la imagen corporativa del Compras

Oscar pidio que la Validacion se vea igual que el Compras (misma linea de imagen corporativa). Cambios en validation_exporter.py: (1) HEADER_FILL cambiado de azul 5B9BD5 a verde FF00FD28, el mismo del Compras, con fuente negra en negrita (antes blanca). (2) TITLE_FONT a 14pt negro (antes 13pt azul). (3) TOTAL_FILL a verde claro E2F0D9 para armonizar. (4) Nueva funcion _add_logo que inserta el logo de Soriana en A2, y se llama en las 3 hojas (Resumen, Consolidado, Detalle PAGOS). (5) Titulos movidos a columna D centrados y merge, igual que el Compras, para no encimarse con el logo. Verificado en las 3 hojas: 1 imagen (logo), header_fill FF00FD28, negrita, titulo 14pt en D2. La Validacion es chica asi que se mantiene openpyxl sin problema de rendimiento. NOTA: regenerar la Validacion releyendo el Compras de 27MB es lento (~2-3 min) por el read_compras_workbook de openpyxl; una futura optimizacion seria pasarle el DataFrame en memoria via write_validation_from_dataframe (que el pipeline ya usa).

**Archivos:** `automation_cobros/validation_exporter.py`

---

### 2026-07-23 14:27:43 — [CÓDIGO] Pipeline de una sola accion: compras -> cruce -> recalculo -> validacion

Nuevo modulo automation_cobros/pipeline.py con generar_salida_proveedor(vendor, start, end, parquet, outdir). Encadena las 4 etapas post-descarga EN MEMORIA: fetch_compras desde SQL, cruce con CPA Vision (RFC auto-detectado del cnpj, filtrado por codigo de barras), recalculo, y Validacion de Condiciones armada desde el DataFrame sin releer el Compras gigante. Escribe dos archivos: Compras completo (opcion B) y Validacion (el entregable). Expuesto como subcomando 'python main.py cpa-salida' y como boton 'Generar salida completa (1 clic)' en la tarjeta ETAPA 2 de la GUI (usa Proveedor y fechas de la barra superior; el boton de solo-cruce quedo como paso secundario). PILOTO REAL exitoso con Selecta del Campo (741) periodo completo 2020-2025: 55,375 renglones, 27.3% con CFDI encontrado (15,090), Consolidado de 195 filas de diferencias, Detalle PAGOS de 1,125 filas. Compras 27.6 MB, Validacion 135 KB, 3 hojas correctas (Resumen, Consolidado, Detalle PAGOS). GUI construye OK con los 6 indicadores. Este es el flujo que produce los entregables de los 6 urgentes.

**Archivos:** `automation_cobros/pipeline.py`, `automation_cobros/app.py`, `main.py`, `docs/CRUCE_IMPLEMENTACION.md`

---

### 2026-07-23 14:15:07 — [DATO] Descarga de Celaya y Selecta verificada: completa, los 6 urgentes ya estan

Se descargaron los 2 urgentes que faltaban. Verificado contra el Parquet: EMPACADORA CELAYA (ECE830923MJ2) request 641727, 1,108,078 filas, los 6 anios 2020-2025 (rango real 2020-01-02 a 2025-12-30). SELECTA DEL CAMPO (SCA060711FG6) request 641815, 43,224 filas, los 6 anios (rango 2020-01-02 a 2025-12-31). Un solo request_id cada uno, SIN duplicacion. Con esto los 6 proveedores URGENTES estan completos y listos para el pipeline compras -> cruce -> recalculo -> validacion.

**Archivos:** `docs/PLANEACION.md`

---

### 2026-07-23 12:19:38 — [DATO] RFC de los 6 urgentes resueltos: 4 de 6 ya descargados, faltan Celaya y Selecta

Se resolvieron los RFC de los 6 urgentes desde SQL (fetch de un mes y lectura de cnpj). Verificado contra el Parquet: 4 de 6 YA estan descargados: Pepsico 76034 CPM110719SG3, Nestle 5462 MNE0409226K9, Arca 391250 DJB850527F30, y 3M 80622 TMM720509PYA (solo 2025, que era su periodo, ya estaba en el parquet). Faltan solo 2: Empacadora Celaya 73692 ECE830923MJ2 y Selecta del Campo 741 SCA060711FG6, ambos periodo completo 2020-2025. Se creo urgentes_pendientes.xlsx con columnas RFC y FECHAS (ambos 2020-2025) para el lote de descarga. El comando cpa-batch-vendors lee ese Excel; FECHAS acepta rango 2020-2025 o un anio; con --parquet-dir outputs/cpa_vision/parquet la descarga se convierte al mismo dataset. DECISION de Oscar sobre el exportador: opcion B, escribir el Compras completo aunque tarde ~20 min; opcion A (no escribir el gigante, solo la Validacion) queda anotada como alternativa futura en docs/RENDIMIENTO_EXPORTADOR.md.

**Archivos:** `docs/PLANEACION.md`, `urgentes_pendientes.xlsx`, `docs/RENDIMIENTO_EXPORTADOR.md`

---

### 2026-07-23 11:42:22 — [CÓDIGO] Exportador de Compras reescrito: valores en Python + xlsxwriter (mucho mas rapido)

Oscar eligio 'valores en Python' para el exportador. Cambios: (1) Las 10 columnas que eran formulas vivas de Excel ahora se calculan como VALORES en Python via nueva funcion calculations.apply_display_formula_values, replicando las formulas originales; dpagar se calcula como suma de impaud por concaten con groupby, lo que ELIMINA el limite del VLOOKUP de 4779 folios. (2) Motor de escritura cambiado de openpyxl a xlsxwriter en modo constant_memory (streaming); el wb.save() de openpyxl era el cuello real, 51s solo para guardar 30k filas. (3) Sin estilo por celda en los datos, solo el encabezado; se quito el borde/alineacion por celda que eran millones de asignaciones. (4) prepare_compras_dataframe ya no repite normalize_date_columns + add_derived_base_columns (corrian dos veces). Se eliminaron _apply_formula_columns, _force_formula_recalculation, _write_impaud_helper_sheet, FORMULA_COLUMNS y la hoja auxiliar impaud. RESULTADO medido: Nestle 1 mes (10,731 filas) SQL 4s + Excel 22s; el archivo abre instantaneo en Excel (sin formulas); sin limite de folios. Verificado correcto: 2 hojas (Compras, Pendientes_EDI), encabezado en fila 7, cto_aud presente, datos desde fila 8, RFC en A8. GUI e imports OK, sin referencias colgadas. PENDIENTE IMPORTANTE: para proveedores enormes (5 anios ~700k filas x 105 cols = 73M celdas) sigue siendo ~20 min y archivo inmanejable; el cuello ya no es el motor sino la magnitud. Recomendacion documentada en docs/RENDIMIENTO_EXPORTADOR.md: el entregable real es la Validacion (chica), el Compras gigante es intermedio; opcion recomendada es no escribirlo en Excel para proveedores enormes o segmentarlo por anio. Tambien pendiente vectorizar make_folio/clean_code en add_derived_base_columns (el prepare es el 40% del tiempo). requirements.txt actualizado con XlsxWriter.

**Archivos:** `automation_cobros/excel_exporter.py`, `automation_cobros/calculations.py`, `requirements.txt`, `docs/RENDIMIENTO_EXPORTADOR.md`

---

### 2026-07-23 10:31:02 — [CÓDIGO] El cruce ahora SOLO rellena celdas vacias (regla de negocio de Oscar) + piloto real con Nestle

Oscar aclaro que el cruce no debe llenar todo, solo las columnas VACIAS de Compras, y que si muchas quedan sin llenar esta bien. Correccion importante: antes se sobrescribia la columna entera (pisaba datos que Compras ya traia). Ahora cada columna se escribe solo donde _vacio() es cierto y hay valor cruzado; las derivadas ctobto_edi/impart_edi tambien solo en huecos con insumo; nunca se pisa un dato ni se rellena con 0 un renglon sin CFDI. Nueva metrica principal: celdas vacias rellenadas (ya no tasa de cruce). Se agrego _vacio() y el campo celdas_llenadas al ResultadoCruce. PILOTO REAL de punta a punta con Nestle (5462) 2024 desde SQL: 134,850 renglones de compras, RFC auto-detectado MNE0409226K9, filtrado a 650 codigos de barras (viable en memoria), 696,069 conceptos de CPA cargados en 5s, cruce en 9s. Resultado: 93,827 renglones (69.6%) encontraron CFDI, 282,481 celdas vacias rellenadas, 41,023 sin CFDI se dejan como estan. Techo real medido: 82.8% de los renglones tienen un CFDI que empata por codigo de barras + factura; el resto no tiene match (codigo que no coincide o factura ausente, reunion 1 R3). DIAGNOSTICO de ambiguedad: de 90,072 llaves repetidas, 99.94% tienen el mismo valor unitario (mismo producto en varias lineas de la misma factura); _indexar ahora colapsa las identicas y solo descarta las que chocan de verdad. Fix de dtype: convertir la columna destino a object antes de rellenar (pandas nuevo no deja meter texto en float64). test_cruce_cpa.py actualizado a la semantica de llenar-solo-huecos (vacia el bloque EDI antes de cruzar, como Pendientes_EDI); pasan las 3 validaciones. GUI construye OK.

**Archivos:** `automation_cobros/cruce_cpa.py`, `test_cruce_cpa.py`, `scripts/piloto_cruce.py`, `docs/CRUCE_IMPLEMENTACION.md`

---

### 2026-07-23 10:01:29 — [CÓDIGO] Cruce: deduplicacion de request_id y filtrado por codigo de barras para escala

Dos cambios en cruce_cpa. (1) DEDUPLICACION: cargar_cpa asigna cada year al request_id mas completo (mas anios distintos, a igualdad mas filas) via ROW_NUMBER en DuckDB, y descarta el resto. Resuelve la duplicacion del 2025 en Pepsico (req 619617 vs 619939) y Nestle (618728 vs 620512) sin borrar particiones. Se conserva un solo request como pidio Oscar. (2) FILTRADO POR CODIGO DE BARRAS: cargar el proveedor completo a pandas agota memoria (Pepsico 16M filas dio ArrowMemoryError). Ahora cargar_cpa recibe el set de codigos de barras del Compras y filtra en DuckDB con IN (SELECT bc FROM codigos), normalizando igual en ambos lados (ltrim(regexp_replace) = solo_digitos). Solo llega a memoria lo cruzable. (3) Nueva funcion orquestadora cruzar_proveedor(compras_path, parquet_root, rfc=None) que lee el Compras, resuelve el RFC (arg o cnpj), arma los barcodes, carga CPA filtrado y cruza; devuelve (ResultadoCruce, rfc). La GUI y el CLI se simplificaron para usarla. Verificado que todo importa y la GUI construye. Prueba piloto con Nestle (5462) en curso: generando su Compras 2020-2025 desde SQL.

**Archivos:** `automation_cobros/cruce_cpa.py`, `automation_cobros/app.py`, `main.py`, `docs/CRUCE_IMPLEMENTACION.md`

---

### 2026-07-23 08:29:07 — [CÓDIGO] El cruce detecta el RFC solo desde el Compras (resuelve el problema numero->RFC)

Oscar planteo que muchas veces no se sabe el RFC de un proveedor a partir del vendor number. Solucion: no hace falta una tabla de mapeo, porque el archivo de Compras ya trae el RFC en la columna cnpj. Nueva funcion cruce_cpa.rfc_de_compras() que lo lee. La GUI y el CLI ahora auto-detectan el RFC del Compras; el campo RFC de la GUI paso a ser opcional (solo para forzar otro). Verificado: rfc_de_compras devuelve ALC0011111Y9 del archivo real de Alceda, ignora nulos, y la GUI construye. Flujo: numero de proveedor -> F_COMPRAS -> Compras.xlsx -> cnpj -> RFC -> Parquet. El auditor nunca teclea el RFC.

**Archivos:** `automation_cobros/cruce_cpa.py`, `automation_cobros/app.py`, `main.py`

---

### 2026-07-22 16:03:18 — [CÓDIGO] GUI rehecha con el lenguaje visual PRGX e integrado el cruce de CPA Vision

RESPUESTA A LA PREGUNTA DE OSCAR: no, el cruce NO estaba en la GUI; app.py solo tenia los tres botones de la Etapa 1 y cero menciones de CPA Vision. Ahora si esta. CAMBIO 1 - INTEGRACION: nueva tarjeta ETAPA 2 con el boton 'Rellenar EDI desde CPA Vision', mas campos de RFC y carpeta Parquet. Toma como entrada el 'Compras editado' de la Etapa 1, vuelca las metricas completas del cruce en la bitacora (tasa de cruce, desglose por estrategia y discrepancias de la doble validacion), escribe <nombre>_EDI.xlsx y lo deja seleccionado como entrada del siguiente paso. Si el RFC no tiene datos en el Parquet lo dice en vez de generar un archivo vacio. CAMBIO 2 - VISUAL: se replico el lenguaje de Conciliacion_Memo_Panoptic. Nuevo modulo automation_cobros/ui.py con las paletas PRGX clara y oscura, la clase Tema, la clase Indicadores (puntos de estado y barras de progreso con parpadeo) y fabricas de widgets (tarjeta, titulo_seccion, boton_principal, boton_paso, separador, pista, campo, boton_secundario). ui.py no importa nada del dominio, asi que es reutilizable en otras herramientas de la suite. app.py se reescribio con customtkinter: encabezado con icono PRGX, subtitulo 'PRGX · Soriana Audit Suite', logo Soriana y toggle de tema; barra de configuracion; dos tarjetas con insignia numerada; y bitacora con timestamp gris y mensajes coloreados por tipo. Assets copiados de Panoptic a automation_cobros/assets. CONCURRENCIA: _ejecutar() centraliza el patron de hilo daemon mas indicador; los widgets solo se tocan desde el hilo de Tk via queue e Indicadores.estado() reencola con after(0). BUILD: AutomationCobros.spec actualizado con collect_submodules('automation_cobros') porque los subcomandos importan dentro de funciones, collect_data_files('customtkinter') porque carga temas JSON en runtime, la carpeta assets, templates y el icono .ico. Nuevo scripts/build_release.py que compila y empaqueta en dist/AutomationCobros_<version>_<fecha>.zip. requirements.txt actualizado con customtkinter, duckdb y pyarrow. VERIFICADO: la GUI construye, el toggle de tema funciona en ambos sentidos y se capturaron pantallazos de los dos modos. PENDIENTE: no se ha compilado ni probado el .exe.

**Archivos:** `automation_cobros/app.py`, `automation_cobros/ui.py`, `automation_cobros/assets`, `AutomationCobros.spec`, `scripts/build_release.py`, `requirements.txt`, `docs/GUI.md`, `CLAUDE.md`

---

### 2026-07-22 15:37:14 — [CÓDIGO] Implementado el cruce CPA Vision -> Compras

Nuevo modulo automation_cobros/cruce_cpa.py y subcomando 'python main.py cpa-cruce'. Arquitectura: funciones puras mas un dataclass ResultadoCruce, sin estado global. Lee el Parquet con DuckDB para aprovechar el particionado por RFC y no cargar 66M de filas a memoria. CRUCE EN DOS PASADAS: principal por codigo de barras mas Serie+Folio normalizados (mayusculas sin caracteres no alfanumericos, para absorber los formatos FN-21226 / FN21226 / -21226), y respaldo por codigo de barras mas la parte numerica del folio, aplicado solo a los renglones que no cruzaron. Las llaves ambiguas (mas de un concepto del CFDI) se DESCARTAN en vez de tomar una al azar, y se reportan; preferimos no llenar un dato a llenarlo mal. El codigo de barras se normaliza a digitos, lo que de paso resuelve C17 (notacion cientifica). DOBLE VALIDACION PERMANENTE: ademas de copiar el importe del CFDI se calcula la formula sobre totfactura en columnas de control impiva_edi_formula e imieps_edi_formula, y se reporta cuantos renglones difieren. BUG ENCONTRADO Y CORREGIDO durante la implementacion: la primera version leia factem_edi asumiendo que ya venia lleno, pero medido en Alceda fact_empaq esta lleno al 100% (400/400) y factem_edi solo al 24% (98/400); factem_edi hay que LLENARLO desde fact_empaq. Sin la correccion, ctobto_edi e impart_edi habrian salido en 0 para el 76% de los renglones. PRUEBA: test_cruce_cpa.py usa invnbr y codbarra reales de Alceda y simula el lado de CPA Vision; resultado 98.5% de cruce sobre 400 renglones (los 6 sin cruce no tienen invnbr o codbarra) y pasan las tres validaciones de calculo. PENDIENTE: no se ha podido validar contra un proveedor real que exista en ambos lados, porque ninguno de los 43 RFC descargados coincide con los archivos de Compras disponibles.

**Archivos:** `automation_cobros/cruce_cpa.py`, `main.py`, `test_cruce_cpa.py`, `docs/CRUCE_IMPLEMENTACION.md`, `CLAUDE.md`

---

### 2026-07-22 15:23:28 — [BUG] invnbr tiene formato inconsistente: el cruce directo contra Folio no funcionaria

Se inspecciono outputs/Compras_383612_ALCEDA S. A. DE C. V.xlsx (cerca de 3000 valores de invnbr). invnbr es el NUMERO DE FACTURA DEL PROVEEDOR con su serie incluida, capturado en el sistema con formato inconsistente. Patrones encontrados en Alceda: FN-99999 (2688 filas), FN99999 (168), FN-999999 (70), FN-9999999 (33), -999999 (9), 99999 (7) y REM-9999-9999999 (4). Oscar confirmo con otra captura que la serie cambia por proveedor (EXT, TSO, FN, REM) y que el formato es inconsistente incluso dentro del mismo proveedor: conviven EXT-13163 y EXT13338. En cambio CPA Vision trae los datos limpios y separados en Serie (O), Folio (P) y SerieFolio (N). CONSECUENCIA: un JOIN directo invnbr = Folio no encontraria practicamente nada. ESTRATEGIA PROPUESTA: normalizar ambos lados a mayusculas quitando todo lo no alfanumerico (FN-21226 -> FN21226 que empata con SerieFolio), y como respaldo reintentar solo con la parte numerica contra Folio. Hay que medir y reportar la tasa de cruce de cada estrategia antes de dar el cruce por bueno. El riesgo de falso positivo del respaldo se acota porque el cruce ya va restringido por RFC y codigo de barras. Otras columnas de compras confirmadas: encabezados en la fila 7 (no la 6) en este archivo, y hojas Compras, impaud y Pendientes_EDI.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 14:54:45 — [BUG] DOBLE VALIDACION sobre 66M de filas: la formula del impuesto es incorrecta en el 55% de las facturas

Se aplico la doble validacion propuesta por Oscar (calcular las formulas candidatas y compararlas contra el importe en pesos del CFDI) sobre el dataset Parquet completo con DuckDB. Script reproducible en scripts/validar_formulas_impuesto.py. RESULTADO 1: las columnas IVA (S) e IEPS (U) de CPA Vision son el importe del impuesto DEL RENGLON, identicas a Importe Impuesto (AP), con coincidencia del 100.00% en 8,692,170 filas de IVA 16% y en 13,167,869 filas de IEPS 8%. La formula Total/(1+t)*t solo coincide en el 0.9% y el 4.4% respectivamente. Ninguna fila trae IVA e IEPS distintos de cero a la vez. RESULTADO 2 a nivel factura: la formula Total/1.16*0.16 solo cuadra en el 1.3% de las 401,981 facturas con tasas mezcladas (55% del total), con error promedio de +1,565.86 pesos; en las de tasa unica cuadra el 89%. La causa es que la mayoria de las facturas de Soriana mezclan articulos gravados y a tasa 0 (alimentos), y dividir el Total completo entre 1.16 asume que todo esta gravado. Ejemplo real UUID d0597acb con 65 renglones: IVA real 60.47 contra 5,003.33 que da la formula, 83 veces mas. DECISION TECNICA: impiva_edi e imieps_edi se COPIAN de S y U, no se calculan. Esto cierra C13, C14, C19 y C20. C14 se resuelve porque el dato es por renglon y por lo tanto se puede sumar sin duplicar. ADEMAS: C15 y C9 CERRADOS con datos reales; el Parquet SI trae las tasas especiales de vinos y licores (22,293 filas al 26.5%, 20,186 al 53% y 993 al 30%), asi que la premisa de Luis de que esos proveedores no se descargan era falsa.

**Archivos:** `scripts/validar_formulas_impuesto.py`, `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 14:27:03 — [BUG] CORRECCION: el mapeo de tasas estaba invertido (C18 cerrado)

Oscar reviso un proveedor con IVA de 16% y confirmo que la columna IVA de CPA Vision trae el IMPORTE EN PESOS (38.43, 101.65, 677.67, 813.20) y la columna TASA IVA trae el PORCENTAJE (0.16). MAPEO CORREGIDO: poriva_edi viene de V (TASA IVA) y prieps_edi viene de X (TASA IEPS), NO de S y U como se habia dicho en la reunion 004 [9:58] y como estaban las anotaciones moradas de la captura 11:28. Esas eran las columnas de importe. De no haberse detectado, poriva_edi se habria llenado con pesos e impart_edi habria multiplicado por (1+38.43) en vez de por 1.16. CONSECUENCIA: C19 se REABRE, porque los importes de impuesto SI vienen en CPA Vision (columnas S y U), contra lo que se concluyo en la reunion 004 [11:13]. Se podrian copiar en vez de calcularlos, lo que eliminaria C13 y usaria el dato del CFDI en lugar de reconstruirlo. Es decision de Oscar porque cambia lo acordado con Luis. NUEVO HUECO C20: la formula del IEPS (Total/(1+ieps)*ieps) sobrestima cuando la factura trae IVA e IEPS a la vez, porque el IEPS grava el subtotal pero el Total ya incluye IVA; el resultado sale inflado por (1+iva). Sin verificar por falta de facturas con IEPS real (C15). Desaparece si se adopta C19.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 12:45:42 — [DECISIÓN] REGLA DE ALCANCE: solo se tocan las columnas marcadas BT-CD

Oscar establecio la regla: las UNICAS columnas que se llenan son las del bloque BT-CD marcadas con las bandas de color. Todo lo demas del archivo de compras se deja exactamente como esta, y si una columna no aparece marcada ahi no se modifica ni hay que buscarle origen. Esto cierra C10 (descuento de catalogo) como FUERA DE ALCANCE: facdecto (AM) y fact_desct (BQ) no estan marcadas, asi que son de solo lectura. Tambien se descarta por ahora el archivo AP-LI y el conteo de registros por proveedor; Oscar indicara los 50 prioritarios mas adelante. Hallazgo adicional de la captura 42:03: la formula de concaten es =CONCATENATE(N23,L23), es decir strnbr + rcvnbr (tienda + nota de entrada), lo que confirma la composicion del folio. Catalogo ampliado de columnas de compras: AK poitmgrscst, AL poitmnetcst, AM facdecto, AN ctouni, AO ctontol, AP ctoaudl, AQ impaud, AR dpagarl, AS iva, AY ieps_t007s, AZ iva_t007s, BQ fact_desct, BR tipo_marca, BS cod_tipo_mvto.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 12:39:55 — [DATO] Punto 4: llave del cruce ID_CRUCE y origen de factem_edi confirmados

C11 CERRADO: factem_edi (BU) se alimenta de fact_empaq, que ya existe en el archivo de compras en la columna AF. Confirmado en la captura 39:17 (AF6 = fact_empaq) y por Oscar. Por eso esta marcada en verde y no en amarillo; no hay que buscarla en CPA Vision. LLAVE DEL CRUCE (ID_CRUCE, marcado en rojo por Oscar): codigo de barras = compras.codbarra (col Y) <-> cpa.noIdentificacion (col AK); numero de factura = compras.invnbr (col R) <-> cpa.Folio (col P); numero de proveedor = compras.vndnbr (col B). OJO: compras tiene dos columnas de codigo, Y=codbarra (la llave) y Z=upc (NO es la llave). Se documento el catalogo completo de columnas de compras de la A a la CF, incluyendo rcvnbr (L) y strnbr (N) que forman el folio, can_rec (AJ), ctouni (AN) que es el costo del sistema contra el que se compara ctonto_edi, y las tasas SAP ieps_t007s/iva_t007s (AY/AZ). C10 se actualiza: ahora hay TRES candidatos para el descuento de catalogo, la columna Descuento (AJ) de CPA Vision y en compras facdecto (AM) y fact_desct (BQ); hay que preguntarle a Luis cual es.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 12:29:18 — [DECISIÓN] Criterio del impuesto CERRADO por Oscar: la formula del IVA debe usar poriva_edi

Oscar aclaro que el 1.16 y 0.16 de la formula de impiva_edi eran CIRCUNSTANCIALES (porque poriva_edi vale 0.16 en ese proveedor), no intencionales, y que la formula correcta debe ser igual a la del IEPS usando la tasa de la celda: impiva_edi = (totfactura/(1+poriva_edi))*poriva_edi. Con esto C13 queda CERRADO EN CRITERIO, pendiente solo de implementar. Tambien confirmo que impiva_edi e imieps_edi son FORMULAS calculadas en compras sobre el TOTAL DE LA FACTURA (no por articulo, no copiadas de CPA Vision), lo que descarta C19 y deja C14 como el pendiente real. C16 CERRADO: el porcentaje sale del bloque de comprobante, S (IVA) -> poriva_edi y U (IEPS) -> prieps_edi; la etiqueta imieps_edi que aparecia sobre V (TASA IVA) era una anotacion a medio pegar, no un mapeo. Mapeo adicional confirmado en las capturas 14:19 y 15:46: Z -> uuid, AF (Cantidad) -> canfac_edi, AH (Valor Unitario) -> ctonto_edi. Y en la captura 13:26 se ven las 3 columnas marcadas en amarillo en compras: prieps_edi, poriva_edi y uuid. Queda C18 como comprobacion barata: verificar en una factura con IVA 16% que la columna S traiga 0.16 y no el importe.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 12:15:58 — [DATO] Convencion de las anotaciones en morado de las capturas

Oscar aclaro la convencion de sus capturas: los rotulos en MORADO son sus anotaciones con el nombre del campo DESTINO en la base de compras; los nombres en negro (IVA, IEPS, TASA IVA...) son los encabezados ORIGINALES del archivo de CPA Vision. Morado = a donde va, negro = de donde viene. Mapeo anotado en el minuto 11:28: S (IVA) -> poriva_edi, U (IEPS) -> prieps_edi, V (TASA IVA) -> imieps_edi. Las dos primeras coinciden con lo dicho en la reunion 004. La tercera queda pendiente de confirmar porque cruza IVA con IEPS, y ademas la anotacion estaba a medio pegar segun la barra de estado. Tampoco quedo anotado de donde sale impiva_edi. Se corrige la interpretacion previa: no es que la reunion se hubiera equivocado con S y U.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 12:10:11 — [DATO] Capturas 10:03 y 11:28: estructura de impuestos de CPA Vision y llave del cruce

HALLAZGO PRINCIPAL: el archivo de CPA Vision tiene DOS bloques de impuestos a niveles distintos. Bloque A nivel COMPROBANTE (S=IVA, T=ISR, U=IEPS, V=TASA IVA, W=TASA ISR, X=TASA IEPS) y bloque B nivel CONCEPTO (AO=Base, AP=Importe Imp, AQ=Impuesto, AR=Tasa o cuota). El equipo tomo el bloque A, lo que EXPLICA R22 (el impuesto se calcula a nivel factura completa): no era un error de Luis, es la estructura del archivo. Verificado que los valores del bloque A se repiten por fila: el folio 64177184 ocupa 9 filas con Subtotal=Total=1500.84, lo que refuerza C14. C16 queda casi resuelto: se usa el bloque de comprobante, pero falta desempatar si el porcentaje sale de S/U (como dice la etiqueta de Oscar y la reunion) o de V/X (como dicen los encabezados TASA...). No se puede desempatar porque tanto SPECTRUM BRANDS como Lala traen todo el bloque de impuestos en 0 -> nuevo hueco C18. OPORTUNIDAD (C19): si S y U son IMPORTES y no tasas, entonces impiva_edi e imieps_edi se podrian COPIAR en vez de calcular, y C13 desapareceria de raiz. En la reunion 004 [11:13] se concluyo que el importe no venia en CPA Vision, pero puede que si venga. Se resuelve mirando una sola factura con IVA de 16%. Ademas se documento la llave del cruce: el numero de factura es la columna P (Folio); queda por confirmar si compras usa el Folio solo o el SerieFolio completo (FMZ64171398 vs 64171398).

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 12:05:56 — [DATO] Capturas 33:19-38:44 de la reunion 004: formulas de impuesto capturadas literales

HALLAZGO DECISIVO: las dos formulas de impuesto NO siguen el mismo patron. imieps_edi (BZ) usa =+(CC7/(1+BY7))*BY7, es decir la tasa DINAMICA leida de la celda; impiva_edi (CB) usa =+(CC7/1.16)*0.16, con la tasa QUEMADA. El patron correcto ya existe en el mismo archivo, asi que arreglar C13 es copiar la formula vecina: =+(CC7/(1+CA7))*CA7. VALIDACION: en el minuto 36:55 Oscar tecleo prieps_edi=0.08 solo para probar y el resultado fue 2791.56148; verificado 37686.08/1.08*0.08 = 2791.5614814..., cuadra exacto. OJO: ese 0.08 es valor de prueba, NO dato real; C15 pasa a parcial (la formula esta validada, falta un proveedor real con IEPS). Impacto medido de la tasa quemada en la fila 7: con tasa 8% el error es de 2406.52 y con tasa 0% es de 5198.08 de impuesto inventado. Otras formulas capturadas: ctobto_edi (BV) = +BW7*BU7 [37:43]. Verificado que prieps_edi y poriva_edi son VALORES (datos de CPA Vision) mientras que imieps_edi, impiva_edi, ctobto_edi e impart_edi son FORMULAS, lo que confirma las bandas de color. Documentada la estructura del libro: hojas impaud, dpagar, Sheet3, Compras, Compra_Neta x Mes, Analisis de Costos; encabezados en la fila 6 y datos desde la fila 7; columnas cto_aud (CE) e iva_aud (CF) despues del bloque EDI.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 11:52:25 — [DATO] Captura de CPA Vision: columnas reales W-AU y factura de 1386.18 verificada

Oscar aporto la captura con los nombres y letras reales del archivo de CPA Vision. Mapeo confirmado: Y=Total -> totfactura, Z=UUID -> uuid, AF=Cantidad -> canfac_edi, AH=Valor Unitario -> ctonto_edi, AI=Importe concepto, AJ=Descuento, AK=noIdentificacion (codigo de barras). VERIFICADO: la suma de los 7 Importe concepto da exactamente 1386.18 = Total (col Y); es la misma factura revisada en la reunion 004 [24:56]. HALLAZGO 1: el Total se REPITE en los 7 renglones de la factura, lo que confirma C14 (sumar el impuesto por renglon daria 7x el IVA real). HALLAZGO 2: esa factura tiene tasa 0 (alimentos), asi que la formula quemada (Total/1.16)*0.16 le calcularia 191.20 de IVA inexistente: caso real que confirma C13. HALLAZGO 3: la identidad suma(importe concepto)=Total solo se cumple con tasa 0; con IVA 16% el Total seria la suma x 1.16. Nuevos huecos C16 (de que columna sale la tasa: la reunion dijo S y U pero la captura muestra X y el bloque AQ+AR) y C17 (noIdentificacion se ve como 7.50102E+12, hay que forzarlo a texto o el cruce falla).

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`

---

### 2026-07-22 11:45:27 — [DATO] Capturas del archivo real: mapeo del cruce corregido y verificado

Oscar aporto 6 capturas del archivo de compras real (proveedor 137 - SPECTRUM BRANDS). Se reescribio MAPEO_CRUCE_CPA_COMPRAS.md con los NOMBRES REALES de las columnas BT-CD (canfac_edi, factem_edi, ctobto_edi, ctonto_edi, impart_edi, prieps_edi, imieps_edi, poriva_edi, impiva_edi, totfactura, uuid) y las bandas de color que indican el origen: 6 columnas se copian de CPA Vision, 1 ya esta en compras (factem_edi) y 4 se calculan. Formulas literales capturadas: impart_edi = (ctobto*canfac)*(1+poriva) e impiva_edi = (totfactura/1.16)*0.16. VERIFICADO: las 9 filas de las capturas cuadran exactamente en las 3 formulas. CORRECCION a la nota de la reunion 004: impart_edi NO se copia del importe concepto de CPA Vision, se calcula. HALLAZGO: CPA Vision tiene columna Descuento, posible enganche del descuento de catalogo (C10). Nuevo hueco C15: no hay ningun caso de IEPS real validado, todos los ejemplos traen IEPS en 0. Ademas se guardaron las 4 transcripciones integras en docs/reuniones/transcripciones/.

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`, `docs/reuniones/transcripciones/001-2026-04-23-transcripcion.md`, `docs/reuniones/transcripciones/002-2026-04-29-transcripcion.md`, `docs/reuniones/transcripciones/003-transcripcion.md`, `docs/reuniones/transcripciones/004-2026-06-09-transcripcion.md`

---

### 2026-07-22 11:37:26 — [REUNIÓN] Reunión 004 (2026-06-09) documentada — MAPEO DE COLUMNAS DEL CRUCE

La reunion mas importante del proyecto. Se creo el documento dedicado docs/MAPEO_CRUCE_CPA_COMPRAS.md con: la llave del cruce (proveedor + factura + codigo de barra, que en CPA se llama 'numero de identificacion'), los 11 campos EDI a llenar, el mapeo directo de columnas (valor unitario -> costo neto EDI, AF -> cantidad facturada, S -> IVA EDI, U -> IEPS EDI, Y/total -> total factura, importe concepto -> importe por articulo EDI col BX, UUID), y 6 formulas validadas en vivo. Hallazgos: costo bruto y factor empaque NO vienen de CPA (el factor sale de compras, el costo bruto se deriva); los importes de impuesto tampoco vienen, solo el porcentaje. Reglas R19-R24. CAMBIO DE ESTRATEGIA: descargar todo primero a SQL y cruzar despues, revirtiendo la opcion 2 de la reunion 002. Nuevos huecos C13 (tasas 1.16/1.08 literales) y C14 (los importes de impuesto se calculan a nivel factura pero calculations.py lo hace por renglon).

**Archivos:** `docs/MAPEO_CRUCE_CPA_COMPRAS.md`, `docs/reuniones/004-2026-06-09-mapeo-columnas-cruce.md`, `docs/LOGICA_NEGOCIO.md`, `docs/ESTADO_ACTUAL.md`, `CLAUDE.md`

---

### 2026-07-22 11:33:05 — [DECISIÓN] Mecanica de descarga de CPA Vision: tema cerrado

Oscar confirmo que toda la parte de descarga de CPA Vision (botones, selecciones, filtros, formato de solicitud) ya esta bien y no requiere trabajo. Se cerraron los huecos C8 (cuenta compartida) y C12 (varios RFC por solicitud) como no accionables. C9 (vinos y licores con tasas especiales no bajan) se reclasifica: no es un problema de descarga sino de cobertura de datos, a tener presente al interpretar los resultados del cruce. El foco queda en la logica de la Etapa A y el cruce CPA -> compras.

**Archivos:** `docs/LOGICA_NEGOCIO.md`

---

### 2026-07-22 11:28:40 — [REUNIÓN] Reunión 003 documentada — Capacitación CPA Vision con Luis Martinez

Reglas R14-R18. (1) CORRIGE el procedimiento de descarga de la reunion 002: en Emitidos NO se marca nada, solo Recibidos + Vigentes + Ingreso. Verificado en codigo: cpa_vision.py YA lo implementa correctamente (lineas 35-37). (2) R18 CIERRA el hueco C2: la fuente de verdad del impuesto es la factura. (3) Limitacion critica: la hoja de CPA Vision solo trae tasas 16% y 8%, NO vinos/licores (53%, 30%, 26.5%) -> nuevo hueco C9, impacto economico alto. (4) Concepto nuevo no implementado: descuento de catalogo -> C10. (5) Factor de empaque cuando las unidades no coinciden -> C11. (6) Prueba de 2 RFC en paralelo quedo inconclusa -> C12.

**Archivos:** `docs/reuniones/003-2026-XX-XX-capacitacion-cpa-vision-luis.md`, `docs/LOGICA_NEGOCIO.md`, `docs/reuniones/README.md`

---

### 2026-07-22 11:22:04 — [DECISIÓN] Objetivo de la semana definido por Oscar

Alcance acotado: (1) dejar bien hecha la logica de la Etapa A, (2) descargar ~50 proveedores PRIORITARIOS en CPA Vision (no los 986 del vendor master), (3) implementar el cruce CPA Vision -> compras para vaciar las columnas faltantes, (4) recalcular, (5) generar el archivo de validacion de condiciones. El mapeo exacto de columnas del cruce esta en la transcripcion de la REUNION 4, aun por documentar. FUERA DE ALCANCE: la integracion dentro de Audit Tools (hueco C6) queda aplazada; no retomarla hasta nueva indicacion.

**Archivos:** `docs/ESTADO_ACTUAL.md`, `docs/LOGICA_NEGOCIO.md`

---

### 2026-07-22 11:16:13 — [REUNIÓN] Reunión 002 (2026-04-29) documentada — Paso a paso de CPA Vision

Se documentaron las reglas R7-R13. Lo más importante: (a) la LLAVE DEL CRUCE CPA Vision-Compras es proveedor + factura + codigo de barra (R9), especificacion del puente Etapa A-B que sigue sin implementar; (b) el paso a paso manual completo de la descarga en CPA Vision, que es la especificacion literal del scraper; (c) restriccion organizacional: la vicepresidencia pidio integrar todo dentro de Audit Tools, sin resolver. Se agregaron los huecos C6, C7 y C8, y se agravo C5 por los pagos de facturas cruzadas historicos.

**Archivos:** `docs/reuniones/002-2026-04-29-paso-a-paso-cpa-vision.md`, `docs/LOGICA_NEGOCIO.md`, `docs/reuniones/README.md`

---

### 2026-07-22 11:10:20 — [REUNIÓN] Reunión 001 (2026-04-23) documentada — Proceso de Compras en Audit Tools

Reunión de arranque con Mónica López y Héctor Saucedo. Se documentaron 6 reglas de negocio (R1-R6), el catálogo de columnas del Excel de Audit Tools, la estructura de 3 pestañas del entregable al proveedor, y el origen de CPA Vision como Etapa B. Hallazgo clave: los campos costo OUT / IVA OUT / IEPS OUT los generó Data Services, no Audit Tools — el criterio exacto quedó pendiente y NUNCA se confirmó. Se abrió la sección 10 de LOGICA_NEGOCIO.md con 5 contradicciones/huecos por resolver (C1-C5).

**Archivos:** `docs/reuniones/001-2026-04-23-proceso-compras-audit-tools.md`, `docs/LOGICA_NEGOCIO.md`, `docs/reuniones/README.md`, `CLAUDE.md`

---

### 2026-07-22 10:56:52 — [CÓDIGO] Se verifica el helper log_cambio.py

Primera ejecución real del script para confirmar que estampa la fecha/hora del sistema y la inserta arriba en la bitácora.

**Archivos:** `scripts/log_cambio.py`

---

### 2026-07-22 10:53:41 — [DECISIÓN] Se crea el sistema de documentación del proyecto

Oscar pidió que toda la información, lógica y contexto quede persistida en archivos del
repo, para que si el chat se cierra o se borra se pueda retomar leyendo el proyecto.

Estructura creada:
- `CLAUDE.md` — índice maestro, se autocarga en cada sesión de Claude Code
- `docs/LOGICA_NEGOCIO.md` — reglas, criterios y columnas (fuente de verdad)
- `docs/reuniones/` — una nota resumen por reunión + índice
- `docs/BITACORA.md` — este archivo
- `docs/ESTADO_ACTUAL.md` — dónde vamos y cuál es el siguiente paso
- `scripts/log_cambio.py` — helper que estampa fecha/hora con `datetime.now()`

Se sembró `LOGICA_NEGOCIO.md` y `ESTADO_ACTUAL.md` con el contexto que ya existía en la
memoria de sesiones anteriores (reglas del folio y costo auditado, dos niveles de
agregación, estado del lote CPA Vision, fragilidades del exportador de Excel).

**Archivos:** `CLAUDE.md`, `docs/LOGICA_NEGOCIO.md`, `docs/BITACORA.md`, `docs/ESTADO_ACTUAL.md`, `docs/reuniones/README.md`, `scripts/log_cambio.py`

---
