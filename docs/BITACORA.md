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

### 2026-08-24 23:21:10 — [CÓDIGO] Cola: el tiempo estimado va en minutos y solo desde 4 proveedores

Dos ajustes pedidos por Oscar. 1) El estimado se muestra en MINUTOS, no en horas: la mayoria de las tandas de trabajo caen por debajo de dos horas y '0.7 h' se lee peor que '42 min'. 2) Solo se muestra cuando hay 4 o mas proveedores pendientes (MINIMO_PARA_ESTIMAR). Con 1, 2 o 3 no se estima nada, y el razonamiento es de Oscar: los dos factores son promedios (7.9 min por descarga sobre 530 intentos medidos, 12 min por entregable), y sobre dos o tres proveedores un promedio no promedia nada porque la dispersion de la fase de salida es enorme —un gigante como Arca o Pepsico se lleva horas por el camino de trimestres mientras uno chico sale en dos minutos. Un estimado que puede errar por un factor de diez es peor que no dar ninguno. El umbral se cuenta sobre los proveedores PENDIENTES (cola.pendientes()), que es lo que el usuario ve en la tabla, no sobre el numero de operaciones. Verificado 1..6 proveedores, en pantalla y tras dos vueltas de cambio de tema.

---

### 2026-08-24 23:09:26 — [CÓDIGO] GUI: acciones renombradas con ayuda, campos por vista y bitacora plegable

Cuatro ajustes pedidos por Oscar tras usar la interfaz. 1) NOMBRES DE LAS ACCIONES: 'Generar con CPA' y 'Generar sin CPA' se prestaban a confusion —parecian variantes de descargar— porque el 'con/sin CPA' no acompaña al descargar sino al generar; descargar siempre es de CPA Vision, no hay otra fuente. Ahora son 'Generar con lo ya descargado' y 'Generar sin cruce de CPA'. Las CLAVES no cambiaron (generar / generar_sin_cpa), asi que las colas guardadas siguen leyendose, y se añadio un alias para que un Excel de lote exportado con los nombres viejos tambien se importe. 2) AYUDA EN LINEA: Accion gana un campo `ayuda` y la interfaz lo muestra bajo el desplegable, en letra chica, que hace la opcion elegida; son cuatro opciones parecidas y el nombre solo no alcanza. ui.opciones acepta al_cambiar. 3) CAMPOS POR VISTA: proveedor/desde/hasta se movieron de la barra comun a la vista 'Un proveedor', que es la unica que trabaja sobre un proveedor concreto (en Por lotes cada renglon trae el suyo, en Ajustes no pintan nada). La carpeta de salida SI es compartida —las dos vistas generan entregables— asi que se fue a Ajustes con las demas carpetas, y las otras dos vistas anuncian en letra chica donde caen los entregables. Desaparece la barra de contexto, que ademas libera ~54 px de alto. 4) BITACORA PLEGABLE Y DE ALTO FIJO: antes se llevaba una porcion variable de la ventana (weight=2), que en pantallas chicas es justo lo que le falta a la vista; ahora ocupa 130 px y se pliega hasta dejar solo su titulo, y row=5 no crece nunca. FALLO CORREGIDO de paso: tras cambiar el tema, los atributos que guardan widgets de las vistas (aviso_cola, tabla_cola, aviso_salida...) apuntaban a widgets destruidos y configurarlos reventaba con TclError; un getattr(...) is not None no lo detecta. Se añadio el helper _widget(nombre) que comprueba winfo_exists(), y se uso en los seis puntos que lo necesitaban. Verificado con DOS vueltas de tema seguidas, que es donde fallaba.

---

### 2026-08-24 17:30:48 — [CÓDIGO] Dos correcciones sobre el rediseño: pestañas invisibles y el scroll que no debia quitarse

1) PESTANAS INVISIBLES (lo reporto Oscar al abrir la aplicacion): CTkSegmentedButton tiene un unico text_color para todos sus segmentos, y aqui hacen falta dos —blanco sobre el acento para la activa, texto oscuro sobre gris para las inactivas—. Con un solo color, en modo claro las inactivas quedaban en blanco #FFFFFF sobre #F3F6FA: no se veian. Se rehizo con CTkButton normales (ui.Pestanas), el mismo patron que ya usa Paso, con su par de colores por estado. Se añadio una comprobacion automatica de contraste sobre TODOS los botones y etiquetas de las tres vistas en los dos temas: 0 pares por debajo de 3.0:1. 2) EL SCROLL: quitar el CTkScrollableFrame fue un error mio. Medido, las vistas piden entre 684 y 752 px y con el encabezado, el contexto, las pestañas, la barra de estado y la bitacora suman 1032-1100 px: no caben en los 900 px de la ventana, y menos en un 1366x768 que es lo que hay en los equipos de destino. Lo que se perdia al recortar era justo el borde inferior, o sea el boton de ejecutar. Se devolvio UN scroll para las tres vistas (no uno por vista). El ahorro de recursos venia de construir solo la vista activa y de dejar una sola barra de progreso, no de quitar el scroll: arranque 2.62 s -> 1.45-1.76 s, widgets 343 -> 181, canvas 100 -> 53, barras 8 -> 1. Cifras corregidas en GUI.md y ESTADO_ACTUAL.md.

---

### 2026-08-24 17:08:29 — [CÓDIGO] Rediseño de la GUI: tres vistas en vez de «etapas», y la lista de pasos

La pantalla se agrupaba en Etapa 1 / Etapa 2, que describe como se construyo el codigo y no como trabaja el auditor; la prueba fue su pregunta real: 'le di a generar Compras, luego a descargar CPA, ¿ahora que?'. Se reorganizo por la pregunta que si se hace el usuario al abrir —¿cuantos proveedores?— en tres vistas con pestañas: Un proveedor / Por lotes / Ajustes. La pieza central es la lista de pasos numerada de la primera vista: cada renglon ES el boton y muestra si ya se hizo (v), si es el siguiente (>) o si no toca (·). El estado sale de lo que hay en disco y en los campos, no de la ultima corrida, asi que reabrir la aplicacion a media faena muestra el mismo mapa; lo que no se puede saber barato se deja pendiente antes que afirmar algo falso, y ningun paso bloquea a otro. RECURSOS (el objetivo era maquinas de 1 nucleo): arranque 2.62 s -> 0.92 s, widgets 343 -> 175, CTkCanvas 100 -> 51, barras de progreso 8 -> 1. Tres palancas: solo se construye la vista activa (las otras nacen al primer clic y luego se ocultan con grid_remove), una sola BarraEstado en vez de un indicador por boton, y el latido es un reloj de 1 Hz en vez de una barra indeterminada animada; la barra de progreso solo sale cuando hay algo real que medir. Fuera el CTkScrollableFrame. En ui.py: se borraron Indicadores, boton_principal, boton_paso, boton_peligro, tarjeta y titulo_seccion; entraron BarraEstado, Paso, pestanas, boton_cta, bloque, rotulo y grupo. CERO cambios de logica de negocio: ejecutor, cola_descarga, pipeline, cruce_cpa y cpa_vision quedaron intactos (verificado: 760/760 proveedores del plan siguen dando comandos identicos y el CLI --listar responde igual). Se arreglo de paso que la memoria del Parquet (_cache_parquet) no se invalidaba: ahora se tira al terminar cualquier operacion, porque una descarga acaba de crear particiones nuevas. El cambio de tema se bloquea mientras algo corre: reconstruye la ventana y destruir la barra de estado a media operacion dejaria al hilo de fondo publicando en widgets muertos.

---

### 2026-08-24 15:29:36 — [CÓDIGO] Cola: la ruta de persistencia se resuelve al llamar, no al importar

Cola.guardar/cargar tenían RUTA_COLA como valor por omisión directo, así que la ruta quedaba grabada al importar el módulo y no había forma de redirigirla. Consecuencia real: una prueba que creía escribir en un temporal machacó la cola guardada del usuario en logs/cola_descarga.json. Ahora el parámetro es None y RUTA_COLA se resuelve dentro de la función, que es además lo que permite probar la persistencia aislada. También se añadió un guardarraíl en ejecutor.ejecutar: comprueba UNA vez que exista el intérprete del .venv antes de lanzar subprocesos (bajo el .exe empaquetado no existe), en vez de dejar N fallos enterrados en N logs.

---

### 2026-08-24 15:29:18 — [CÓDIGO] Cola de trabajo: columna «Qué hacer» y fase de generación (paso 3)

La cola de la GUI dejó de ser solo de descarga. Cada renglón lleva ahora su acción (Solo descargar / Descargar y generar / Generar con CPA / Generar sin CPA), modelada en cola_descarga.ACCIONES como tres interruptores (descarga·genera·cpa) en vez de cuatro ramas. 'Ejecutar la cola' corre dos fases en orden: primero TODAS las descargas (cpa_vision.request_vendor_master_batch, vía el Excel RFC/FECHAS de siempre) y después TODAS las salidas (ejecutor.ejecutar, vía TrabajoSalida) — ese orden es lo que hace que 'Descargar y generar' salga de un solo clic. Trabajo lleva estado por fase (estado / estado_salida): con un solo campo, terminar la descarga sacaría de la fila a un proveedor al que le falta el entregable. listos_para_generar() excluye a quien falló la descarga, para no entregar un Excel con el bloque EDI vacío y sin marcar error. Los renglones se cuentan con database.contar_compras al arrancar la fase de salida, porque de ahí sale la decisión de camino gigante. Nuevo widget ui.opciones(). Verificado: 760/760 proveedores del plan siguen produciendo comandos únicos con las mismas 7 combinaciones de rama, el CLI --listar intacto, y la GUI construye, repinta y sobrevive al cambio de tema.

---

### 2026-08-24 12:56:45 — [CÓDIGO] Motor de ejecucion extraido a automation_costos/ejecutor.py

La decision de QUE comandos produce un proveedor (camino normal vs gigante por UMBRAL_GRANDE, --sin-cpa vs --cruzar-anios, --anios cuando hay años salteados) vivia dentro de scripts/ejecutar_bloque1.py, asi que solo la terminal podia usarla. Se saco al paquete como ejecutor.py para que la GUI ejecute EXACTAMENTE lo mismo y no haya dos definiciones de 'proveedor gigante' separandose con el tiempo. Piezas: TrabajoSalida (dataclass con prov/nombre/anios/anios_cruce/renglones y las propiedades derivadas inicio, fin, usar_cpa, cruce_parcial, con_huecos, grande) es el punto de encuentro entre el Excel del plan y la cola de la interfaz; comandos(); entregados()/ya_entregado(); y ejecutar(), el bucle que corre un proceso por proveedor con log, cronometro, progreso opcional y cancelacion cooperativa ENTRE proveedores. ejecutar_bloque1.py conserva lo que es suyo -argparse, cargar_plan, revisar_cpa y el cache de RFC- y delega el resto; se le quitaron 66 lineas duplicadas y los imports re/subprocess/time que quedaron huerfanos. REFACTOR SIN CAMBIO DE COMPORTAMIENTO, verificado: se capturo una baseline de comandos() ANTES de tocar nada y despues se cotejaron los 760 proveedores del plan uno por uno -760 identicos, 0 diferencias- mas las 7 combinaciones distintas de (grande, cpa, parcial, huecos) contra la baseline en disco. --listar y el filtrado de entregados siguen funcionando igual.

---

### 2026-08-24 12:46:11 — [CÓDIGO] Importar a la cola aceptaba solo Excel con columna num

crear_trabajo exigia que el proveedor fuera numerico, regla correcta al capturar a mano pero equivocada al importar: un Excel con solo RFC/FECHAS -el formato que acepta el CLI y el que documenta docs/GUI.md- entraba con CERO filas, avisando 'El proveedor debe ser un numero'. Solo funcionaba descarga_monica_pendientes.xlsx porque trae la columna num. Se corrige con Trabajo.identidad (el numero de proveedor, o el RFC si no hay) y un unico crear_trabajo(proveedor, fechas, rfc=, nombre=) que exige uno de los dos, en vez de duplicar la funcion para cada camino. Cola.agregar/indice_de/a_excel pasan a usar identidad. El alta manual sigue exigiendo numero.

---

### 2026-08-24 12:33:48 — [CÓDIGO] Cola de descarga por lotes en la GUI

La GUI solo bajaba un proveedor a la vez; el lote existia solo en el CLI (cpa-batch-vendors) y exigia un Excel armado a mano. Ahora hay una tercera tarjeta 'COLA DE DESCARGA': se captura numero de proveedor + periodo, se resuelve (rfc, nombre) contra SQL al agregar -y se muestra el nombre, para cazar un dígito mal tecleado antes de encolar-, y se descargan uno por uno con estado y tiempo por fila. Piezas: automation_costos/cola_descarga.py (modelo y persistencia, sin Tk ni Playwright, probable solo); ui.tabla() (ttk.Treeview con la paleta PRGX, porque customtkinter no trae tabla); ui.tarjeta(span=) para ocupar el ancho completo; database.resolver_proveedor() devuelve (rfc, nombre) y resolver_rfc queda como envoltura suya. En cpa_vision.request_vendor_master_batch se agregaron DOS parametros OPCIONALES: progreso (avance por proveedor) y cancelado (se consulta entre proveedores, nunca a media descarga). Sin ellos el comportamiento por terminal es identico al de antes. La cola se le entrega al motor como un Excel temporal RFC/FECHAS, asi que no se reimplementa nada del scraping: reintentos, deteccion de Sin valores, metricas e inventario siguen siendo del motor. El periodo se valida con el MISMO _parse_years del CLI. 'sin_valores' cuenta como terminado, no como error. La cola persiste en logs/cola_descarga.json y sobrevive al cambio de tema. Documentado en docs/GUI.md 5b.

---

### 2026-08-24 12:18:12 — [CÓDIGO] La descarga de CPA Vision va sin ventana por omision

config.CPA_VISION_HEADLESS pasa de default '0' a '1'. La casilla 'Descargar sin ventana (en segundo plano)' de la GUI lee ese valor, asi que ahora aparece marcada al abrir. Motivo: el uso real son lotes largos que corren de noche o mientras el auditor trabaja en otra cosa, y la ventana del navegador robaba el foco. Se puede volver a ver el navegador con CPA_VISION_HEADLESS=0. OJO: el mismo default aplica al CLI (cpa-request-download y cpa-batch-vendors); las 212 h de historico de descargas se corrieron con ventana, asi que si aparece cualquier rareza en el portal, lo primero a descartar es el modo headless.

---

### 2026-08-24 10:30:16 — [CÓDIGO] RFC en mayusculas tambien en la descarga individual

cpa_vision.request_download_and_wait normalizaba el RFC solo con .strip(), mientras que el camino por lotes (_load_vendor_master_jobs) ya hacia .strip().upper(). El RFC termina siendo el nombre de la particion Hive 'rfc=' del Parquet, y cruce_cpa lo busca en mayusculas contra esa carpeta: una descarga individual escrita en minusculas habria creado 'rfc=djb850527f30' y el cruce no la encontraria, sin error, simplemente sin cruzar nada. Se agrego .upper() en las dos entradas (parametro/config y el input() interactivo, que es el origen mas probable de minusculas). Auditadas las 475 carpetas del acervo: ninguna traia minusculas, asi que no hay datos que reparar. IMPORTANTE: no se normaliza quitando no-alfanumericos como se hace con las facturas, porque 4 RFC legitimos llevan '&' (B&S730507563, C&D640131SR3, J&J920909AV8, M&M030307AW2) y el SAT tambien admite 'N con tilde'; ese filtro los romperia.

---

### 2026-08-19 14:19:33 — [CÓDIGO] reporte_cruce.py acepta --excluir para separar los gigantes

De los 70 proveedores con entregable, solo CUATRO (76034 Pepsico 6.5M, 392811 Sigma 5.8M, 391250 Arca 1.6M, 73692 Celaya 1.1M) se llevan 3.4 de las 3.9 horas estimadas de reconstruccion; los otros 66 juntos son 35 min. Sin una forma de excluirlos habia que pegar 66 numeros a mano en --vendors. Con --excluir se corre primero lo liviano y se deja lo pesado para cuando la maquina este libre. Estimacion calibrada con la prueba real de FRABEL: 522,610 renglones en ~7 min.

**Archivos:** `scripts/reporte_cruce.py`

---

### 2026-08-19 14:13:17 — [CÓDIGO] Las metricas del cruce se guardan solas en cada ejecucion (terminal y GUI)

Peticion de Oscar tras la consulta de Monica: estandarizar que el resumen del cruce quede en un Excel y se actualice solo. Nuevo automation_costos/metricas_cruce.py (dentro del paquete, asi viaja en el .exe): almacen append-only Historico_Cruce_CPA.parquet + Reporte_Cruce_CPA.xlsx derivado, ambos junto a los entregables. Mismo patron que el reporte de diferencias: nunca lanza, y el Excel se escribe a un temporal que se mueve encima para que si esta abierto el bueno quede intacto. Dos hojas: 'Cobertura por proveedor' con la ejecucion MAS RECIENTE de cada uno, e 'Historico de ejecuciones' con todas -asi se ve como sube la cobertura conforme entran mas descargas de CPA-. Las columnas 'Difieren en IVA/IEPS' se ocultan de la hoja principal a proposito: son control tecnico y difieren SIEMPRE que la factura mezcla tasas, leidas sin contexto parecen una alarma. ENGANCHES: (1) pipeline.generar_salida_proveedor, el camino normal; (2) pipeline_streaming para los gigantes, donde hay un ResultadoCruce por trimestre y se suman con fila_desde_varios -el acumulador va como parametro opcional 'metricas' y NO como valor de retorno porque _salida_intervalo se llama dos veces, una por pasada, y contaria doble-; (3) el boton Cruzar de la GUI y (4) el subcomando cpa-cruce, ambos marcados con Origen 'cruce manual' para distinguirlos de una ejecucion con entregable. scripts/reporte_cruce.py ahora tambien alimenta ese mismo historico (una fila por proveedor, Origen 'reconstruido') para que no haya dos archivos con la misma informacion; se puede omitir con --sin-consolidar. Verificado el ciclo completo con resultados simulados: la hoja principal se queda con la ejecucion nueva y no con la vieja, el historico conserva ambas, y la suma de los 3 trimestres del gigante cuadra exacto (240,300 cruzados y 1,500,000 celdas). Todo compila, CLI e imports OK.

**Archivos:** `automation_costos/metricas_cruce.py`, `automation_costos/pipeline.py`, `automation_costos/pipeline_streaming.py`, `automation_costos/app.py`, `main.py`, `scripts/reporte_cruce.py`

---

### 2026-08-19 14:04:01 — [CÓDIGO] Reporte en Excel con las metricas del cruce, tambien para los proveedores ya ejecutados

Peticion de Monica (2026-08-19): el mensaje que la aplicacion muestra al terminar el cruce ('Celdas vacias rellenadas: N') se pierde al cerrar la app, y pregunta si queda guardado por proveedor. Verificado en app.py: _log solo encola el texto para pintarlo en la ventana, no escribe a disco. Nuevo scripts/reporte_cruce.py -> outputs/Reporte_Cruce_CPA.xlsx con dos hojas: Resumen por proveedor y Detalle por proveedor-anio. Lleva las mismas cifras del mensaje (renglones, cruzados por serie y por folio, % de cruce, celdas rellenadas, CFDI en conflicto, discrepancias IVA/IEPS) mas la cobertura EDI antes/despues y los renglones ganados. SIRVE RETROACTIVAMENTE sin abrir los Compras ya generados -son 122 archivos y 20.4 GB de Excel, releerlos tardaria horas-: el cruce se recalcula en memoria desde SQL + Parquet, que es lo que ya hace beneficio_cpa.py, solo que ese DESCARTA el ResultadoCruce y aqui se conserva, que es el objeto con todas las metricas. Es resumible: guarda el avance en CSV despues de cada proveedor. Probado con FRABEL 7112 (522,610 renglones, 6 anios, ~7 min): 364,596 cruzados (69.8%), 2,440,219 celdas rellenadas, cobertura EDI 37.9% -> 70.8% (+32.9 puntos). Pendiente de decidir con Oscar: los proveedores gigantes (Pepsico, Sigma, Arca) pueden tardar horas o no caber en memoria por este camino.

**Archivos:** `scripts/reporte_cruce.py`

---

### 2026-08-18 14:52:14 — [CÓDIGO] Carpeta logica_explicada/ para Data Services y Audit Tools

Peticion de Oscar tras la reunion con Data Services, Audit Tools y Hector: ellos van a REPLICAR la logica en SQL Server y necesitan entenderla, pero los modulos de produccion no se dejan leer por alguien de fuera (nombres tecnicos, comentarios en ingles, optimizaciones que tapan la regla). Nueva carpeta logica_explicada/ con una version DIDACTICA de los cuatro modulos nucleo, mas un README con el orden de lectura, el diagrama del flujo y el vocabulario minimo. Se reescribieron con nombres en español y descriptivos (costo_unitario_facturado en vez de ctonto_edi), comentarios que explican el POR QUE de cada regla, las optimizaciones quitadas (en_sitio, chunks, duckdb) porque estorban para entender, notas 'En SQL Server' con el equivalente aproximado, y ejemplos numericos completos. Se explican los puntos donde es facil equivocarse al replicar: por que 'cruzo' se mide por PRESENCIA y no por valor distinto de cero, por que el total pagado es MAXIMO y no SUMA, por que los impuestos se multiplican en cascada, por que MR8M y KG-14 usan llaves distintas, por que el KG exige XREF3 que empiece en 14, y el reparto en cascada que nunca deja diferencia negativa. NO se toco ningun modulo de produccion: verificado con git, cruce_cpa.py, calculations.py y ajustes_pagos.py sin cambios. Cada archivo declara a que modulo real corresponde y advierte que la fuente de verdad es produccion. Los cuatro compilan. 1,310 lineas en total.

**Archivos:** `logica_explicada/README.md`, `logica_explicada/01_cruce_cpa.py`, `logica_explicada/02_calculo_auditado.py`, `logica_explicada/03_ajustes_pagos.py`, `logica_explicada/04_validacion_condiciones.py`

---

### 2026-08-18 13:44:51 — [DATO] Auditadas las dos guias Word contra el codigo: correctas, con dos huecos que se cerraron

Peticion de Oscar: revisar si Guia_Columnas_Compras.docx y Guia_Validacion_Condiciones.docx siguen al dia con la logica del cruce. Se comparo tabla por tabla contra el codigo, no a ojo. RESULTADO: lo que documentan esta CORRECTO. Verificado exacto: las 8 columnas copiadas del CFDI coinciden con COLUMNAS_COPIADAS de cruce_cpa; factem_edi<-fact_empaq; las 2 calculadas (ctobto_edi, impart_edi) y sus formulas coinciden con _calcular_derivadas; las 2 de control (impiva_edi_formula, imieps_edi_formula) con _validar_importes; las 2 pasadas del cruce (serie+folio principal, solo digitos de respaldo) y las 2 reglas de seguridad; las 10 columnas de auditoria con calculations.py incluida imp_aud = cto_aud x can_rec x (1+iva_aud) x (1+ieps_aud) y la bandera cruzo_cpa. En la Validacion: Consolidado 15/15, Detalle 21/21 y las 6 columnas de ajuste cuadran con el codigo; la unica diferencia de la hoja Ajustes es cosmetica (la guia agrupa 4 columnas en una fila). Tampoco documentan ninguna de las 10 columnas retiradas del Compras el 2026-08-14. HUECOS CERRADOS, los dos en la guia de Compras: (1) no explicaba la ESTRUCTURA del archivo -una hoja por año, la hoja Pendientes_EDI, y que en proveedores grandes se parte en un archivo por año cortando en limites de año mientras la Validacion sigue siendo uno solo-; (2) no mencionaba el periodo en el encabezado. Ambas guias regeneradas. Los PDF siguen siendo del 2026-07-24: se exportan a mano desde Word.

**Archivos:** `scripts/generar_guia_columnas.py`, `scripts/generar_guia_validacion.py`

---

### 2026-08-18 13:36:06 — [CÓDIGO] Documentada la generacion de la Validacion de Condiciones (hueco de documentacion)

Pregunta de Oscar sobre si el cruce y la generacion de la Validacion ya estaban documentados. Auditado: el CRUCE si lo estaba y bien (MAPEO_CRUCE_CPA_COMPRAS.md como especificacion de negocio y CRUCE_IMPLEMENTACION.md como implementacion), pero la VALIDACION no tenia su documento de implementacion equivalente: estaba repartida entre las reglas de LOGICA_NEGOCIO y la guia en Word del auditor, sin un lugar que explicara el codigo. NUEVO docs/VALIDACION_IMPLEMENTACION.md: donde encaja en el pipeline y por que se escribe ANTES que el Compras, las 4 hojas, el filtro de folios que califican (los dos caminos de _has_audit_concepts y por que es prefiltro vectorizado y no bucle), el umbral de 1 peso y que sigue pendiente con negocio, los ajustes MR8M/KG-14 con sus llaves y el corte 3/31/2026, los TRES motores de escritura (openpyxl / rapida / streaming) y cual pinta titulos, el periodo en el titulo, los efectos colaterales al terminar (reporte consolidado y soportes) y el flujo del auditor con validate. Enlazado desde el indice docs/CLAUDE.md. Cifras verificadas contra el codigo, no de memoria: umbral 1.0, 32 columnas fuente, consolidado 15 -> 21 con ajustes, detalle 21, compras 95, PERIODO_FIN 3/31/2026. Ademas se reviso que las guias en Word no documenten las 10 columnas retiradas del Compras el 2026-08-14 (no lo hacen) y se agrego a Guia_Validacion_Condiciones una seccion sobre el periodo en el encabezado, advirtiendo que los años que no aparecen NO se revisaron. Ambas guias regeneradas.

**Archivos:** `docs/VALIDACION_IMPLEMENTACION.md`, `docs/CLAUDE.md`, `scripts/generar_guia_validacion.py`

---

### 2026-08-18 10:22:28 — [CÓDIGO] revisar_cpa resuelve el RFC contra SQL en vez de depender de 5 fijos

Sin esto el plan completo abortaba en seco: revisar_cpa solo conocia los 5 RFC del bloque 1 (RFC_POR_PROVEEDOR) y el plan tiene 246 proveedores con cruce, asi que cualquier tanda nueva moria con 'no se pudo resolver su RFC' antes de ejecutar nada. Ahora los que faltan se resuelven contra SQL en una sola conexion (medido: 1.8 s los dos primeros) buscando cnpj en la base que tenga movimientos del proveedor, y se cachean en rfc_por_proveedor.csv para que las tandas siguientes no vuelvan a pagarlo. Solo se resuelven los del bloque en curso, no los 246. Si SQL no responde, se avisa y la barrera sigue funcionando con lo que haya en cache (no se pierde la proteccion: los que queden sin RFC siguen reportandose como problema). Verificado sobre el primer bloque real de 20: 12 llevan cruce, se resolvieron los 12 y la barrera pasa -todos tienen sus años en el Parquet-, asi que la corrida ya no aborta.

**Archivos:** `scripts/ejecutar_bloque1.py`

---

### 2026-08-18 10:18:07 — [BUG] La deteccion de 'ya entregado' fallaba con los entregables que llevan sufijo de periodo

Hallazgo de Oscar: 3M (80622) aparecia como pendiente aunque ya se habia ejecutado. Causa: ya_hecho reconstruia el nombre exacto del archivo (Validacion_<num>_<nombre>.xlsx) a partir del nombre de la PLANEACION, y fallaba de dos formas verificadas en disco: (1) 3M tiene sus entregables con sufijo de periodo -Validacion_80622_3M MEXICO SA DE CV_2020-2024.xlsx y _2025.xlsx-, ninguno con el nombre exacto esperado; (2) el nombre de la planeacion no siempre coincide con el vndname de SQL con el que se creo la carpeta (acentos, cortes, espacios). Nueva funcion entregados(): escanea UNA vez la carpeta de entregables e indexa por NUMERO de proveedor (regex ^(\d+)_ sobre el nombre de carpeta + glob Validacion_*.xlsx, ignorando los temporales ~$ de Excel). Es inmune al nombre y al sufijo, y cambia cientos de exists() sobre unidad de red por un solo escaneo. Resultado: los detectados pasan de 47 a 48 y el primer bloque ya no arranca en 3M sino en SALMI (64840). Verificado: 51 proveedores con Validacion en disco, 48 estan en el plan y 3 no (885, 19311, 312231, que no tienen accion ejecutable); ninguno de los 20 del bloque tiene carpeta en la ruta de entregables, ni siquiera sin Validacion.

**Archivos:** `scripts/ejecutar_bloque1.py`

---

### 2026-08-18 10:11:15 — [CÓDIGO] Los proveedores ya entregados salen del plan ANTES de cortar el bloque

Hallazgo de Oscar al listar el primer bloque: de los 20 que traia, 5 ya estaban entregados (Pepsico, Nestle, Arca, Celaya, Selecta) y el ejecutor los metia al bloque para omitirlos dentro del bucle. Efecto: un --batch-size 20 rendia 15 proveedores de trabajo real y el --start-index seguia contando huecos, asi que el usuario tenia que adivinar cuanto avanzar. Ahora se filtran antes del corte, en main(): el bloque siempre rinde el batch-size completo de pendientes. La comprobacion es contra el DISCO (existe su Validacion, via ya_hecho), no contra la columna 'entregado' del Excel, que queda vieja en cuanto corre la primera tanda -mismo criterio de la regla 4.4: validar contra la realidad, no contra el archivo-. --rehacer los vuelve a incluir (verificado: con --rehacer reaparecen los 3 primeros). --solo de un proveedor ya entregado ahora dice que esta entregado y sugiere --rehacer, en vez del confuso 'no esta en el plan'. Se conserva el chequeo dentro del bucle como red de seguridad. Verificado con --listar: 47 entregados fuera, bloque 0-19 arranca en 3M (80622) con 20 pendientes reales; el plan del bloque 1 original sigue funcionando (42 de 43 ya entregados, queda 1).

**Archivos:** `scripts/ejecutar_bloque1.py`

---

### 2026-08-18 09:56:53 — [CÓDIGO] El ejecutor corre por bloques: --start-index / --batch-size / --orden

Peticion de Oscar: con 713 proveedores pendientes (~25 h estimadas) no sirve una sola corrida derecho. Misma convencion que cpa-batch-vendors para no tener dos vocabularios: --start-index y --batch-size. Nuevo --orden con dos modos: 'tamano' (el de siempre, chicos primero, DEFAULT para no cambiar el comportamiento del bloque 1) y 'prioridad', que respeta el orden del plan y es el que se quiere por bloques -el bloque 1 deben ser los 20 mas prioritarios, no los 20 mas chicos-. El corte se aplica DESPUES de ordenar, sobre un indice estable 'pos' que se fija con reset_index en cargar_plan, para que el numero sirva igual en la corrida siguiente. Al terminar, el resumen imprime el --start-index de la proxima tanda y cuantos quedan por delante, asi no hay que contar a mano. Bloque vacio (start-index mayor que el plan) aborta con mensaje explicito en vez de correr en silencio. Verificado con --listar, que no ejecuta nada: bloques 0-4 y 5-9 por prioridad, el borde (755 pidiendo 20 y solo quedan 5), el fuera de rango, que sin --batch-size sigue tomando los 760, y que el plan del bloque 1 original y --solo siguen funcionando igual.

**Archivos:** `scripts/ejecutar_bloque1.py`

---

### 2026-08-18 09:17:26 — [CÓDIGO] Plan de ejecucion completo + el periodo ejecutado se anuncia en los titulos

Peticion de Oscar. (1) NUEVO scripts/gen_plan_ejecucion.py -> plan_ejecucion.xlsx: lee la columna accion de la planeacion y define QUE proveedores ejecutar y en que anios. Alcance: 760 proveedores / 1,815 pares prov-anio (1,399 Ejecutar + 416 Descargar/Ejecutar), 42.0M renglones; 246 llevan cruce CPA, 514 sin CPA, 47 ya entregados, 6 por el camino de trimestres. Ordenado por Prioridad_Proveedores_CPA. El volumen sale de reg_compras del propio archivo, sin SQL (760 COUNT tardarian horas). Mismas columnas que consume ejecutar_bloque1 mas prioridad/periodo/con_huecos/entregado. (2) 9 proveedores traen anios SALTEADOS y F_COMPRAS se pide por rango continuo, asi que el anio de en medio -accion 'ninguna': ya terminado o cobertura >=90%- llegaba al entregable y se volveria a reclamar. Decision de Oscar: se recorta. Nuevo parametro anios en pipeline.generar_salida_proveedor y flag --anios en cpa-salida; reusa _mascara_anios, que devuelve None cuando no recorta y asi no copia el DataFrame en los 751 de periodo continuo. ejecutar_bloque1 acepta --plan y agrega --anios solo a los 9 con huecos. (3) Los titulos del Compras y de la Validacion dicen el periodo: consecutivos '2020-2025', con huecos '2020, 2022, 2025', uno solo '2025'. Nuevas utils.formatear_periodo y utils.anios_de_compras; el periodo se deriva de los renglones que QUEDARON (rcvdt), no del rango pedido a SQL, para que el titulo nunca prometa un anio que el archivo no trae. En Compras se calcula sobre el libro completo, no sobre el chunk de la hoja con titulo, que al partir por anios seria solo el primero. La Validacion no lo tenia; ahora sale en las 4 hojas por las dos rutas (openpyxl y xlsxwriter/streaming). write_validation_rapida no pinta titulos, asi que no aplica. Verificado generando libros reales y releyendo la celda del titulo en los 3 casos, la mascara de anios con 5 combinaciones, formatear_periodo con 8, y los comandos que genera el ejecutor para los 9 con huecos y 3 sin huecos.

**Archivos:** `automation_costos/utils.py`, `automation_costos/validation_exporter.py`, `automation_costos/excel_exporter.py`, `automation_costos/pipeline.py`, `main.py`, `scripts/gen_plan_ejecucion.py`, `scripts/ejecutar_bloque1.py`, `docs/LOGICA_NEGOCIO.md`

---

### 2026-08-16 18:48:27 — [DATO] Cierre del objetivo <90% de Monica: 397/398 pares descargados

Lote final del 2026-08-15 (descarga_monica_pendientes.xlsx, 24 proveedores / 44 pares prov-anio): 23 OK, 0 errores, 1 sin valores; 19,596 filas nuevas en 1h 12m (3m 0s por proveedor). Validado contra el PARQUET, no contra el CSV: 43 de 44 pares en el acervo. Acervo general: 475 RFC, 1,208 pares RFC-anio, 87,760,780 conceptos, 10,116,257 CFDI, 1.9 GB. Complemento (solo <90%): 227 RFC, 397 pares, 7,122,851 conceptos, 613,748 CFDI, 140 MB. Ambos inventarios se regeneraron solos al cerrar el lote. El unico par faltante es IGU880227Q96 2023 (INDUSTRIAS GUACAMAYA, 44586), que el portal marca 'Sin valores': no hay CFDI, imposible por CPA Vision, va reportado a Monica junto con los 17 extranjeros sin RFC. Documentado en LOGICA_NEGOCIO 13.1 y actualizado ESTADO_ACTUAL (corte 2026-08-15, comando en PowerShell de una sola linea sin rutas -los defaults de config ya apuntan al acervo-, y como retomar un lote cortado con scripts/complemento_cpa.py + la columna excel_row). Siguiente paso: re-correr actualizar_plan_beneficio.py con el objetivo ya completo.

**Archivos:** `docs/ESTADO_ACTUAL.md`, `docs/LOGICA_NEGOCIO.md`

---

### 2026-08-16 18:44:20 — [BUG] downloaded_after_recovery se contaba como error en los dos resumenes

Hallazgo al revisar el lote de 24 de Monica del 2026-08-15: el resumen dijo 'con error: 2' (DET780215MV1, IEO890214JPA) y Oscar pregunto cuales habian fallado. Ninguno fallo: los dos traen estatus downloaded_after_recovery, es decir tropezaron y el reintento completo la descarga. Validado contra el PARQUET, no contra el CSV: 43 de los 44 pares proveedor-anio del lote quedaron en el acervo (DET 9 filas, IEO 1,593). Es el mismo defecto ya anotado en ESTADO_ACTUAL.md para METRICAS_TOTALES.txt (reportaba 76.5% de exito contando 47 recuperadas como error). Nuevo _ESTATUS_OK = {downloaded, downloaded_after_recovery}, aplicado en _resumen_batch y en actualizar_metricas_totales (donde ademas corrige 'Proveedores unicos OK', que subcontaba). Recalculado el resumen del lote con el CSV real: OK 23, sin valores 1, con error 0. El unico no descargado es IGU880227Q96 2023, que el portal marca 'Sin valores': no tiene CFDI, no es un fallo.

**Archivos:** `automation_costos/cpa_vision.py`

---

### 2026-08-15 14:19:35 — [CÓDIGO] Lote CPA: 'Sin valores' salta al siguiente proveedor en vez de gastar reintentos

Peticion de Oscar tras ver que IGU880227Q96 (primer proveedor del lote de 24 de Monica) terminaba con estatus 'Sin valores' en la pagina de Solicitudes. Ese estatus es un resultado DEFINITIVO del portal -no hay CFDI para ese RFC en el periodo-, pero el codigo lo trataba como cualquier fallo: agotaba los 2 intentos, reiniciaba el navegador y esperaba los max_wait_minutes completos en cada uno. Nueva excepcion SolicitudSinValores + regex _SIN_VALORES; se lanza en _wait_for_request_zip DESPUES de _first_ready_request_link, para que si el portal ya dio link mande el link. En el bucle del lote se captura antes del except generico: estatus propio 'sin_valores', sin reintento, sin reinicio de navegador y sin artefactos de depuracion; vuelve al formulario y sigue con el siguiente. Tampoco detiene el lote con --stop-on-error, porque no pasa por la rama de error. _resumen_batch y actualizar_metricas_totales lo cuentan como categoria aparte para no mandar al auditor a perseguir proveedores que no tienen nada. Verificado: py_compile, la regex contra 10 variantes de texto del estatus, y el resumen con un CSV de metricas de prueba (OK 1, sin valores 1, error 1).

**Archivos:** `automation_costos/cpa_vision.py`

---

### 2026-08-14 12:28:54 — [CÓDIGO] Compras se entrega con 95 columnas (se ocultan 10 intermedias)

Peticion de Oscar con archivo de referencia Compras_9647_FRABEL.xlsm. Se dejan de ESCRIBIR 10 columnas de trabajo: concaten, fante, facdecto, ctouni_sistema, ctontol, impaud, dpagar, imp, 'dif cto fac ctouni', ctontopza. Son restos de cuando el libro llevaba formulas de Excel; hoy cto_aud/imp_aud/debio_pagar_ne ya dicen lo mismo. El recorte es SOLO de escritura (nuevo excel_exporter.COLUMNAS_INTERNAS / COLUMNAS_SALIDA), no del calculo: concaten agrupa las hojas por anio y dpagar alimenta el debio-pagar por folio, quitarlas del calculo romperia el pipeline. Se recorta por posicion en cada renglon y no con df[COLUMNAS_SALIDA] para no copiar millones de renglones en proveedores grandes. Verificado el ciclo completo generar->releer->recalcular->validar con Serral 386029: 54.15, identico al entregable con 105 columnas. Coincide exacto con las 95 columnas del archivo de referencia.

---

### 2026-08-14 08:10:18 — [CÓDIGO] GUI: descarga sin ventana, boton Detener y rutas/fechas por defecto

Peticion de Oscar. 1) Casilla 'Descargar sin ventana (en segundo plano)' en la tarjeta CPA: pasa headless a CPAVisionSettings (el soporte ya existia, faltaba exponerlo). 2) Boton Detener con cancelacion COOPERATIVA: nuevo automation_costos/cancelacion.py (SenalCancelacion, CancelacionSolicitada, revisar). No se mata el hilo -dejaria Excel a medias y navegadores huerfanos-; la senal se revisa en el bucle de sondeo de _wait_for_request_zip, que es donde la descarga pasa las horas, asi que responde en segundos. El parametro cancelado es OPCIONAL en toda la cadena: sin el, comportamiento identico al anterior. 3) Salida por defecto = config.ENTREGABLES_DIR (X:\...\Proceso Validacion de condiciones) en vez de outputs/: con outputs/ la ETAPA 2 dejaba el paquete del proveedor fuera del acervo y creaba un reporte de diferencias suelto ahi. 4) Fechas por defecto 2020-01-01 a 2026-01-31 como constantes, no calculadas desde hoy. Nuevos widgets ui.casilla y ui.boton_peligro. Verificado construyendo la ventana de verdad. .exe reconstruido.

---

### 2026-08-13 14:34:36 — [BUG] F_APV2 se consultaba solo hasta 31-dic-2025: se perdian TODAS las devoluciones de 2026

Hallazgo de Monica en FRABEL 9647: la nota 2649467 tenia un KG-14 de 136,906.68 del 20-ene-2026 que no se aplicaba. Validado contra la base: la llave (proveedor+nota+tienda) SIEMPRE estuvo bien (StrNbr 5537, RcpNbr 2649467 casan exacto); el registro no se leia porque PERIODO_FIN era 12/31/2025. Solo en FRABEL se perdian 254 movimientos KG y 8.9M. Corregido a 3/31/2026, el ultimo corte de pagos recibido del cliente (indicacion de Monica) y cierre del periodo 2025. Verificado: el caso de Monica ahora cierra en 0.00. Se evaluo y DESCARTO un respaldo por factura para los KG sin nota/tienda: resultaron asientos globales (VIAJES BACK HAUL, DESCTO X MANIOBR, APORTACION ECOM, partidas de hasta -47M), cruzarlos por factura borraria diferencias reales. IMPACTO: todo entregable anterior a hoy sobrestima y hay que reejecutar.

---

### 2026-08-13 12:48:33 — [CÓDIGO] El complemento CPA se actualiza solo al cerrar cada lote, tambien desde el .exe

Peticion de Oscar: que al descargar un proveedor queden al dia las DOS carpetas y los DOS inventarios, con procesos separados. Antes solo se actualizaba el inventario de cpa_vision; el complemento era un script manual (y por eso se habia quedado con corte de un dia antes). Nuevo automation_costos/complemento_cpa.py (copia + inventario del complemento) enganchado en cpa_vision.py aparte del inventario general, cada uno en su try/except. El obstaculo era que el objetivo <90% EDI sale del Excel de planeacion + SQL, que el .exe no tiene: se resolvio persistiendolo en cpa_vision_complemento/_objetivo_edi_menor_90.csv, que escribe scripts/complemento_cpa.py y lee el paquete. Verificado que el modulo corre sin importar nada de scripts/ y sin SQL. Nuevo config.CPA_VISION_COMPLEMENTO_DIR. .exe reconstruido.

---

### 2026-08-13 11:40:30 — [BUG] Reporte de diferencias: manda Rejecucion_validacion_pagos + historico de montos

HALLAZGO de Oscar: 6 proveedores (Arca, Nestle, Celaya, Selecta, Pepsico, 3M) tienen su entregable BUENO en Rejecucion_validacion_pagos; los de sus carpetas normales se generaron ANTES de la regla MR8M/KG-14 y no traen hoja Ajustes, asi que sobrestimaban. El reporte tomaba los equivocados: 187.8 M de mas (solo Pepsico 160.6M vs 75.6M real). Ahora esa carpeta manda sobre las carpetas normales. Total corregido: 851,271,547.22 -> 663,485,884.05 a reclamar. 2) Nuevo Historico_Diferencias.parquet (append-only, en la raiz de entregables): anota un renglon por proveedor cada vez que sus cifras cambian, para que los ajustes del auditor no borren el monto original. Alimenta 3 columnas nuevas del Resumen (Monto inicial, Variacion vs inicial, Revisiones) y la hoja 'Historico de montos'. Verificado idempotente: correr sin cambios no agrega renglones.

---

### 2026-08-13 11:08:59 — [CÓDIGO] Reporte de diferencias: se cierra el hueco del flujo manual (validate)

Revisando la cobertura del enganche automatico aparecio que 'main.py validate' no actualizaba el reporte, y ese es justo el flujo en que el auditor corrige el Compras y regenera la Validacion (cuando los montos MAS cambian). Nueva funcion actualizar_desde_validacion(): deduce la raiz de entregables de la ruta (<raiz>/<carpeta>/Validacion_<carpeta>*.xlsx) y no hace nada si el archivo no tiene esa forma, para no sembrar reportes en carpetas sueltas. Enganchada en main.py validate. El boton 'Validar' de la GUI NO se engancha a proposito: escribe un archivo suelto en la carpeta de salida, fuera del arbol de entregables, asi que no alimenta el reporte.

---

### 2026-08-13 09:15:23 — [CÓDIGO] Reporte de diferencias: etiqueta y periodo de los proveedores 100% compensados

Hallazgo revisando por que 5 proveedores salian sin periodo: NO estaban sin diferencias, todas fueron anuladas por devoluciones KG-14/MR8M (3,787,583.77 detectados, 100% compensado). Se etiquetaban 'Sin diferencias', que se leia como 'no se les encontro nada'. Ahora dicen 'Compensado por devoluciones (nada que reclamar)' y su periodo sale de la fecha de pago de la devolucion, marcado como tal. 'Sin diferencias' se reserva para el cero real. Ademas el reporte ahora se escribe a un temporal y se mueve encima del destino: con el archivo abierto en Excel el bueno queda intacto y el mensaje dice que hacer. Totales: 1,020,510,983.18 detectados -> 851,271,547.22 a reclamar.

---

### 2026-08-13 08:40:23 — [CÓDIGO] Reporte consolidado de diferencias (proveedor, periodo, monto, concepto)

Peticion de Hector Saucedo (2026-08-13): un solo archivo de control con la diferencia de cada proveedor. Nuevo automation_costos/reporte_diferencias.py + scripts/reporte_diferencias.py. Genera Reporte_Diferencias_Consolidado.xlsx en la raiz de los entregables con 3 hojas: Resumen por proveedor, Por periodo y concepto, Detalle notas. Lee la hoja Consolidado de cada Validacion (no recalcula: cuadra al centavo con el entregable). Se actualiza SOLO al terminar cada proveedor (enganche en pipeline.generar_salida_proveedor y pipeline_streaming.generar_validacion_grande) y al cerrar un lote (ejecutar_bloque1). Es incremental por cache (archivo+fecha+tamano). Estado inicial: 50 proveedores, 380,295 notas, 851,271,547.22 a reclamar.

---

### 2026-08-12 22:40:12 — [CÓDIGO] Bloque 1 ejecutado: 43 de 43 entregados, con dos hallazgos

Corrida completa el 2026-08-12 de 14:45 a 20:16 (5h 31m): 41 OK, 0 fallos, 2 omitidos (25133 y 386029, que se habian corrido como prueba por la tarde y la reanudacion salto correctamente). VERIFICADO releyendo el disco, no el log: los 43 proveedores tienen carpeta con Compras y Validacion, ninguno vacio, 5.9 GB en total. Los soportes de CPA aparecen SOLO en los 5 con cruce (7112, 11914, 17222, 23873, 43398), que es la regla acordada. Tiempos: los 42 normales entre 0.2 y 22.7 min; Sigma 237.9 min (4 horas) por el camino de trimestres, con 5 archivos de Compras de 0.8 a 1 GB cada uno y una Validacion de 76 MB. HALLAZGO 1 - Procter 17222 cruzo muy bien: 175,546 de 191,018 renglones (91.9%), y solo 42 por la pasada de RESPALDO (la que ignora la serie y era el unico riesgo con RFC compartidos). 42 sobre 175 mil es despreciable, asi que ese riesgo queda cerrado con datos. HALLAZGO 2 - Grupo Carmi 43398 NO se pudo cruzar pese a estar marcado Descargar/Ejecutar2025: sus 8 renglones de compras de 2025 vienen SIN codigo de barras (0 de 8) y el unico codigo del CFDI tambien esta vacio; como la llave del cruce es codigo de barras + factura, ahi no hay nada que emparejar. No es un fallo del pipeline sino una limitacion del dato de origen; conviene avisarlo a negocio porque el plan esperaba un cruce que es imposible. BUG CORREGIDO detectado en la validacion: el gateo de soportes por usar_cpa se habia implementado solo en el camino en memoria, no en pipeline_streaming, asi que Sigma corrio --sin-cpa pero se llevo un ZIP de soporte de todas formas (618652). Se condiciono tambien en las dos llamadas de pipeline_streaming y se elimino el ZIP sobrante de la entrega. OJO para futuras verificaciones: el nombre de la carpeta lo pone el pipeline con el nombre real del proveedor que sale de SQL, no con el del plan; por eso 17222 aparecia como faltante al buscarlo por el placeholder 'PROCTER (fuera del archivo)' cuando en realidad estaba completo como '17222_PROCTER & GAMBLE MEXICO S DE RL DE'.

**Archivos:** `automation_costos/pipeline_streaming.py`, `scripts/ejecutar_bloque1.py`

---

### 2026-08-12 14:40:19 — [BUG] Cruce acotado por anio + barrera que impide entregar sin el CPA que el plan pide

Dos correcciones sobre la ejecucion del Bloque 1, ambas detectadas probando antes de lanzar. (1) CRUCE POR ANIO: 23873 y 43398 mezclan verbos entre sus anios (2025 es Descargar/Ejecutar, los anteriores solo Ejecutar). El pipeline corre un periodo completo de una vez, asi que activar el cruce les metia CPA tambien en los anios que el plan excluye. Se agrego el parametro anios_cruce a generar_salida_proveedor/_generar_salida_en_memoria y el flag --cruzar-anios al CLI: se parte el DataFrame por anio de rcvdt (que es por donde F_COMPRAS filtra el periodo), se cruza solo el subconjunto pedido y se reconcatena con sort_index para restituir el orden original. Cuando no hay recorte devuelve None y no parte nada, asi el caso normal no paga el costo. Ahora 43398 cruza solo sus 2 renglones de 2025 y deja intactos los 365 de 2020-2024, y 23873 solo sus 332 de 2025. Sub-bug encontrado al probar: Excel devuelve la celda '2025' como el numero 2025.0, y sin normalizar se generaba '--cruzar-anios 2025.0' (argparse type=int habria reventado) y ademas los 5 proveedores con cruce quedaban marcados como parciales al comparar '2025.0' contra '2025'. Se normaliza con _anios_texto(). (2) BARRERA DE CPA FALTANTE, el hallazgo grave: el driver lee config.CPA_VISION_PARQUET_DIR, que ya apunta a la ruta nueva de X:, pero ESA copia es del 11-ago y los cinco proveedores que necesitan cruce se descargaron DESPUES; dos de ellos (GCA960122UD0 de 43398 y CEGM8802092Z8 de 23873) no estan ahi. La corrida de prueba de 43398 NO fallo: no encontro CPA, cayo en la rama de 'el Compras ya trae 96.8% de cobertura' y entrego Compras y Validacion SIN el cruce que el plan pedia, en silencio. Ese es exactamente el modo de fallo que no se puede permitir en un entregable. Se agrego revisar_cpa() al driver: antes de ejecutar nada verifica que cada proveedor con cruce tenga en el Parquet las particiones rfc/year que le tocan, y si falta alguna aborta listando cuales y recordando sincronizar. Verificado: detecta los 3 pendientes (17222 anio 2021, 43398 y 23873 anio 2025) y corta la corrida. Se borro el entregable de 43398 generado mal para que se rehaga con su cruce; los de 386029 y 25133 se conservan porque van --sin-cpa y su salida es correcta. PENDIENTE OPERATIVO: el robocopy de outputs/cpa_vision a la ruta de X: es ahora REQUISITO para ejecutar, no un paso cosmetico.

**Archivos:** `automation_costos/pipeline.py`, `main.py`, `scripts/ejecutar_bloque1.py`, `plan_ejecucion_bloque1.xlsx`

---

### 2026-08-12 14:28:08 — [CÓDIGO] Flag --sin-cpa: el cruce se hace SOLO donde la columna accion lo pide

Oscar corrigio un supuesto mio. Yo habia dicho que 40 de los 43 del Bloque 1 usarian datos de CPA en el cruce; el observo que si la columna accion dice solo 'Ejecutar', esa informacion de CPA no deberia usarse porque nunca se debio haber descargado. Tiene razon en el fondo: el umbral del 90% es un criterio de PRIORIZACION DE DESCARGAS, no una regla sobre que datos usar al calcular, pero dejar que el resultado dependa de que se alcanzo a bajar en un lote que ademas se detuvo a la mitad hace la corrida IRREPRODUCIBLE, y parte de ese dato entro por un error de alcance mio del dia anterior (21 proveedores bajados de mas). Se agrego el parametro usar_cpa (default True, comportamiento anterior intacto) en generar_salida_proveedor, _generar_salida_en_memoria, generar_salida_proveedor_por_anios, generar_validacion_grande y generar_compras_grande, y el flag --sin-cpa en los tres subcomandos del CLI. El punto unico del camino por trimestres es _salida_intervalo, asi que ahi se implemento una sola vez para los tres. Con usar_cpa=False NO se lee el Parquet aunque tenga datos del RFC, y TAMPOCO se copian los ZIP de soporte: el entregable no se apoya en ningun CFDI y meterlos sugeriria lo contrario a quien lo revise. scripts/ejecutar_bloque1.py decide solo, leyendo la columna verbos del plan: 5 proveedores con cruce (17222 Procter, 43398, 23873, 11914 Haleon, 7112 Frabel) y 38 sin CPA. EXCEPCION DOCUMENTADA: 23873 y 43398 mezclan ambos verbos entre sus anios (2025 es Descargar/Ejecutar, los demas Ejecutar); como el pipeline corre un periodo completo de una vez se les deja el cruce activo y alcanza tambien a sus anios 'Ejecutar', pero son 914 renglones entre los dos. OJO al leer el plan: 7112 y 9647 son la MISMA empresa (Frabel) con distinto numero, y quedan con trato distinto -7112 con cruce, 9647 sin- porque asi lo dice su accion respectiva. VERIFICADO con 25133 Pactech, que SI tiene CPA en el parquet (years 2024 y 2025): con el flag el log dice 'Sin cruce con CPA Vision' y sale 0 ZIP de soporte, o sea el flag de verdad ignora el dato. SIGMA: se confirma por trimestre, no por anio. Su cuenta real en SQL para 2025-01-01..2026-03-31 es 7,140,231 renglones (no 5.8M como decia la planeacion, que no contaba el arrastre a 2026); como es UN SOLO anio, partir por anio no partiria nada y daria un archivo de ~4 GB con 7 hojas de continuacion. Por trimestre son 5 archivos de ~1.4M cada uno, que aun asi llevan 2 hojas cada uno.

**Archivos:** `automation_costos/pipeline.py`, `automation_costos/pipeline_streaming.py`, `main.py`, `scripts/ejecutar_bloque1.py`

---

### 2026-08-12 14:02:05 — [BUG] El pipeline abortaba en proveedores que no necesitan CPA + driver del Bloque 1

Al preparar la ejecucion del Bloque 1 se probo primero con Laboratorios Serral (386029, 191 renglones) porque era el caso dudoso: proveedor marcado 'Ejecutar' sin datos en el parquet. Fallo con 'ValueError: El RFC LSE071206IX6 no tiene datos en el dataset Parquet' (pipeline.py:123). La guarda era demasiado estricta: hay proveedores que la planeacion marca Ejecutar y NO Descargar justamente porque su cobertura EDI ya viene alta de origen y no hay nada que bajar de CPA; abortar ahi impedia generar un entregable perfectamente valido. Afectaba a 3 de los 43 del bloque: 1256 (99.87% EDI), 312231 Abbott (96.24%) y 386029 Serral (98.95%). CORRECCION: si no hay CPA se mide la cobertura EDI del propio Compras con _cobertura_edi(); si supera el 90% —el mismo umbral con el que la planeacion decide si hay que descargar— se continua sin cruce y se deja dicho en el log; si NO lo supera se sigue abortando, porque ahi la falta de CPA si es un problema real (parquet equivocado, RFC mal resuelto o descarga pendiente) y la Validacion saldria sin sustento. DOS ERRORES PROPIOS detectados al implementar, ninguno llego a ejecutarse: (a) el helper usaba pd.to_numeric pero pandas NO esta importado en pipeline.py, habria sido un NameError en ejecucion; se cambio por to_number de utils, que es el idiom del proyecto; (b) mas abajo el codigo hacia prepare_compras_dataframe(cruce.df) y con cruce=None eso era un AttributeError, asi que se introdujo la variable  que toma cruce.df o el raw segun haya habido cruce. VERIFICADO: Serral corre completo en 0.6 min, deja Compras y Validacion en su carpeta, reporta '97.0% de cobertura EDI (no habia nada que cruzar)' y 0 ZIP de soporte. NUEVO scripts/ejecutar_bloque1.py: driver que lee plan_ejecucion_bloque1.xlsx, corre cada proveedor en su PROPIO proceso (memoria liberada entre uno y otro, un fallo no arrastra al resto), es resumible (omite si la Validacion ya existe), aplica el cierre 2026-03-31 cuando el ultimo anio es 2025 (reunion 008) y rutea a los comandos por trimestre los proveedores de mas de 1.5M renglones. En este bloque el unico gigante es Sigma con 5,803,242 renglones (77% de todo el volumen); los otros 42 suman 1.7M. Salida en 'X:\...\Proceso Validacion de condiciones (Oscar Pineda)', una carpeta por proveedor con sus soportes, igual que Arca.

**Archivos:** `automation_costos/pipeline.py`, `scripts/ejecutar_bloque1.py`, `plan_ejecucion_bloque1.xlsx`

---

### 2026-08-12 12:11:28 — [CÓDIGO] CPA Vision sale del repo: una sola raiz configurable + inventario automatico al cerrar cada lote

Pedido de Oscar y de su jefe. (1) RUTA UNICA: el acervo de CPA Vision deja de vivir en outputs/ del proyecto y pasa a 'X:\...\Proceso Validacion de condiciones (Oscar Pineda)\cpa_vision', que es la carpeta que consultan los auditores y donde Oscar copiaba todo a mano. Se agrego config.CPA_VISION_DIR (raiz), CPA_VISION_DOWNLOAD_DIR (los ZIP, = la raiz) y CPA_VISION_PARQUET_DIR (<raiz>/parquet), las tres con variable de entorno para moverlas sin tocar codigo. CLAVE: se apuntaron TAMBIEN los seis scripts que tenian la ruta quemada (gen_lote_monica, beneficio_cpa, validar_formulas_impuesto, correr_validaciones_grandes, piloto_cruce, metricas_totales) a config, porque si solo se cambiaba la GUI el dataset quedaba PARTIDO: gen_lote_monica seguiria midiendo cobertura contra outputs/ y reportaria como pendientes proveedores ya bajados, mandando a redescargar horas de portal. (2) La GUI expone la carpeta de descargas como campo editable 'Descargas CPA' con boton Elegir, junto al de Parquet, y la pasa a descargar_cpa_proveedor. (3) INVENTARIO AUTOMATICO: nuevo automation_costos/inventario_cpa.py; request_vendor_master_batch lo llama al terminar el lote, justo despues de actualizar_metricas_totales, y deja Inventario_CPA_Vision.xlsx dentro de la carpeta de cpa_vision. No lanza nunca (actualizar_inventario traga la excepcion): si el Excel esta abierto o falta memoria no puede tumbar un lote de horas ni ocultar que las descargas si se hicieron. Tambien queda scripts/inventario_cpa.py para regenerarlo a demanda. HALLAZGO: el inventario que se venia armando A MANO SOBRECONTABA. Un mismo RFC puede tener dos descargas con anios que se solapan y se sumaban las dos; medido en Pepsico CPM110719SG3, la solicitud 619617 trae 2020-2025 (13,801,868 filas) y la 619939 solo 2025 (2,162,606 ya contenidas en la primera), y el archivo viejo reportaba 15,964,474, contando 2025 dos veces. El generador nuevo deduplica por (rfc, anio) eligiendo el request_id de mayor cobertura, que es el MISMO criterio de cruce_cpa._CTE_ELEGIDO, asi que el inventario y el cruce ya cuentan igual. Afecta a 16 RFC. Probado sobre el parquet actual: 84 segundos, 397 RFC con datos, 87,286,669 conceptos y 10,039,645 UUID. PENDIENTE OPERATIVO: hay que MOVER outputs/cpa_vision (5.1 GB, 1.9 de parquet y 429 ZIP) a la ruta nueva cuando termine el lote de 34 que esta corriendo; hasta que se mueva, los scripts miran una carpeta que no existe.

**Archivos:** `config.py`, `automation_costos/inventario_cpa.py`, `automation_costos/cpa_vision.py`, `automation_costos/app.py`, `scripts/inventario_cpa.py`, `scripts/gen_lote_monica.py`

---

### 2026-08-11 20:05:01 — [CÓDIGO] Arca 391250: Validaciones por anio acotadas a la lista VF mayor a 20MX (caso aislado)

Pedido puntual de Oscar: seis Validaciones de Condiciones de Arca, una por anio, recortadas a los 75,717 folios de 'VF mayor a $20MX Dis Arca.xlsx', con una columna Trimestre nueva al final del Detalle. Script scripts/arca_validacion_por_anio.py, en dos fases (--extraer arma un cache Parquet por trimestre, --generar escribe los Excel) para no releer 7 GB cada vez que se ajuste el formato. DECISIONES DE OSCAR: el Resumen suma 'Diferencia Ajustada' (119.38M neta de devoluciones) y no 'Diferencia' (122.35M bruta); el Consolidado conserva sus 3 columnas de trabajo (Concatenar, Cruce con NE, Diferencia NE), o sea 24 columnas. El Consolidado NO se recalcula: el archivo de Oscar YA es un Consolidado con las 21 columnas del formato, asi que se reparte por anio y se escribe tal cual; recalcularlo solo podria introducir diferencias contra lo que el ya reviso. HALLAZGO 1 - el anio y el trimestre salen de rcvdt, no de podt: se verifico leyendo el 2020-T1 que las fechas de recibo caen exactas dentro del trimestre (2020-01-02..2020-03-31) mientras las de pedido se salen (2019-12-29), o sea F_COMPRAS filtra por fecha de recibo y por eso es rcvdt quien decide en que archivo trimestral vive cada renglon. HALLAZGO 2 - COLISION DE FOLIO, el bug importante: el folio es prefijo+tienda+nota SIN fecha y los numeros de nota se reutilizan. El folio 11004035400243772 existe como nota recibida el 2023-09-28 (la del filtro) y otra distinta el 2024-03-27; cruzar solo por folio metia 40 renglones ajenos en el archivo de 2023, y por eso su Detalle mostraba un trimestre 2024-T1 imposible. Se detecto justamente por esa anomalia en la columna Trimestre. Desambiguacion: 2,027,860 de 2,027,905 renglones (99.998%) traen rcvdt identico al Fec Recibo del filtro y las 45 excepciones son exactamente los 4 folios repetidos, asi que la llave real es folio + fecha de recibo. Con el filtro puesto se descartan 45 renglones y ninguno legitimo. HALLAZGO 3 - tipos mezclados: prieps_edi trae el numero 0 y el texto '0' en la misma columna (unas celdas del exportador, otras editadas a mano), y pyarrow aborta al escribir Parquet; normalizar_tipos() fija un tipo por columna y se aplica al escribir y al leer. RESULTADO VERIFICADO releyendo los seis Excel entregados: 2020 22,950 folios / 591,198 renglones / 37,841,272.55; 2021 31,511 / 826,496 / 70,523,860.78; 2022 15,796 / 432,491 / 9,275,633.12; 2023 2,002 / 58,189 / 615,742.21; 2024 2,081 / 69,462 / 756,296.55; 2025 1,377 / 50,024 / 370,371.19. Cero folios sin detalle en los seis anios, ultima columna del Detalle = Trimestre en los seis, y la suma de los seis Resumenes da 119,383,176.40, identica al total del archivo de Oscar. Lectura de los 24 Compras: 2.4 h, 2,027,905 renglones extraidos de 11.5M leidos.

**Archivos:** `scripts/arca_validacion_por_anio.py`

---

### 2026-08-11 15:45:21 — [CÓDIGO] GUI: Validacion ya no arrastra el Compras del proveedor anterior, hilos seguros y empaquetado onedir

Tres correcciones sobre la GUI y el empaquetado. (1) ARCHIVO OBSOLETO EN VALIDACION: _validar prefiere archivo_recalculado sobre archivo_editado, pero archivo_recalculado no se limpiaba al cambiar de proveedor. Secuencia que rompia: se recalcula el proveedor A, luego se genera el Compras de B, se edita en Excel y se pide la Validacion sin recalcular -> generaba la Validacion de A, sin ningun aviso, con la unica pista del nombre del archivo de salida. Es un entregable INCORRECTO sostenido solo por que alguien se acuerde de pulsar Limpiar. Ahora _fijar_compras() descarta el recalculado cada vez que entra un Compras nuevo (quedan desincronizados por definicion) y se usa en los tres caminos que producen uno: extraer, salida completa y cruce. Ademas la tarjeta muestra una etiqueta viva ('Validará: <archivo> · recalculado/sin recalcular') conectada por trace_add a las dos variables, para ver el archivo elegido ANTES de hacer clic, y _validar deja escrito en la bitacora sobre que archivo corrio. Verificado reproduciendo la secuencia exacta del bug. (2) THREAD-SAFETY: seis .set() de StringVar se hacian desde el hilo trabajador (archivo_editado, archivo_recalculado, rfc, carpeta_parquet), y un .set() dispara la actualizacion del widget, o sea llamadas a Tcl desde el hilo equivocado; sintoma tipico 'RuntimeError: main thread is not in main loop', intermitente e irreproducible. IMPORTANTE - el primer intento de arreglo fue self.after(0, ...) y ESTABA MAL: after es a su vez una llamada a Tk (registra un comando en el interprete), asi que llamarla desde el hilo de fondo es el mismo problema; solo parece funcionar mientras el mainloop corre. Un test con app.update() en vez de mainloop lo destapo de inmediato. La via correcta es la cola: se agrego self.acciones (queue.Queue, thread-safe) que _procesar_mensajes vacia en el hilo principal, que es el patron que la bitacora ya usaba desde el primer dia. De paso se corrigio ui.Indicadores.estado, que hacia root.after por su cuenta con el mismo defecto: ahora aplica directo y quien orquesta hilos es el que encola. Verificado con 200 actualizaciones desde un hilo de fondo con mainloop real: 200 aplicadas en el hilo principal, 0 en otro hilo, 0 excepciones. (3) ONEDIR: el .spec compilaba en onefile, un contenedor de 123 MB que el bootloader extraia COMPLETO a un temporal en cada arranque. Ahora EXE con exclude_binaries=True + COLLECT: queda dist/AutomationCostos/ con el .exe de 10.9 MB y _internal/ al lado. Arranque medido de 3 segundos contra las decenas del onefile. build_release.py se ajusto para empaquetar la carpeta completa (el .exe solo no arranca sin _internal) bajo el prefijo AutomationCostos/ en el zip. AVISO: onedir es sensible al limite de ruta de Windows (~260 caracteres) porque las DLL viven en disco en la ruta donde se copie la carpeta; una prueba en una ruta muy larga fallo con 'DLL load failed while importing pyodbc: The filename or extension is too long'. En ruta corta arranca perfecto. Hay que documentar que la carpeta se coloque en una ruta corta.

**Archivos:** `automation_costos/app.py`, `automation_costos/ui.py`, `AutomationCostos.spec`, `scripts/build_release.py`

---

### 2026-08-11 13:56:38 — [BUG] El .exe escribia las salidas en la carpeta temporal de PyInstaller y las perdia al cerrar

config.py definia BASE_DIR = Path(__file__).parent, que en desarrollo es la raiz del proyecto pero DENTRO del .exe es sys._MEIPASS: la carpeta temporal que el bootloader de PyInstaller extrae al arrancar y BORRA al cerrar. Consecuencia: OUTPUT_DIR y LOG_DIR apuntaban ahi, asi que todo Compras, toda Validacion y la sesion guardada de CPA Vision (logs/cpavision_state.json) se escribian en un temporal y desaparecian al salir del programa. Nadie lo habia notado porque el .exe nunca se habia usado en serio; corriendo desde el codigo fuente el comportamiento es correcto. SOLUCION: separar las dos raices que se estaban confundiendo. RESOURCE_DIR = sys._MEIPASS cuando esta congelado (para lo EMPAQUETADO: templates/Soriana-Logo.png) y BASE_DIR = carpeta del sys.executable cuando esta congelado (para los DATOS DEL USUARIO: outputs, logs). Sin congelar las dos siguen apuntando a la raiz del proyecto, asi que el modo desarrollo no cambia en nada. Se actualizaron las 4 referencias a config.BASE_DIR/'templates' de excel_exporter, validation_exporter (x2) y exception_report para que usen RESOURCE_DIR; si se hubieran dejado en BASE_DIR el logo habria desaparecido de los entregables generados con el .exe. SEGUNDO BUG encontrado en el mismo punto: config.py hacia OUTPUT_DIR.mkdir() a nivel de modulo, o sea al IMPORTAR. Si el .exe se copia a una carpeta de solo lectura, a una unidad de red caida o a un USB retirado, ese mkdir lanza y mata el proceso ANTES de que exista la ventana; compilado con console=False el usuario no ve absolutamente nada, el programa simplemente no abre. Ahora _crear_carpeta() traga el OSError y se falla despues, al escribir, donde si hay como avisar. VERIFICADO EN EL BINARIO REAL, no en simulacion: se compilo, se copio AutomationCostos.exe solo a una carpeta limpia, se ejecuto y creo outputs/ y logs/ junto a si mismo. Tambien verificado que el modo desarrollo sigue resolviendo el logo y las salidas igual que antes.

**Archivos:** `config.py`, `automation_costos/excel_exporter.py`, `automation_costos/validation_exporter.py`, `automation_costos/exception_report.py`

---

### 2026-08-11 11:23:50 — [CÓDIGO] Actualizadas las dos guias Word: ajustes de pago MR8M/KG-14 y llave real del cruce

Los .docx eran del 24-jul y el codigo cambio despues. Se validaron ambos generadores contra el codigo fuente y se corrigieron. GUIA DE VALIDACION (5 desfases, el grave era omitir todo el bloque de devoluciones de las reuniones 006 y 007): (1) decia 'las 3 hojas del archivo' cuando ahora pueden ser 4, porque validation_exporter crea la hoja 'Ajustes' si el proveedor tiene devoluciones; (2) el Consolidado pasa de 15 a 21 columnas con Tipo Ajuste, Ajuste Pagos, Diferencia Ajustada, Compensado, Conteo No Compensados y Monto No Compensado; (3) el Resumen ya no suma 'Diferencia' sino 'Diferencia Ajustada' cuando existe; (4) faltaba el tercer caso del filtro: los folios que una devolucion compensada deja en ~0 SALEN del Consolidado y solo quedan en la hoja Ajustes; (5) no existia la distincion compensada (se resta) vs no compensada (no se resta, se marca alerta con conteo y monto), que es justo el acuerdo de la reunion 007. Se agrego seccion 4 completa con los dos tipos y sus llaves (MR8M por proveedor+factura, KG-14 por nota+tienda), las 6 columnas nuevas, las 12 de la hoja Ajustes, el paso 5 del calculo y la nota de que sin devoluciones o sin BD la Validacion sale igual que antes. GUIA DE COLUMNAS (1 error y 2 omisiones): el ERROR era describir la llave del cruce como 'se normaliza quitando la serie: FN-21226 -> 21226', que en realidad es solo la pasada de RESPALDO; la principal conserva la serie (FN-21226 -> FN21226) y cruza por codigo de barras + Serie+Folio, y el respaldo solo se aplica a lo que no cruzo. Se documentaron ademas las dos reglas de seguridad (solo rellena celdas vacias, los CFDI en conflicto se descartan) y las columnas de control impiva_edi_formula / imieps_edi_formula con el dato de los 66M de filas que justifica copiar en vez de despejar. Se aclaro que 'cruzo con CPA' significa PRESENCIA de uuid o ctonto_edi, no valor distinto de cero. PENDIENTE: los PDF siguen siendo los del 24-jul; hay que reexportarlos desde Word.

**Archivos:** `scripts/generar_guia_columnas.py`, `scripts/generar_guia_validacion.py`, `Guia_Columnas_Compras.docx`, `Guia_Validacion_Condiciones.docx`

---

### 2026-08-11 11:13:44 — [BUG] .venv recreado tras quedar a medias: no se puede correr 'venv --clear' con el entorno activado

Oscar corrio 'python -m venv .venv --clear' desde una terminal que tenia el entorno ACTIVADO (prompt con el prefijo (.venv)). Windows bloqueo el archivo en uso: [WinError 5] Access is denied sobre .venv\Scripts\python.exe. El --clear alcanzo a borrar el entorno viejo y a copiar python.exe y pythonw.exe, y murio ahi: quedo un .venv sin pyvenv.cfg, sin Lib y sin pip, mas un vba_extract.py sobreviviente del entorno anterior. SINTOMA VISIBLE: VS Code mostraba 'Error refreshing packages / Source: Python Environments', porque su extension de Python apuntaba a ese interprete roto; cualquier comando devolvia 'failed to locate pyvenv.cfg'. SOLUCION: borrar .venv por completo y recrearlo desde una terminal SIN el entorno activado (rm -rf .venv && python -m venv .venv), luego python.exe -m pip install --upgrade pip y -r requirements.txt. REGLA PARA LA PROXIMA VEZ: nunca recrear el entorno desde una shell donde este activado; usar 'deactivate' primero o una terminal nueva. Preferir borrar y recrear en vez de --clear. VERIFICADO tras la recreacion: pip.exe 26.2.1 y pyinstaller.exe 6.22.0 YA FUNCIONAN (era la secuela del renombre, queda cerrada), pyvenv.cfg apunta a Automation-Costos, importan docx duckdb pyarrow customtkinter pyodbc pandas playwright openpyxl xlsxwriter dotenv, config da ATL20AF2222SQ19 11004, main.py --help lista los 17 subcomandos y el parquet sigue con 350 RFC / 912 archivos, leidos con exito por el DuckDB nuevo. SUBIDAS DE VERSION al reinstalar sin pin: pyarrow 24.0.0->25.0.1, duckdb 1.5.3->1.5.5, pandas 3.0.2->3.0.5, playwright 1.59.0->1.62.0, pyinstaller 6.20.0->6.22.0, Pillow 12.2.0->12.3.0. Smoke test de lectura de Parquet OK (6,263 filas y 60 columnas en el archivo de muestra). PENDIENTE MENOR: requirements.txt usa rangos abiertos (>=), asi que cada reinstalacion puede traer versiones distintas; valorar pinear si aparece alguna regresion.

**Archivos:** `requirements.txt`, `docs/ESTADO_ACTUAL.md`

---

### 2026-08-11 10:59:51 — [BUG] requirements.txt no declaraba python-docx

python-docx estaba instalado en el .venv pero nunca se declaro en requirements.txt. Lo importan scripts/generar_guia_columnas.py y scripts/generar_guia_validacion.py, que producen Guia_Columnas_Compras.docx y Guia_Validacion_Condiciones.docx. Se detecto justo antes de recrear el entorno virtual: una instalacion limpia desde requirements.txt habria dejado esos dos scripts rotos con ModuleNotFoundError, sin ningun aviso previo. Agregado como python-docx>=1.1 (instalado: 1.2.0). El resto de los paquetes de primer nivel del entorno si coincide con requirements.txt: customtkinter 6.0.0, duckdb 1.5.3, openpyxl 3.1.5, pandas 3.0.2, pillow 12.2.0, playwright 1.59.0, pyarrow 24.0.0, pyinstaller 6.20.0, pyodbc 5.3.0, python-dotenv 1.2.2, xlsxwriter 3.2.9. Nota: pytest NO esta instalado ni declarado; test_cruce_cpa.py se corre directo con python test_cruce_cpa.py, no con pytest.

**Archivos:** `requirements.txt`

---

### 2026-08-11 10:58:52 — [CÓDIGO] Renombre a Costos CERRADO: checklist validado, build unificado en el .spec y artefactos regenerados

Se corrio el checklist completo de la entrada anterior desde la carpeta ya renombrada y paso entero: main.py --help dice 'Automation Costos - fase 1' con los 17 subcomandos, import automation_costos+config devuelve ATL20AF2222SQ19 11004, py_compile de scripts/ main.py config.py y test_cruce_cpa.py sin salida, outputs/cpa_vision/parquet accesible con 350 RFC, los 20 archivos del paquete siguen como R (rename) en git y el unico residuo de 'cobros' es el lenguaje de negocio legitimo. CORRECCIONES APLICADAS: (1) CLAUDE.md se habia movido a docs/ y ahi ya NO lo autocarga Claude Code (solo lee el de la raiz); se regreso a la raiz. (2) build_exe.ps1 y AutomationCostos.spec generaban ejecutables con NOMBRE DISTINTO ('AutomationCostos.exe' vs 'Automation Costos.exe' con espacio) y ademas el .ps1 compilaba a mano con --onefile omitiendo automation_costos/assets, los temas de customtkinter y los imports diferidos de main.py, o sea producia un exe roto; ahora hay UN SOLO camino de build: build_exe.ps1 delega en scripts/build_release.py, que usa el .spec. Se unifico el nombre en AutomationCostos.exe (sin espacio) en el .spec, build_release.py y docs/GUI.md. (3) .gitignore ignoraba *.spec incluyendo AutomationCostos.spec, del que depende build_release.py; se agrego la excepcion !AutomationCostos.spec. (4) Se borraron los artefactos viejos build/AutomationCobros y dist/AutomationCobros.exe (del 8 de mayo) y se recompilo: dist/AutomationCostos.exe 122 MB y dist/AutomationCostos_1.0_20260811.zip 115.6 MB. SECUELA ABIERTA: el .venv se heredo de la ruta vieja, pyvenv.cfg todavia dice Automation-Cobros y los lanzadores pip.exe y pyinstaller.exe salen con codigo 1; python.exe -m pip si funciona (pip 26.1). Se resuelve recreando el entorno con --clear.

**Archivos:** `CLAUDE.md`, `AutomationCostos.spec`, `build_exe.ps1`, `scripts/build_release.py`, `.gitignore`, `docs/ESTADO_ACTUAL.md`, `docs/GUI.md`

---

### 2026-08-11 09:59:33 — [DECISIÓN] PENDIENTE: renombrar la carpeta raiz a Automation-Costos + checklist de validacion

El renombre Cobros -> Costos quedo hecho DENTRO del repo (ver la entrada anterior). Falta unicamente la carpeta raiz en disco y los artefactos build/ y dist/, que conservan el nombre viejo (son de compilacion, se regeneran con scripts/build_release.py; NO se borraron).

No se renombro la carpeta en la sesion del 2026-08-11 porque es el directorio de trabajo de VS Code y de la sesion de Claude Code: moverla a media operacion rompe la sesion. Oscar decidio hacerlo el mismo al cerrar.

MIENTRAS NO SE RENOMBRE NO PASA NADA: todo ejecuta igual (verificado). El nombre de la carpeta no es una dependencia del codigo, solo queda la inconsistencia cosmetica de que la ruta dice Cobros y el proyecto dice Costos.

PASOS PARA RENOMBRAR
1. Cerrar VS Code y asegurarse de que NO haya descargas de CPA Vision corriendo.
2. Desde una terminal fuera del proyecto:
   move "X:\Soriana\00 - AUDITORIA 2020 - 2024\00 - Auditores\Oscar\Proyectos Python\Automation-Cobros" "X:\Soriana\00 - AUDITORIA 2020 - 2024\00 - Auditores\Oscar\Proyectos Python\Automation-Costos"
3. Abrir la carpeta nueva.

CHECKLIST DE VALIDACION (correr desde la carpeta nueva)
- [ ] .venv\Scripts\python.exe main.py --help  -> debe decir 'Automation Costos - fase 1' y listar los 17 subcomandos.
- [ ] .venv\Scripts\python.exe -c "import automation_costos, config; print(config.DB_SERVER, config.FOLIO_PREFIX)"  -> ATL20AF2222SQ19 11004.
- [ ] .venv\Scripts\python.exe -m py_compile scripts/*.py main.py config.py test_cruce_cpa.py  -> sin salida.
- [ ] Abrir la GUI: .venv\Scripts\python.exe main.py gui  -> el encabezado debe decir 'Automation Costos'.
- [ ] Buscar residuos: grep -ri "cobros" --exclude-dir=.venv --exclude-dir=.git --exclude-dir=outputs .  -> lo unico valido que debe aparecer es 'no cobros reales' en docs/ESTADO_ACTUAL.md (lenguaje de negocio, no el nombre del proyecto).
- [ ] git status  -> confirmar que los renombres del paquete siguen registrados como R (rename), no como borrado+alta.
- [ ] Verificar que outputs/cpa_vision/parquet sigue accesible y que gen_lote_monica.py lee el parquet (350 RFC).

DESPUES DEL RENOMBRE
- El .venv SIGUE funcionando invocando .venv\Scripts\python.exe directamente. Lo que se rompe son los lanzadores con ruta absoluta incrustada (pip.exe, pyinstaller.exe): usar .venv\Scripts\python.exe -m pip ... en su lugar, o recrear el entorno con python -m venv .venv --clear y reinstalar.
- Si hay variables de entorno COBROS_* puestas a mano en la maquina, ya no se leen: renombrarlas a COSTOS_* (los valores por defecto del codigo son los mismos, asi que sin ellas tambien funciona).
- La memoria de Claude Code esta indexada por la ruta del proyecto, asi que arrancara en blanco. Todo el contexto importante vive en docs/, que es justo para lo que se diseno.

**Archivos:** `docs/ESTADO_ACTUAL.md`, `AutomationCostos.spec`, `build_exe.ps1`

---

### 2026-08-11 09:58:56 — [DATO] Correo de estatus de descarga CPA Vision para Monica y Hector (redactado)

Se redacto el correo de avance con el corte al 2026-08-11. Estructura acordada tras una correccion de Oscar (la primera version arrancaba con el avance contra el objetivo; el pidio que el PRIMER cuadro fuera lo efectivamente descargado segun los parquet, y todo mas resumido e ir directo a los datos): (1) Informacion descargada: 350 RFC, 809 pares proveedor-anio, 9,788,880 CFDI, 86,978,317 conceptos, ene-2020 a ene-2026, 4.9 GB (1.9 GB de parquet); se aclara que 337 traen datos y 13 quedaron vacias y se reintentan. (2) Avance vs objetivo <90%: 416/246 objetivo, 167 descargadas (109 prov completos), 17 extranjeros sin RFC, faltan 232 filas / 120 prov, con desglose por anio. (3) Tiempos: 378 solicitudes, 89% de exito, mediana 3m43s, promedio 9m32s, p90 17m, 190 h acumuladas, estimado de 20-25 h para los 120 pendientes (3-4 jornadas). (4) Rutas: outputs/cpa_vision del proyecto, copia para Data Services y carpeta de entregables. (5) Indicador de beneficio por anio, con el caso Selecta 2020 (8.5%->8.7% pese a 15 mil CFDIs bajados) puesto a consideracion de negocio. Adjuntos: Inventario_CPA_Vision.xlsx y el reporte de extranjeros. PENDIENTE al momento de redactarlo: la Fase 3 (copiar el parquet a la carpeta de Data Services) no estaba hecha, por eso el correo dice 'disponible esta semana'; si se envia despues de copiarlo hay que cambiar esa frase a presente.

**Archivos:** `Inventario_CPA_Vision.xlsx`, `reporte_monica_extranjeros.xlsx`

---

### 2026-08-11 09:58:37 — [DECISIÓN] Columnas de beneficio sin celdas vacias + nueva columna estatus_cpa

Oscar pidio que en 'Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx' ningun proveedor quede con las columnas nuevas en blanco (ejemplo: proveedor 70). Regla acordada para el proveedor-anio AUN NO DESCARGADO: edi_despues = reg_edi (arrastra el estado actual), pct_despues = pct (el mismo porcentaje que ya tenia), mejora_pp = 0 y renglones_ganados = 0. Se agrego ademas la columna estatus_cpa (Descargado / Pendiente) porque sin ella un 0 en mejora_pp se lee igual para 'ya descargue y no gano nada' que para 'todavia no descargo'. La regla quedo dentro de actualizar_plan_beneficio.py para que las proximas corridas salgan asi de origen, y se aplico al archivo ya existente. RESULTADO VERIFICADO sobre el archivo escrito: 4,202 filas / 760 proveedores, CERO celdas vacias en las 5 columnas; 1,781 filas Descargado (312 prov) y 2,421 filas Pendiente (448 prov), con la regla cumplida en el 100% de las pendientes. Hallazgo: no hay proveedores mezclados (los 448 pendientes lo estan en todos sus anios), porque el beneficio se calcula por proveedor completo cuando su RFC ya esta en parquet; es decir estatus_cpa es estatus del PROVEEDOR, no del anio. Total renglones ganados a la fecha: 116,907. OJO al reportar: la mejora promedio simple da 0.69 pp y enganya, porque mezcla proveedores de 100 renglones con los de millones; conviene ponderar por reg_compras o usar renglones ganados en absoluto.

**Archivos:** `scripts/actualizar_plan_beneficio.py`, `Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx`

---

### 2026-08-11 09:41:09 — [DECISIÓN] Renombre del proyecto: Cobros -> Costos

El nombre estaba mal desde el origen: la automatizacion es del proceso de COSTOS, no de cobros. Se renombro en todo: paquete automation_cobros -> automation_costos (git mv, conserva historial), AutomationCobros.spec -> AutomationCostos.spec, clase CobrosApp -> CostosApp, titulo de la GUI y del CLI 'Automation Cobros' -> 'Automation Costos', variables de entorno COBROS_* -> COSTOS_* en config.py y README, build_exe.ps1, .claude/settings.local.json y todas las rutas automation_cobros/ de la documentacion (incluidas las entradas historicas de la bitacora, para que los enlaces sigan sirviendo). Se conservo la palabra 'cobros' donde es lenguaje de negocio legitimo (ESTADO_ACTUAL 'no cobros reales'). Verificado: los 17 modulos del paquete importan, main.py --help corre, scripts/ y config.py compilan. Los artefactos build/ y dist/ quedaron con el nombre viejo; se regeneran al proximo build_release.

**Archivos:** `automation_costos/`, `AutomationCostos.spec`, `config.py`, `README.md`, `main.py`, `build_exe.ps1`, `docs/`

---

### 2026-08-11 08:47:04 — [DATO] Corte de avance CPA Vision al 2026-08-11 (para el correo de estatus)

Medido contra el parquet (fuente de verdad) y las 22 metricas de lote. Parquet: 350 RFC, 337 con datos, 86,978,317 conceptos, 9,788,880 UUID, 809 pares RFC-anio, 4.9 GB (1.9 GB el parquet). Objetivo Monica <90%: 416 filas / 246 prov -> 167 filas cubiertas (eran 104 el 08-10), 232 faltantes en 120 proveedores (eran 295/159), 17 extranjeros sin RFC imposibles, 109 proveedores ya completos. Faltantes por anio: 2020=30, 2021=44, 2022=45, 2023=41, 2024=9, 2025=63. Tiempos: 378 intentos, 190.3 h de reloj acumuladas, mediana 3m43s y media 9m32s por descarga OK, p90 17m. OJO: METRICAS_TOTALES cuenta 'downloaded_after_recovery' (47) como error; el exito real es 336/378 = 88.9%, no 76.5%.

**Archivos:** `Inventario_CPA_Vision.xlsx`, `outputs/cpa_vision/METRICAS_TOTALES.txt`

---

### 2026-08-11 08:46:51 — [CÓDIGO] scripts/actualizar_plan_beneficio.py: plan de Monica con el beneficio por anio

Vuelca la cobertura EDI DESPUES del cruce CPA sobre el archivo de Monica, respetando su estructura (una fila por proveedor-anio). Reusa beneficio_proveedor() de beneficio_cpa.py y resolver_rfc/cobertura_parquet de gen_lote_monica.py; solo calcula proveedores cuyo RFC ya esta en parquet, los demas quedan en blanco. Salida 'Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx' con 4 columnas nuevas: edi_despues, pct_despues, mejora_pp, renglones_ganados. Corrida del 2026-08-11 00:29: 1,781 de 4,202 filas prov-anio con beneficio calculado, 312 proveedores. Cierra el pedido de Monica de un indicador desagregado por anio (reunion 009).

**Archivos:** `scripts/actualizar_plan_beneficio.py`, `Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx`

---

### 2026-08-10 09:49:24 — [CÓDIGO] Limpieza: eliminados lotes de descarga ejecutados y scaffolding

Borrados 17 archivos descarga_prioridad_lote*/descarga_prioritarios_*/descarga_54858/test_mes_ene2026 (superados por el maestro modo-Monica; el parquet es la fuente de verdad) + test_duckdb.py y muestra_duckdb.xlsx (exploratorio). debug.log no se pudo borrar (en uso). Conservado test_cruce_cpa.py (prueba real).

---

### 2026-08-10 09:49:23 — [CÓDIGO] scripts/gen_lote_monica.py y scripts/beneficio_cpa.py

gen_lote_monica.py: genera el maestro descarga_monica_pendientes.xlsx (FECHAS = anios sueltos <90% por proveedor, orden por prioridad, excluye lo ya en parquet) + reporte_monica_extranjeros.xlsx. beneficio_cpa.py: indicador de cobertura EDI antes/despues del cruce por proveedor-anio (reg_compras excluye cod_tipo_mvto 161/162, anio por rcvdt). Validado con Selecta 741: antes 2020-2024 = 20.86% identico a Monica.

**Archivos:** `scripts/gen_lote_monica.py`, `scripts/beneficio_cpa.py`

---

### 2026-08-10 09:49:22 — [REUNIÓN] Correo Monica: enfoque por cobertura <90% e indicador de beneficio por anio

Cambio de criterio: descargar solo proveedor+anio con cobertura EDI <90% (columna accion=Descargar/Ejecutar del archivo 'Planeacion vs %EDI poblado Soriana.xlsx'). Objetivo real 416 filas/246 prov; contra parquet faltan 295 filas/159 prov, 104 ya cubiertas, 17 extranjeros sin RFC imposibles por CPA. Info a compartir con Data Services. Detalle en reunion 009.

**Archivos:** `docs/reuniones/009-2026-08-10-enfoque-cobertura-90-monica.md`, `Planeacion vs %EDI poblado Soriana.xlsx`

---

### 2026-08-05 12:52:20 — [DECISIÓN] Periodo con margen: compras a 31-mar-2026, CPA +enero 2026

Reunion con Monica 2026-08-05. El periodo 2025 arrastra a 2026 (facturas tardias + pagos hasta 90 dias). (1) Compras/ejecucion: FUENTES_COMPRAS extiende SORIANA_2025_PROJECTS a 2026 (limite superior; seguro, no hay otra fuente 2026); ejecutar con --end 2026-03-31 (corte actual de la info, hasta ~marzo). Mapeo: 2020-2024=>1/1/2020-31/12/2024; 2025=>1/1/2025-31/3/2026; 2020-2025=>1/1/2020-31/3/2026. (2) CPA descarga: la malla del portal tiene meses; cuando el periodo incluye 2025 se marca SOLO enero 2026 (celda, no el ano). Nuevo _set_month_checkbox (geometrico) + _MES_MARGEN=(2026,1). NO hay que cambiar las FECHAS de los lotes: el scraper agrega ene-2026 solo. El selector de mes requiere validacion en corrida real.

---

### 2026-08-05 10:53:42 — [CÓDIGO] Formato completo en la validacion de gigantes (streaming xlsxwriter)

write_validation_streaming ahora genera las hojas con el mismo lenguaje visual que la ruta openpyxl: logo Soriana, titulo (filas 2-4), encabezado verde en fila 8, datos desde fila 9 en columna B, formatos de numero (moneda #,##0.00 y % ), formulas SUBTOTAL en la fila de totales (Debio Pagar/Diferencia/Diferencia Ajustada/Monto No Compensado y Debio Pagar correcto), freeze panes y autofiltro. Nuevos helpers _formatos_xlsx/_titulo_xlsx/_encabezar_xlsx/_volcar_xlsx y _DetalleStream formateado (con titulo+encabezado por hoja de continuacion). Verificado que constant_memory soporta logo+merge+formula+set_column+freeze+autofilter escribiendo en orden de filas. Aplica a Pepsico, Arca, Nestle, Empacadora Celaya. Probado con datos sinteticos.

---

### 2026-08-05 08:49:08 — [CÓDIGO] Validacion gigante: hoja Detalle completa por streaming (no se omite)

Arca reventaba por RAM al materializar los 4.3M renglones de detalle. Nueva funcion write_validation_streaming: arma Consolidado+Ajustes desde una fuente de un renglon por folio (chica) y escribe la hoja Detalle PAGOS por chunks (clase _DetalleStream, con corte por tope de filas de Excel), sin tener el detalle completo en memoria. generar_validacion_grande ahora hace dos pasadas sobre los trozos (pasada 1: dedup por folio para el consolidado; pasada 2: generador de chunks para el detalle) y acepta por_mes para partir por mes (chunks mas chicos = menos memoria). CLI cpa-validacion-grande gana --por-mes. Se revirtio la idea de sin_detalle (el usuario necesita el detalle). Probado con 2 chunks: detalle completo (5 renglones) y columnas alineadas.

---

### 2026-08-05 07:32:25 — [CÓDIGO] Bajar pico de memoria en write_validation_rapida (proveedores gigantes)

Arca (4.3M renglones de detalle) reventaba por memoria al escribir la validacion. (1) write_validation_rapida ahora acepta en_sitio=True: muta el df recibido (drop de columnas sobrantes + folio) en vez de copiarlo entero; pipeline_streaming.generar_validacion_grande lo llama asi (no reutiliza df_dif). (2) _dump_tabla itera df.itertuples directo cuando el df ya trae las columnas en orden (caso del Detalle), evitando la copia/consolidacion de df[columnas] que era justo la operacion que fallaba (vstack). (3) del compras_df tras armar el detalle. No es por los ajustes MR8M/KG (esos operan sobre el consolidado chico). Probado en_sitio con df sintetico: muta el df, hojas y orden de columnas correctos.

---

### 2026-08-04 14:52:13 — [BUG] Fecha Pago 1900-01-01 en devoluciones no compensadas

F_APV2 devuelve ChkDt=1900-01-01 (placeholder de SQL Server) cuando la devolucion no esta compensada. En la hoja Ajustes salia esa fecha. Fix: helper _fecha_valida en ajustes_pagos descarta nulos y fechas con year<=1900 -> celda en blanco. Solo afecta la presentacion de Fecha Pago; las compensadas conservan su fecha real. Verificado con 741/12244.

---

### 2026-08-04 14:36:50 — [BUG] Consolidado: datos de columnas de ajuste salian corridos (openpyxl)

En _write_table (ruta openpyxl) los datos se volcaban en el orden del DataFrame, no en el de los encabezados. Como aplicar_ajustes agrega 'Diferencia Ajustada' al final del df pero el encabezado la ubica 3ra del bloque, los valores de Diferencia Ajustada/Compensado/Conteo/Monto salian desalineados (p.ej. bajo 'Diferencia Ajustada' aparecia 'No compensado'). Fix: _write_table ahora hace df.reindex(columns=columns) antes de volcar, igual que _dump_tabla (xlsxwriter) que ya reordenaba con df[columnas]. Verificado con 741/12244: cada dato queda bajo su encabezado.

---

### 2026-08-04 12:35:08 — [CÓDIGO] Alerta de devoluciones MR8M/KG no compensadas (ChkNbr vacio)

ajustes_pagos: clasificar_pagos ahora incluye TODAS las devoluciones MR8M/KG negativas con flag compensado (antes filtraba ChkNbr). aplicar_ajustes: las compensadas se restan (como antes); las NO compensadas no restan y marcan el renglon cruzado con Compensado='No compensado/ejecutado', Conteo No Compensados y Monto No Compensado. Nuevas 3 columnas en Consolidado (total 6 de ajuste) + hoja Ajustes ahora con columnas Compensado/Ajuste Aplicado/Monto No Compensado (bitacora de compensadas y pendientes). validation_exporter: usa COLUMNAS_AJUSTE, formato y SUBTOTAL para Monto No Compensado, ambas rutas openpyxl/xlsxwriter. Validado con 741 (12244 no compensada ahora se marca en vez de ignorarse) y test compensado/no-compensado. Docs LOGICA_NEGOCIO 11 y reunion 007.

---

### 2026-08-04 10:54:59 — [CÓDIGO] Correccion llave KG: nota de entrada + tienda (RcpNbr + StrNbr)

Ajuste en ajustes_pagos.aplicar_ajustes: los casos KG-14 ahora se ligan por Nota de entrada (RcpNbr) + Tienda (StrNbr) = el folio del Consolidado, en vez de factura+tienda. MR8M queda igual (proveedor+factura). RcpNbr ya venia en el fetch. Validado con 741: KG cruza por nota+tienda aunque la factura difiera. Docs LOGICA_NEGOCIO 11 y reunion 006 actualizados.

---

### 2026-08-04 10:37:26 — [CÓDIGO] Ajustes de pagos MR8M/KG-14 en la Validacion (F_APV2)

Nuevo modulo ajustes_pagos.py: fetch_pagos_ajustes lee F_APV2 (SORIANA_PROJECTS) y clasifica devoluciones MR8M (DOC_TEXT=MR8M, llave prov+factura) y KG-14 (COD_TYPE_CODE=KG y BSAK_BSIK_XREF3 LIKE 14%, llave prov+factura+tienda), solo con ChkNbr ejecutado y GrsInvAmt<0. aplicar_ajustes (pura) consume el importe negativo contra la diferencia disponible del Consolidado (cascada, sin negativos). Integrado en validation_exporter (ambas rutas openpyxl y xlsxwriter): agrega columnas Tipo Ajuste/Ajuste Pagos/Diferencia Ajustada, quita del Consolidado los renglones que quedan en ~0 y los lista en nueva hoja Ajustes; Resumen usa Diferencia Ajustada. No-op seguro si no hay devoluciones o falla la BD. Validado con 741 (5 MR8M + 23 KG; 12244 excluida por ChkNbr vacio) y smoke test de ambas rutas. Docs: LOGICA_NEGOCIO 11, reunion 006.

---

### 2026-08-01 23:10:21 — [CÓDIGO] CPA: fix atasco en SELECCIONAR EMPRESA + regeneracion de solicitud

Dos correcciones en cpa_vision.py durante la espera del ZIP. (1) _reauth_solicitudes ahora hace login->_open_descargas(selecciona SORIANA)->_open_solicitudes; antes se saltaba _open_descargas y quedaba atascado en okta/empresas. La verificacion proactiva usa _en_area_descargas (URL descarga-masiva) en vez de _is_empresa_or_downloads_page, que tomaba la pantalla de empresas como valida. (2) _wait_for_request_zip: nuevos params rfc/years/regenerate_after_missing(=30). Si la solicitud nunca aparece en la tabla tras 30 intentos, _regenerar_solicitud crea una nueva para el mismo RFC (return_to_form+configure+submit) y sigue esperando; el batch refresca el request_id real desde el nombre del ZIP (_request_id_from_zip) para particionar el Parquet. La dedup por request_id del dataset cubre posibles duplicados.

---

### 2026-07-31 15:43:14 — [DECISIÓN] cto_aud/iva_aud/ieps_aud por cruce CPA + CtoUnitario_sistema=ctouni

Reunion 005 (2026-07-31, Monica/Perla). (1) La bandera de los 3 campos auditados pasa de 'ctonto_edi != 0' a 'cruzo con CPA' = presencia real de uuid o ctonto_edi (helper _presente). Si cruza: iva_aud=poriva_edi, ieps_aud=prieps_edi aunque sean 0, cto_aud=menor(ctonto_edi,ctouni) nunca 0. Si no cruza: ctouni / iva_t007s / ieps_t007s. (2) CtoUnitario_sistema del archivo de validacion ahora = ctouni (antes ctonto_edi); se agrego ctouni a _COLUMNAS_FUENTE. Docs: LOGICA_NEGOCIO 3/3.1, reunion 005, guias actualizadas. Probado con 2 filas.

---

### 2026-07-31 14:34:41 — [CÓDIGO] Refresco preventivo de sesion CPA cada 60 intentos

En _wait_for_request_zip: aunque el polling vaya bien, cada reauth_every_attempts (default 60) intentos se reinicia sesion (login de nuevo) y se reabre solicitudes via nuevo helper _reauth_solicitudes, reutilizado tambien por la recuperacion reactiva. No cierra el navegador para no invalidar el page del llamador.

---

### 2026-07-30 09:52:02 — [CÓDIGO] Exception Report: totales como formula =SUMA

Las sumatorias de la fila TOTAL (arriba) ahora son formulas vivas =SUM(rango) de la primera a la ultima fila con datos (helper _suma_arriba con xl_range), en ambas pestanas. Se guarda el valor calculado como cache para que se vea correcto antes de recalcular. Asi el total se actualiza si el auditor edita datos.

---

### 2026-07-30 09:41:27 — [CÓDIGO] Exception Report: totales arriba + titulo

A pedido de Oscar: la fila TOTAL se movio ARRIBA (fila 5, sobre el encabezado) y se congela (freeze_panes) en ambas pestanas, para ver la sumatoria sin bajar al final cuando el archivo crezca. Titulo del reporte cambiado a 'Consolidado Diferencias Costos Por Proveedor' (constante TITULO). Regenerado Exception_Report.xlsx.

---

### 2026-07-30 09:18:39 — [CÓDIGO] Exception Report (consolidado de diferencias)

Nuevo modulo automation_costos/exception_report.py + subcomando 'exception-report'. Lee la hoja Consolidado de cada Validacion POR NOMBRE de columna (robusto a los dos layouts: openpyxl fila 8 y xlsxwriter fila 1; openpyxl read_only, NO modifica los archivos del auditor -> sus filtros/ocultas quedan intactos). Un solo Excel con estilo corporativo (logo+verde): 'Consolidado de diferencias' (1 renglon x proveedor: diferencia, facturas/pedidos/folios con dif; 3M unificado 2020-24 + 2025) y 'Detalle de diferencia' (sumatoria por pedido+factura + conteo). Base: TODAS las filas (decision Oscar 2026-07-30). Total 6 proveedores: 688.4M / 335,783 pedido-factura. OJO: Nestle 340.8M luce alto (~13.7k/folio vs 1.1k Arca), revisar antes de presentar.

---

### 2026-07-29 17:47:32 — [CÓDIGO] GUI: descarga de CPA Vision por proveedor

Nuevo modulo automation_costos/cpa_descarga.py (descargar_cpa_proveedor: RFC+periodo -> request_download_and_wait -> zip_to_parquet_dataset). database.resolver_rfc() barato (TOP 1 cnpj) para auto-detectar el RFC del vendor. app.py: tarjeta ETAPA 2 ahora tiene credenciales CPA (usuario/password enmascarada) y boton 'Descargar de CPA Vision' (clave descarga); ui.campo acepta show='*'. La GUI queda delgada: dispara la orquestacion en hilo. Flujo por proveedor completo desde la GUI: descargar CPA -> salida completa (compras+cruce+recalculo+validacion). Para reunion con Audit Services.

---

### 2026-07-29 08:02:42 — [DECISIÓN] Entregables van a la carpeta de auditores; outputs/ del proyecto solo guarda cpa_vision

El share X:/Soriana se lleno (cuota) porque los entregables quedaban DUPLICADOS: en outputs/ del proyecto y en la carpeta de auditores donde Oscar los pega para el equipo: 'X:/Soriana/00 - AUDITORIA 2020 - 2024/Proceso Validacion de condiciones (Oscar Pineda)'. DECISION de Oscar (2026-07-29): generar los entregables DIRECTO en la carpeta de auditores (con --output-dir a esa ruta) y NO duplicar en el proyecto. Se BORRARON del proyecto outputs/ las 6 carpetas de proveedor (391250 Arca, 76034 Pepsico, 73692 Celaya, 5462 Nestle, 741 Selecta, 80622 3M) tras verificar que la carpeta de auditores ya las tiene completas; libero ~12.6GB (outputs/ de 17GB a 4.4GB). Se CONSERVA outputs/cpa_vision (4.4GB: ZIPs descargados + dataset Parquet) porque es la materia prima de todos los cruces y NO esta en la carpeta de auditores. De aqui en adelante: cruces/datos en el proyecto (outputs/cpa_vision), entregables (Compras/Validacion/soportes) en la carpeta de auditores via --output-dir. Las descargas de CPA Vision siguen a outputs/cpa_vision (--download-dir). HALLAZGO del dia: de los 59 prioritarios del master (col X), solo 6 tienen CPA descargada y son exactamente los 6 urgentes; 53 pendientes. Se armo descarga_prioritarios_lote1.xlsx con los primeros 10 pendientes (RFC+FECHAS) para el comando cpa-batch-vendors. Ademas: Arca ya tiene sus 24 Compras (Oscar corrio cpa-compras-grande hoy, funciono y fue resumible).

**Archivos:** `descarga_prioritarios_lote1.xlsx`, `docs/ESTADO_ACTUAL.md`

---

### 2026-07-28 09:15:54 — [CÓDIGO] Subcomando cpa-compras-grande: Compras de gigantes por trimestre/mes, resumible

Oscar pidio generar SOLO los archivos de Compras pendientes de los gigantes (Arca 2022-2025; ya tenia 2020-2021 de un intento anterior) por comando en terminal, sin re-hacer lo ya hecho, por trimestre (o mes). Nuevo pipeline_streaming.generar_compras_grande: UNA pasada por intervalo, trae el intervalo COMPLETO (todos los renglones, no solo auditables — el Compras es referencia completa), cruza con CPA (ya filtrada por factura, lo que lo hace caber), y escribe Compras_<base>_<etiqueta>.xlsx. RESUMIBLE: resuelve el base desde la carpeta existente y SALTA los intervalos cuyo archivo ya existe, sin re-consultar SQL (no se pierde el trabajo hecho). NO escribe Validacion -> no acumula nada -> pico acotado a un intervalo (~5.5GB un trimestre de Arca). Soporta --por-mes (nuevo _intervalos_mes, 72 meses) para proveedores donde un trimestre no quepa (Pepsico si hace falta). Nota: los totales por folio del Compras quedan POR INTERVALO (para los ~0.3% de folios que cruzan intervalo difieren del global; el numero exacto vive en la Validacion, que si es global). Subcomando main.py cpa-compras-grande --vendor --start --end --parquet --output-dir [--por-mes]. VERIFICADO en Selecta: genera por trimestre y en un 2do run salta los existentes. Arca tiene 8 Compras (2020-2021) + Validacion + soporte; el comando generara 2022-2025 (16 trimestres). Comando Arca: python main.py cpa-compras-grande --vendor 391250 --start 2020-01-01 --end 2025-12-31 --parquet outputs/cpa_vision/parquet --output-dir outputs

**Archivos:** `automation_costos/pipeline_streaming.py`, `main.py`

---

### 2026-07-27 19:33:13 — [DATO] Pepsico entregado: los 6 urgentes cerrados

Pepsico (76034) Validacion generada con el filtro por factura: 446,489 folios auditables, 123,742 con diferencia > 1 peso (27.7%), monto total 160,600,953.85, Detalle 1,917,582 renglones en 2 hojas (completo), soporte 619617 (el request completo, no el duplicado). RAM estable ~3GB, sin OOM. Con esto los 6 urgentes estan listos: Selecta, Celaya, Nestle, 3M (Compras+Validacion) y Arca (157,433 folios, 170.6M) + Pepsico (123,742 folios, 160.6M) con Validacion (los 2 gigantes por el camino ligero, sin Compras por decision de Oscar 'Validacion primero'). PENDIENTE con negocio: validar si el ~28-38% de diferencias y los montos (~160-170M cada uno) son reales o si el umbral de 1 peso necesita ajuste (Monica/Luis).

**Archivos:** `outputs`

---

### 2026-07-27 18:05:05 — [CÓDIGO] cargar_cpa filtra tambien por factura + Detalle en varias hojas + Arca entregado

Pepsico (16M de CPA) reventaba aun por trimestre: unos pocos codigos de barra matchean ~9GB de conceptos CPA y la memoria no se liberaba entre trimestres. FIX: cargar_cpa acepta facturas=(series_folios, folios) y filtra la CPA a las facturas presentes en el lote, con las DOS llaves del cruce (serie+folio normalizado y solo digitos, con OR) replicadas en SQL. pipeline_streaming._salida_intervalo calcula esas llaves de raw.invnbr y las pasa. RESULTADO: Pepsico 3 trimestres seguidos pico 2.7GB (antes 9), sin OOM. SEGURIDAD VERIFICADA: el filtro solo quita conceptos de CPA cuya factura NO esta en las compras (no podian cruzar); Selecta con filtro vs sin filtro da Validacion IDENTICA (Consolidado 188/188, Detalle 1119/1119, 0 columnas difieren). Otros fixes de esta vuelta: (1) validation_exporter._dump_tabla parte el Detalle en varias hojas cuando pasa de 1,048,576 (antes se truncaba en silencio; Arca tenia 4.29M de detalle). (2) subcomando main.py cpa-validacion-grande y scripts/correr_validaciones_grandes.py corre cada proveedor en PROCESO PROPIO (memoria limpia). ARCA ENTREGADO: Validacion 510MB, Consolidado 157,433 folios con diferencia, monto total 170,642,809.25, Detalle 4,296,801 renglones en 5 hojas, soporte copiado. Pepsico corriendo con el filtro (RAM 2.9GB). Pendiente negocio: validar con Monica/Luis si el ~40% de diferencias / el monto es real o si el umbral de 1 peso necesita ajuste.

**Archivos:** `automation_costos/cruce_cpa.py`, `automation_costos/pipeline_streaming.py`, `automation_costos/validation_exporter.py`, `main.py`, `scripts/correr_validaciones_grandes.py`

---

### 2026-07-27 13:50:15 — [CÓDIGO] Validacion de gigantes: camino ligero (Validacion-solo, filtrado y motor rapido)

Arca (11.5M) y Pepsico (10.1M) fallaban aun por trimestre: el pipeline acumulaba en RAM las filas con diferencia para la Validacion final y reventaba al cargar la CPA del siguiente (ArrowMemoryError en cargar_cpa). Ademas se midio que Arca marca 3.7%-42.6% de diferencias por trimestre (muchos hallazgos reales donde el CFDI < sistema), asi que openpyxl no aguanta el volumen. Oscar pidio analizar que se puede FILTRAR y priorizar la Validacion. Analisis: (1) los ~3.5M renglones 'sin fecha' son en realidad SIN NOTA DE ENTRADA (rcvnbr nulo, ~30%): no auditables a nivel folio, caen en un folio degenerado que nunca se marca -> excluirlos NO cambia la Validacion (verificado). (2) la Validacion solo usa ~31 de las 105 columnas. Solucion: nuevo pipeline_streaming.generar_validacion_grande - UNA pasada por trimestre trayendo solo auditables (fetch_compras ahora acepta filtro_filas='rcvnbr IS NOT NULL'), cruza, prepara, se queda con las columnas fuente, acumula debio/pagado por folio GLOBAL y vuelca a disco (pickle por trimestre, no acumula en RAM); al final filtra folios con diferencia, pega totales globales y escribe con motor RAPIDO. Nuevo validation_exporter.write_validation_rapida (xlsxwriter en streaming) + build_detalle_rapido (vectorizado, sin iterrows) que aguantan millones de renglones. cruzar() ahora soporta en_sitio y cargar_cpa limita la memoria de DuckDB (memory_limit 4GB + spill). NO escribe el Compras (Validacion primero, decision de Oscar). VERIFICADO IDENTICO al camino normal: Selecta 2020-2025 por generar_validacion_grande da Consolidado 188 y Detalle 1119, 0 diferencias. Arca y Pepsico corriendo por scripts/correr_validaciones_grandes.py: pico RAM 4.5GB, ~2.5 min/trimestre.

**Archivos:** `automation_costos/pipeline_streaming.py`, `automation_costos/validation_exporter.py`, `automation_costos/database.py`, `automation_costos/cruce_cpa.py`, `scripts/correr_validaciones_grandes.py`

---

### 2026-07-27 09:21:44 — [CÓDIGO] Proveedores gigantes: procesamiento por TRIMESTRE (un año no cabe en RAM)

Al correr Arca/Pepsico por el camino por año fallaron con MemoryError: un año completo (Arca 2025: 1.6M compras + 2.9M conceptos de CPA -230 codigos de barra pero matchean 2.9M filas-) sube a 12GB y no cabe en los ~13GB libres. Tres cambios: (1) cruzar() ahora acepta en_sitio=True y el pipeline por intervalos lo usa: no copia el df del intervalo (ahorra ~5GB en un año). (2) cargar_cpa limita la memoria de DuckDB (memory_limit 4GB + temp_directory) para que use disco al materializar los millones de conceptos de CPA en vez de reventar. (3) LO PRINCIPAL: pipeline_streaming ahora procesa por TRIMESTRE, no por año (decision de Oscar: Compras por trimestre + Validacion consolidada). Nuevo _intervalos_trimestre (24 trimestres para 2020-2025); _Anio->_Intervalo, _salida_anio->_salida_intervalo; escribe un Compras_<base>_<año>-T<n>.xlsx por trimestre (~24 por proveedor) reusando escribir_libro_compras (con su Pendientes_EDI); la Validacion sigue consolidada en 1 archivo (agregacion global por folio/factura a traves de todos los trimestres). MEDIDO: un trimestre de Arca (2025-T4, 421,151 renglones) pico 5.5GB, 193s -> cabe holgado. VALIDADO que con trimestres el resultado es IDENTICO al camino normal: Selecta 2020-2025 (58,558 filas, 0 columnas difieren, Validacion 188/1119 identica). Se agrego gc.collect() entre trimestres. gan y Pepsico relanzados por scripts/correr_grandes_pendientes.ps1 (ya con trimestres).

**Archivos:** `automation_costos/pipeline_streaming.py`, `automation_costos/cruce_cpa.py`, `automation_costos/pipeline.py`

---

### 2026-07-26 21:23:39 — [CÓDIGO] Pipeline por año (streaming) para proveedores que no caben en memoria

Arca (11.5M renglones) y Pepsico (10.1M) morian con MemoryError en fetch_compras: el DataFrame completo no cabe en 24GB (Celaya 1.24M ya usaba 13GB). Solucion pedida por Oscar: NO tocar la funcion SQL F_COMPRAS; procesar por intervalos (año por año) y consolidar. Nuevo modulo automation_costos/pipeline_streaming.py (generar_salida_proveedor_por_anios) en DOS PASADAS: (1) por año llama F_COMPRAS(vendor, año-01-01, año-12-31) tal cual, cruza con CPA, prepara, y acumula por folio (nota de entrada) y por factura: suma de imp_aud (debio pagar), suma de impaud display (dpagar), max de tot_pagado_ne/tot_pagado_inv (pagado); descarta los renglones. (2) totales GLOBALES por folio/factura (asi los ~0.3% de folios que cruzan un año salen exactos). (3) re-cruza cada año, pega los totales globales y escribe Compras_<base>_<año>.xlsx. (4) junta solo las filas de folios con diferencia y reusa write_validation_from_dataframe -> UNA sola Validacion. Pico de memoria acotado a un año (~1.4M). generar_salida_proveedor ahora es un dispatcher: hace un COUNT barato (nueva database.contar_compras) y si supera MAX_FILAS_EN_MEMORIA=2.5M usa el camino por año, si no el normal (_generar_salida_en_memoria, intacto). Nuevo excel_exporter.escribir_libro_compras (publico) para escribir un df ya preparado. ResultadoPipeline.cruce ahora opcional (None en el camino por año). HALLAZGO clave: los 3.5M 'sin fecha' de Arca son en realidad 'sin nota de entrada' (rcvnbr nulo); entre folios reales solo 0.28% cruzan año. VALIDADO que el camino por año da resultados IDENTICOS al normal: Selecta 2020-2025 (58,558 filas, 0 columnas difieren, Validacion 188/1119 identica) y Nestle 2020-2021 (266,478 filas con folios que cruzan año, 0 difieren, Validacion 7410/114255 identica); mas test unitario de la suma por folio que cruza año. Arca y Pepsico lanzados por scripts/correr_grandes_pendientes.ps1.

**Archivos:** `automation_costos/pipeline_streaming.py`, `automation_costos/pipeline.py`, `automation_costos/database.py`, `automation_costos/excel_exporter.py`, `scripts/correr_grandes_pendientes.ps1`

---

### 2026-07-25 15:37:00 — [CÓDIGO] Compras de proveedores grandes: un archivo por año (>1M filas)

Oscar pidio que los proveedores muy grandes (Arca, Pepsico) generen varios archivos de Compras en vez de uno gigante (Celaya quedo en 682MB). Decidido: un ARCHIVO POR AÑO, y solo para los grandes; los chicos siguen en un solo archivo con hojas por año. Implementado en excel_exporter.write_compras_files (nueva funcion orquestadora): si len<=UMBRAL_PARTIR_POR_ANIO (1,000,000 filas) escribe un solo Compras_<base>.xlsx; si es mayor, escribe Compras_<base>_2020.xlsx, _2021.xlsx, ... cada uno con su Compras <año> y su propio Pendientes_EDI de ese año. Se corta en limites de año (via _grupos_por_anio), asi una nota de entrada nunca queda partida entre archivos y no se afecta ningun calculo. Se refactorizo write_compras_workbook: _preparar_para_escritura (prepare + apply_display_formula_values + reorden) y _escribir_libro (abre el xlsx con use_zip64 y escribe hojas+pendientes, borra el archivo si algo falla); write_compras_workbook (usado por recalc y proveedores chicos) y write_compras_files comparten estos helpers. LA VALIDACION SIGUE SIENDO UN SOLO ARCHIVO (es el entregable real, chica, se arma del DataFrame en memoria). ResultadoPipeline ahora expone compras_paths (lista); compras_path queda como el primero para la GUI. main.py imprime todos los archivos. VERIFICADO en datos reales (Selecta, umbral forzado a 10k): 6 archivos por año que suman 58,558 filas exactas, cada uno con su Pendientes_EDI; Validacion IDENTICA a la entregada (0 columnas difieren, 188/1119 filas); read_compras_workbook relee un archivo-año OK (23,637 filas, 105 cols). Caso chico: 1 archivo. La particion nocturna de Arca/Pepsico se activara sola. Selecta y Celaya NO se tocan.

**Archivos:** `automation_costos/excel_exporter.py`, `automation_costos/pipeline.py`, `main.py`

---

### 2026-07-24 17:00:22 — [CÓDIGO] Script correr_urgentes.ps1 para lote nocturno de proveedores

Se creo scripts/correr_urgentes.ps1 que corre por cpa-salida los 4 urgentes restantes uno tras otro, ordenados de menor a mayor: 80622 3M (solo 2025), 5462 Nestle, 391250 Arca, 76034 Pepsico. Cada proveedor es independiente: si uno falla se registra y sigue con el siguiente (ErrorActionPreference Continue, se captura LASTEXITCODE). Genera un log por proveedor en outputs/logs/<vendor>_<stamp>.log y un resumen urgentes_<stamp>.resumen.txt con estado y duracion. Usa el python del venv y PYTHONIOENCODING=utf-8. Verificado contra el Parquet (regla 4.4) que los 4 RFC estan: Pepsico CPM110719SG3 15.96M filas 2 req, Nestle MNE0409226K9 1.33M 2 req, Arca DJB850527F30 7.85M 1 req, 3M TMM720509PYA 25,555 solo 2025. Sintaxis PowerShell validada. RIESGO documentado: Arca y sobre todo Pepsico son los mas pesados en memoria (Celaya 1.24M compras uso 13.4GB de 24GB); si alguno se queda sin memoria el log lo mostrara y los demas terminan igual.

**Archivos:** `scripts/correr_urgentes.ps1`

---

### 2026-07-24 16:53:54 — [CÓDIGO] Compras: una hoja por año (rcvdt) en vez de por tope de filas

Oscar pidio que el Compras agrupe las hojas por AÑO (2020, 2021, ...) segun rcvdt, en vez del corte por tope de filas. Cambios: (1) excel_exporter._write_compras_sheets ahora agrupa por año de rcvdt y nombra las hojas 'Compras 2020', 'Compras 2021', ...; si un año rebasa el tope de Excel se parte en 'Compras 2020 (2)', (3)... El agrupado es SOLO presentacion: reordena en que hoja cae cada renglon, no cambia ningun valor calculado (todo viene precalculado por renglon y por grupo). (2) Nueva _anio_agrupacion: las filas sin fecha (NaT) NO van a una hoja aparte; heredan el año de su mismo grupo, en orden nota de entrada (concaten) -> factura (invnbr) -> vecino en el orden original (ffill/bfill). Asi ninguna se pierde ni se aisla. (3) BUG LATENTE ARREGLADO: read_compras_workbook (recalculate.py) y leer_compras (cruce_cpa.py) leian solo la hoja 'Compras', perdiendo las filas de las hojas de continuacion; ahora leen TODAS las hojas 'Compras*' y concatenan. Ese bug NO afecto los entregables de Selecta/Celaya porque el pipeline arma Compras y Validacion desde el DataFrame en memoria (write_validation_from_dataframe), nunca releyendo el archivo; VERIFICADO: la Validacion de Celaya cubre los 6 años con 35,762 filas de 2025 que viven en la 2a hoja del Compras. VERIFICACION del cambio con Selecta real a directorio temporal: Compras con 6 hojas por año (2020..2025) suman 58,558 renglones sin perder ninguno, NaT repartidos; Validacion IDENTICA a la entregada (0 columnas difieren, mismas 188/1119 filas), probando que no afecta calculos; leer_compras recupera las 58,558 filas y el RFC. Selecta y Celaya NO se regeneraron: sus archivos actuales quedan como estan (Oscar lo pidio explicitamente). El cambio aplica de ahora en adelante.

**Archivos:** `automation_costos/excel_exporter.py`, `automation_costos/recalculate.py`, `automation_costos/cruce_cpa.py`

---

### 2026-07-24 15:43:05 — [CÓDIGO] Soporte CPA Vision: una sola descarga por proveedor, sin duplicar

Oscar pidio que si un proveedor se descargo dos veces, la carpeta de soportes NO tenga la informacion duplicada sino un solo request_id. Se reemplazo request_ids_de_rfc (que devolvia el conjunto deduplicado por año y en teoria podia dar mas de un request) por request_id_principal, que elige UNA sola descarga: la de mayor cobertura (mas años distintos y, a igualdad, mas filas). Nueva dataclass SoporteRequest(principal, anios_principal, anios_totales, redundantes, cobertura_completa). copiar_soportes_cpa ahora copia solo el ZIP del request principal (incluidas sus partes _1.zip/_2.zip, que son una sola descarga en pedazos, no duplicado), avisa por log las descargas redundantes ignoradas, y lanza un AVISO fuerte si el principal no cubriera todos los años (caso que hoy no ocurre; nunca descarta años en silencio). VERIFICADO con los 2 proveedores que se bajaron dos veces: Pepsico CPM110719SG3 principal=619617 (6 años) ignora 619939 (solo 2025); Nestle MNE0409226K9 principal=618728 ignora 620512; ambos cobertura_completa=True. Prueba funcional: aunque en cpa_vision/ existen los dos ZIP de Pepsico, en la carpeta de soportes cae uno solo (619617, 380MB), cero de 619939. Selecta y Celaya sin cambio (un solo request). Compila e importa OK.

**Archivos:** `automation_costos/cruce_cpa.py`, `automation_costos/pipeline.py`

---

### 2026-07-24 15:26:17 — [CÓDIGO] Salida por proveedor en carpeta propia + copia de soportes ZIP de CPA Vision

Oscar pidio estandarizar la salida: una carpeta por proveedor con formato numero_nombre y dentro una subcarpeta 'cpa vision soportes' con los ZIP de CPA Vision que respaldan el entregable. (1) generar_salida_proveedor ahora crea output_dir/<numero>_<nombre>/ y escribe ahi el Compras y la Validacion (antes planos en output_dir); la GUI y el CLI solo usan las rutas que devuelve, no se rompe nada. (2) Nueva funcion copiar_soportes_cpa en pipeline.py: copia (no mueve) a la subcarpeta los ZIP cuyos request_id alimentaron el cruce; es idempotente (si el ZIP ya esta con el mismo tamaño no recopia) y NO fatal (si falta el ZIP o hay error de permisos/disco avisa y sigue, el entregable ya esta escrito). (3) La correspondencia dato<->soporte es exacta: se extrajo el CTE de deduplicacion de cargar_cpa a la constante compartida _CTE_ELEGIDO y se agrego request_ids_de_rfc(rfc, parquet) que reusa esa misma logica; asi para Pepsico/Nestle (que tienen 2 request cada uno, uno de solo-2025 que se descarta) copia SOLO el request que se uso -verificado: CPM110719SG3->619617, MNE0409226K9->618728, no los descartados-. (4) ResultadoPipeline ahora expone proveedor_dir y soportes; el CLI imprime la carpeta y cuantos ZIP. Constante SUBCARPETA_SOPORTES='cpa vision soportes' (con espacios, como se acordo nombrarla). MANUAL: se copiaron ya los ZIP de los 2 urgentes listos: Selecta 741 (641815, 992KB) y Celaya 73692 (641727, 33MB), verificados por sha256 identicos al original en outputs/cpa_vision. Compila e importa OK (incluida la GUI).

**Archivos:** `automation_costos/pipeline.py`, `automation_costos/cruce_cpa.py`, `main.py`

---

### 2026-07-24 14:26:14 — [DATO] Celaya (73692) generado completo: Compras 682 MB en 2 hojas, 1,244,498 renglones

Con los tres fixes (memoria en_sitio, use_zip64, vectorizacion) el proveedor que reventaba salio completo. Compras_73692 = 682 MB, tres hojas: Compras (1,048,569 filas, el tope de Excel), Compras (2) (195,929 filas, el resto) y Pendientes_EDI (385,554). Total 1,244,498 renglones, cuadra al renglon con lo que trajo SQL; RFC ECE830923MJ2 en A8. Esto confirma el requisito original de Oscar: proveedor grande partido en varias hojas sin perder renglones. Validacion 41.5 MB (Consolidado 26,326 folios, Detalle 322,294 filas). Tiempos aprox: SQL+cruce 6 min, Validacion 14 min (openpyxl con 322k filas de detalle es el paso lento ahora), Compras 26 min. Memoria pico ~13 GB, estable. NOTA para negocio: el Consolidado de Celaya tiene 26k folios pero la mediana de diferencia es 6.86 pesos y el Q1 es 2.48 -> casi todo son centavos de redondeo; el umbral VALIDATION_DIFFERENCE_THRESHOLD=1 peso deja pasar demasiado en proveedores grandes. Decision de umbral pendiente con Oscar/Monica, documentada en ESTADO_ACTUAL.md.

**Archivos:** `outputs`

---

### 2026-07-24 12:55:15 — [DECISIÓN] R25: de SORIANA_2025_PROJECTS solo se toma 2025 (sus años previos estan incompletos)

Oscar aclaro que la informacion anterior a 2025 que devuelve SORIANA_2025_PROJECTS NO es del todo correcta: en ocasiones esta incompleta. Instruccion explicita: de esa base solo se toma 2025, y de SORIANA_PROJECTS todo el resto del periodo. Esto es exactamente lo que ya hacia FUENTES_COMPRAS en database.py, asi que NO hubo cambio funcional; lo que faltaba era dejar constancia del porque para que nadie amplie esos rangos creyendo que corrige algo. Se documento como regla R25 en LOGICA_NEGOCIO.md, con advertencia en el comentario de FUENTES_COMPRAS, en PLANEACION.md y en ESTADO_ACTUAL.md. El riesgo de ampliar el rango no es solo duplicar renglones (Selecta mostro 2022/2023/2024 con conteos identicos en ambas bases): es meter datos parciales en la auditoria.

**Archivos:** `automation_costos/database.py`, `docs/LOGICA_NEGOCIO.md`, `docs/PLANEACION.md`, `docs/ESTADO_ACTUAL.md`

---

### 2026-07-24 12:44:20 — [DATO] SORIANA_2025_PROJECTS no contiene solo 2025

Al verificar Selecta 741 se encontro que la base SORIANA_2025_PROJECTS tambien trae 2022, 2023 y 2024, con los MISMOS conteos que SORIANA_PROJECTS (3570, 5443, 5572). Hoy no hay duplicacion porque fetch_compras recorta el periodo pedido contra el rango de años de cada fuente (FUENTES_COMPRAS) y solo le pide 2025 a esa base, pero si alguien amplia ese rango se duplicarian los renglones en silencio. CONFIRMADO de paso que Selecta 741 esta completo 2020-2025: 21962+12726+3570+5443+5572 de 2020-2024 mas 3183 de 2025 mas 6102 con rcvdt nulo = 58,558 renglones, que es exactamente lo que tienen los archivos de outputs/.

**Archivos:** `automation_costos/database.py`, `docs/PLANEACION.md`

---

### 2026-07-24 12:44:18 — [BUG] Compras de proveedor gigante: ZIP64 obligatorio en xlsxwriter

Con el problema de memoria ya resuelto, Celaya llego hasta el cierre del libro y ahi murio con zipfile.LargeZipFile / xlsxwriter FileSizeError: 'Filesize would require ZIP64 extensions'. Un .xlsx es un ZIP y el de 1.24M filas x 105 columnas rebasa los limites del ZIP clasico. Fix: Workbook(..., {'constant_memory': True, 'use_zip64': True}) en excel_exporter.write_compras_workbook. Ademas, si la escritura falla ahora se borra el .xlsx trunco en vez de dejar un archivo de 1 KB que parece una salida buena. Verificado que use_zip64 no altera la salida de archivos normales (zipfile solo activa las extensiones cuando hacen falta).

**Archivos:** `automation_costos/excel_exporter.py`

---

### 2026-07-24 12:43:49 — [CÓDIGO] Memoria del pipeline: proveedores de mas de un millon de renglones

Empacadora Celaya (73692, 1,244,498 renglones) reventaba con numpy ArrayMemoryError en prepare_compras_dataframe. Causa: la cadena de preparacion hacia CINCO copias completas encadenadas del DataFrame (prepare -> recalculate -> add_derived_base_columns -> _recalculate_invoice_level -> apply_display_formula_values) mas tres en la Validacion, y arrastraba las columnas sobrantes de F_COMPRAS; con 1.24M filas x 105 columnas object cada copia son ~9 GB. Cambios: (1) parametro en_sitio=True en toda la cadena de calculations.py, una sola copia; (2) recorte de columnas sobrantes ANTES de calcular; (3) clean_code, make_folio y normalize_date_columns vectorizados en utils.py (clean_code_series, make_folio_series, _normalize_date_series) - eran bucles Python de 1.2M iteraciones que ademas construian listas de strings; (4) la Validacion copia solo sus 31 columnas fuente en vez de las 105, no recalcula folio tres veces, y prefiltra los folios que califican de forma vectorizada en vez de recorrer ~100k grupos en Python; (5) build_pending_edi_dataframe acumula la mascara columna a columna en vez de materializar df[EDI].astype(str); (6) fetch_compras lee con fetchmany en lotes de 100k en vez de fetchall; (7) el pipeline genera la Validacion ANTES del Compras - es el entregable real y es chica, asi sale aunque el Compras gigante falle. EQUIVALENCIA VERIFICADA: re-corrido Selecta 741 completo, el Compras salio identico celda a celda (58,558 x 105 columnas, 0 diferencias) y la Validacion tambien (Consolidado 188 filas, Detalle 1,119, todas las sumas iguales). Tambien se verificaron una a una clean_code_series vs clean_code, make_folio_series vs make_folio, normalize_date_columns vectorizado vs el apply escalar, la mascara de pendientes y el prefiltro de folios. Resultado en Celaya: memoria estable en 13.4 GB (antes reventaba), el pipeline llego hasta el final.

**Archivos:** `automation_costos/calculations.py`, `automation_costos/utils.py`, `automation_costos/validation_exporter.py`, `automation_costos/database.py`, `automation_costos/pipeline.py`

---

### 2026-07-24 10:34:32 — [BUG] main.py: import perezoso de la GUI

run_app (customtkinter) se importaba en el tope de main.py, rompiendo TODOS los subcomandos de terminal si customtkinter no esta en el interprete usado. Se movio el import dentro de la rama gui, como los demas imports pesados. Ademas: el pipeline debe correrse con .venv/Scripts/python.exe (tiene xlsxwriter, duckdb, customtkinter); el Python global no. Re-ejecutado Selecta 741 completo 2020-2025: 58,558 filas (3,183 de 2025), 30.6% con CFDI, Consolidado 195 filas.

**Archivos:** `main.py`

---

### 2026-07-24 10:22:55 — [CÓDIGO] Compras 2025 desde SORIANA_2025_PROJECTS

F_COMPRAS esta partido por año en dos bases del mismo servidor: SORIANA_PROJECTS (2020-2024) y SORIANA_2025_PROJECTS (2025). fetch_compras() ahora recorta el periodo pedido contra el rango de cada fuente (FUENTES_COMPRAS) y concatena; un periodo 2020-2025 hace dos consultas, uno de un solo rango hace una. Verificado con Selecta 741: 2024=6949, 2025=3183, completo=58558 filas. Se levanta el bloqueo de REVISAR 2025.

**Archivos:** `automation_costos/database.py`, `config.py`, `docs/PLANEACION.md`

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

**Archivos:** `automation_costos/validation_exporter.py`

---

### 2026-07-23 14:27:43 — [CÓDIGO] Pipeline de una sola accion: compras -> cruce -> recalculo -> validacion

Nuevo modulo automation_costos/pipeline.py con generar_salida_proveedor(vendor, start, end, parquet, outdir). Encadena las 4 etapas post-descarga EN MEMORIA: fetch_compras desde SQL, cruce con CPA Vision (RFC auto-detectado del cnpj, filtrado por codigo de barras), recalculo, y Validacion de Condiciones armada desde el DataFrame sin releer el Compras gigante. Escribe dos archivos: Compras completo (opcion B) y Validacion (el entregable). Expuesto como subcomando 'python main.py cpa-salida' y como boton 'Generar salida completa (1 clic)' en la tarjeta ETAPA 2 de la GUI (usa Proveedor y fechas de la barra superior; el boton de solo-cruce quedo como paso secundario). PILOTO REAL exitoso con Selecta del Campo (741) periodo completo 2020-2025: 55,375 renglones, 27.3% con CFDI encontrado (15,090), Consolidado de 195 filas de diferencias, Detalle PAGOS de 1,125 filas. Compras 27.6 MB, Validacion 135 KB, 3 hojas correctas (Resumen, Consolidado, Detalle PAGOS). GUI construye OK con los 6 indicadores. Este es el flujo que produce los entregables de los 6 urgentes.

**Archivos:** `automation_costos/pipeline.py`, `automation_costos/app.py`, `main.py`, `docs/CRUCE_IMPLEMENTACION.md`

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

**Archivos:** `automation_costos/excel_exporter.py`, `automation_costos/calculations.py`, `requirements.txt`, `docs/RENDIMIENTO_EXPORTADOR.md`

---

### 2026-07-23 10:31:02 — [CÓDIGO] El cruce ahora SOLO rellena celdas vacias (regla de negocio de Oscar) + piloto real con Nestle

Oscar aclaro que el cruce no debe llenar todo, solo las columnas VACIAS de Compras, y que si muchas quedan sin llenar esta bien. Correccion importante: antes se sobrescribia la columna entera (pisaba datos que Compras ya traia). Ahora cada columna se escribe solo donde _vacio() es cierto y hay valor cruzado; las derivadas ctobto_edi/impart_edi tambien solo en huecos con insumo; nunca se pisa un dato ni se rellena con 0 un renglon sin CFDI. Nueva metrica principal: celdas vacias rellenadas (ya no tasa de cruce). Se agrego _vacio() y el campo celdas_llenadas al ResultadoCruce. PILOTO REAL de punta a punta con Nestle (5462) 2024 desde SQL: 134,850 renglones de compras, RFC auto-detectado MNE0409226K9, filtrado a 650 codigos de barras (viable en memoria), 696,069 conceptos de CPA cargados en 5s, cruce en 9s. Resultado: 93,827 renglones (69.6%) encontraron CFDI, 282,481 celdas vacias rellenadas, 41,023 sin CFDI se dejan como estan. Techo real medido: 82.8% de los renglones tienen un CFDI que empata por codigo de barras + factura; el resto no tiene match (codigo que no coincide o factura ausente, reunion 1 R3). DIAGNOSTICO de ambiguedad: de 90,072 llaves repetidas, 99.94% tienen el mismo valor unitario (mismo producto en varias lineas de la misma factura); _indexar ahora colapsa las identicas y solo descarta las que chocan de verdad. Fix de dtype: convertir la columna destino a object antes de rellenar (pandas nuevo no deja meter texto en float64). test_cruce_cpa.py actualizado a la semantica de llenar-solo-huecos (vacia el bloque EDI antes de cruzar, como Pendientes_EDI); pasan las 3 validaciones. GUI construye OK.

**Archivos:** `automation_costos/cruce_cpa.py`, `test_cruce_cpa.py`, `scripts/piloto_cruce.py`, `docs/CRUCE_IMPLEMENTACION.md`

---

### 2026-07-23 10:01:29 — [CÓDIGO] Cruce: deduplicacion de request_id y filtrado por codigo de barras para escala

Dos cambios en cruce_cpa. (1) DEDUPLICACION: cargar_cpa asigna cada year al request_id mas completo (mas anios distintos, a igualdad mas filas) via ROW_NUMBER en DuckDB, y descarta el resto. Resuelve la duplicacion del 2025 en Pepsico (req 619617 vs 619939) y Nestle (618728 vs 620512) sin borrar particiones. Se conserva un solo request como pidio Oscar. (2) FILTRADO POR CODIGO DE BARRAS: cargar el proveedor completo a pandas agota memoria (Pepsico 16M filas dio ArrowMemoryError). Ahora cargar_cpa recibe el set de codigos de barras del Compras y filtra en DuckDB con IN (SELECT bc FROM codigos), normalizando igual en ambos lados (ltrim(regexp_replace) = solo_digitos). Solo llega a memoria lo cruzable. (3) Nueva funcion orquestadora cruzar_proveedor(compras_path, parquet_root, rfc=None) que lee el Compras, resuelve el RFC (arg o cnpj), arma los barcodes, carga CPA filtrado y cruza; devuelve (ResultadoCruce, rfc). La GUI y el CLI se simplificaron para usarla. Verificado que todo importa y la GUI construye. Prueba piloto con Nestle (5462) en curso: generando su Compras 2020-2025 desde SQL.

**Archivos:** `automation_costos/cruce_cpa.py`, `automation_costos/app.py`, `main.py`, `docs/CRUCE_IMPLEMENTACION.md`

---

### 2026-07-23 08:29:07 — [CÓDIGO] El cruce detecta el RFC solo desde el Compras (resuelve el problema numero->RFC)

Oscar planteo que muchas veces no se sabe el RFC de un proveedor a partir del vendor number. Solucion: no hace falta una tabla de mapeo, porque el archivo de Compras ya trae el RFC en la columna cnpj. Nueva funcion cruce_cpa.rfc_de_compras() que lo lee. La GUI y el CLI ahora auto-detectan el RFC del Compras; el campo RFC de la GUI paso a ser opcional (solo para forzar otro). Verificado: rfc_de_compras devuelve ALC0011111Y9 del archivo real de Alceda, ignora nulos, y la GUI construye. Flujo: numero de proveedor -> F_COMPRAS -> Compras.xlsx -> cnpj -> RFC -> Parquet. El auditor nunca teclea el RFC.

**Archivos:** `automation_costos/cruce_cpa.py`, `automation_costos/app.py`, `main.py`

---

### 2026-07-22 16:03:18 — [CÓDIGO] GUI rehecha con el lenguaje visual PRGX e integrado el cruce de CPA Vision

RESPUESTA A LA PREGUNTA DE OSCAR: no, el cruce NO estaba en la GUI; app.py solo tenia los tres botones de la Etapa 1 y cero menciones de CPA Vision. Ahora si esta. CAMBIO 1 - INTEGRACION: nueva tarjeta ETAPA 2 con el boton 'Rellenar EDI desde CPA Vision', mas campos de RFC y carpeta Parquet. Toma como entrada el 'Compras editado' de la Etapa 1, vuelca las metricas completas del cruce en la bitacora (tasa de cruce, desglose por estrategia y discrepancias de la doble validacion), escribe <nombre>_EDI.xlsx y lo deja seleccionado como entrada del siguiente paso. Si el RFC no tiene datos en el Parquet lo dice en vez de generar un archivo vacio. CAMBIO 2 - VISUAL: se replico el lenguaje de Conciliacion_Memo_Panoptic. Nuevo modulo automation_costos/ui.py con las paletas PRGX clara y oscura, la clase Tema, la clase Indicadores (puntos de estado y barras de progreso con parpadeo) y fabricas de widgets (tarjeta, titulo_seccion, boton_principal, boton_paso, separador, pista, campo, boton_secundario). ui.py no importa nada del dominio, asi que es reutilizable en otras herramientas de la suite. app.py se reescribio con customtkinter: encabezado con icono PRGX, subtitulo 'PRGX · Soriana Audit Suite', logo Soriana y toggle de tema; barra de configuracion; dos tarjetas con insignia numerada; y bitacora con timestamp gris y mensajes coloreados por tipo. Assets copiados de Panoptic a automation_costos/assets. CONCURRENCIA: _ejecutar() centraliza el patron de hilo daemon mas indicador; los widgets solo se tocan desde el hilo de Tk via queue e Indicadores.estado() reencola con after(0). BUILD: AutomationCostos.spec actualizado con collect_submodules('automation_costos') porque los subcomandos importan dentro de funciones, collect_data_files('customtkinter') porque carga temas JSON en runtime, la carpeta assets, templates y el icono .ico. Nuevo scripts/build_release.py que compila y empaqueta en dist/AutomationCostos_<version>_<fecha>.zip. requirements.txt actualizado con customtkinter, duckdb y pyarrow. VERIFICADO: la GUI construye, el toggle de tema funciona en ambos sentidos y se capturaron pantallazos de los dos modos. PENDIENTE: no se ha compilado ni probado el .exe.

**Archivos:** `automation_costos/app.py`, `automation_costos/ui.py`, `automation_costos/assets`, `AutomationCostos.spec`, `scripts/build_release.py`, `requirements.txt`, `docs/GUI.md`, `CLAUDE.md`

---

### 2026-07-22 15:37:14 — [CÓDIGO] Implementado el cruce CPA Vision -> Compras

Nuevo modulo automation_costos/cruce_cpa.py y subcomando 'python main.py cpa-cruce'. Arquitectura: funciones puras mas un dataclass ResultadoCruce, sin estado global. Lee el Parquet con DuckDB para aprovechar el particionado por RFC y no cargar 66M de filas a memoria. CRUCE EN DOS PASADAS: principal por codigo de barras mas Serie+Folio normalizados (mayusculas sin caracteres no alfanumericos, para absorber los formatos FN-21226 / FN21226 / -21226), y respaldo por codigo de barras mas la parte numerica del folio, aplicado solo a los renglones que no cruzaron. Las llaves ambiguas (mas de un concepto del CFDI) se DESCARTAN en vez de tomar una al azar, y se reportan; preferimos no llenar un dato a llenarlo mal. El codigo de barras se normaliza a digitos, lo que de paso resuelve C17 (notacion cientifica). DOBLE VALIDACION PERMANENTE: ademas de copiar el importe del CFDI se calcula la formula sobre totfactura en columnas de control impiva_edi_formula e imieps_edi_formula, y se reporta cuantos renglones difieren. BUG ENCONTRADO Y CORREGIDO durante la implementacion: la primera version leia factem_edi asumiendo que ya venia lleno, pero medido en Alceda fact_empaq esta lleno al 100% (400/400) y factem_edi solo al 24% (98/400); factem_edi hay que LLENARLO desde fact_empaq. Sin la correccion, ctobto_edi e impart_edi habrian salido en 0 para el 76% de los renglones. PRUEBA: test_cruce_cpa.py usa invnbr y codbarra reales de Alceda y simula el lado de CPA Vision; resultado 98.5% de cruce sobre 400 renglones (los 6 sin cruce no tienen invnbr o codbarra) y pasan las tres validaciones de calculo. PENDIENTE: no se ha podido validar contra un proveedor real que exista en ambos lados, porque ninguno de los 43 RFC descargados coincide con los archivos de Compras disponibles.

**Archivos:** `automation_costos/cruce_cpa.py`, `main.py`, `test_cruce_cpa.py`, `docs/CRUCE_IMPLEMENTACION.md`, `CLAUDE.md`

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
