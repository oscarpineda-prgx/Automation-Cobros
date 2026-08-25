# Interfaz gráfica — PRGX Soriana Audit Suite

> **Última actualización:** 2026-08-24
> **Archivos:** [`automation_costos/ui.py`](../automation_costos/ui.py) (presentación) ·
> [`automation_costos/app.py`](../automation_costos/app.py) (aplicación)

---

## 1. Por qué se reestructuró (2026-08-24)

La pantalla estaba agrupada en **"Etapa 1" / "Etapa 2"**, que describe *cómo se construyó el
código*, no *cómo trabaja el auditor*. La prueba fue una pregunta real de una auditora:

> *"Le di a generar Compras preliminar, luego a descargar información de CPA. ¿Ahora qué?"*

La interfaz no se lo contestaba, porque los botones estaban ordenados por **de qué módulo
salen**, no por **en qué orden se usan**.

La pregunta que sí se hace el usuario al abrir es **"¿cuántos proveedores?"**, y por ahí se
organiza ahora:

| Vista | Para qué | Quién |
|---|---|---|
| **Un proveedor** | El trabajo del día, interactivo | El auditor |
| **Por lotes** | Tandas desatendidas de horas | Óscar |
| **Ajustes** | Credenciales, carpetas, conexión, tema | Se toca una vez |

## 2. Separación de responsabilidades

| Archivo | Contiene |
|---|---|
| `ui.py` | Paletas, `Tema`, `BarraEstado`, `Paso` y fábricas de widgets. **Cero lógica de negocio.** |
| `app.py` | La aplicación: composición de vistas y llamadas a los módulos del paquete. |

`ui.py` no importa nada del dominio, así que puede reutilizarse en otra herramienta de la
suite sin arrastrar dependencias.

## 3. Presupuesto de recursos

Esto corre en equipos de **un solo núcleo**. En customtkinter cada widget con esquinas
redondeadas es un `CTkCanvas`, y cada animación continua es CPU que no vuelve.

| Medido al abrir | Antes | Ahora |
|---|---:|---:|
| Arranque | 2.62 s | **1.45-1.76 s** |
| Widgets vivos | 343 | **181** |
| `CTkCanvas` | 100 | **53** |
| Barras de progreso | 8 | **1** |

Las tres palancas, en orden de impacto:

1. **Solo se construye la vista activa.** Antes las tres tarjetas nacían de golpe. Ahora una
   vista se crea la **primera vez que se visita** y después solo se oculta con
   `grid_remove()`: crear widgets Tk es lo caro, tenerlos ocultos no. Volver a una vista ya
   construida cuesta 0.14 s.
2. **Una sola barra de estado.** Había un punto y una barra de progreso **por botón** —ocho
   canvas animables para una aplicación que solo hace una cosa a la vez.
3. **El latido es un reloj de 1 Hz, no una animación.** La barra indeterminada de
   customtkinter se redibuja de continuo; un reloj que avanza cada segundo contesta
   "¿sigue vivo?" igual de bien por un redibujo de texto. La barra de progreso **solo
   aparece cuando hay algo real que medir** (3 de 12 proveedores), nunca como decoración.

También se quitó el botón de tema del encabezado (vive en Ajustes: se toca una vez y ahí
costaba un canvas permanente).

> ⚠️ **El scroll del área de vistas NO se quita.** Se intentó y fue un error: medido, las
> vistas piden entre 684 y 752 px, y con el encabezado, el contexto, las pestañas, la barra
> de estado y la bitácora **no caben en 900 px** — menos aún en un 1366x768, que es lo que
> hay en los equipos de destino. Lo que se pierde al recortar es justo el borde inferior: el
> botón de ejecutar. Es **un** `CTkScrollableFrame` para las tres vistas, no uno por vista.

## 4. Lenguaje visual (heredado de Panoptic)

- **Paleta PRGX** en dos modos, claro y oscuro, con el mismo juego de claves
  (`bg1`, `card`, `accent`, `t1`, `s_ok`...). El acento morado `#611EEC` es la firma PRGX.
- **Franja de acento** de 3 px arriba del encabezado.
- **Encabezado**: icono PRGX · título + `PRGX · Soriana Audit Suite` · logo Soriana.
- **Bloques** con esquinas redondeadas y borde de 1 px.
- **Bitácora** con timestamp en gris y el mensaje coloreado según sea info, ok o error.

### Assets
`automation_costos/assets/` — `prgx-icon.png`, `prgx-icon.ico`, `Soriana-Logo.png`.

## 5. Estructura de la pantalla

```
+- PRGX · Automation Costos ------------------- [Soriana] -+
+----------------------------------------------------------+
| |Un proveedor|   Por lotes   Ajustes                      |  vistas
+----------------------------------------------------------+
|                    (la vista activa)                     |  crece
+----------------------------------------------------------+
| * en curso · Descargando de CPA Vision · 04:32 [#Detener]|  estado
| ############----------------------------------------     |
+----------------------------------------------------------+
| v  BITÁCORA DE EJECUCIÓN                      [Limpiar]  |  plegable
| 15:04:12  Compras generado: Compras_391250.xlsx          |  130 px
+----------------------------------------------------------+
```

**Solo el área de vistas crece.** La barra de estado y la bitácora son de alto fijo, y la
bitácora **se pliega** con un clic en su título hasta dejar solo esa línea. Antes se llevaba
una porción variable de la ventana (`weight=2`), que en pantallas chicas es justo el alto que
le hace falta a la vista — donde están los botones.

**Dónde va cada campo.** No hay barra de contexto compartida: cada dato vive donde se usa.

| Campo | Dónde | Por qué |
|---|---|---|
| Proveedor · Desde · Hasta | Vista **Un proveedor** | Solo esa vista trabaja sobre un proveedor concreto; en «Por lotes» cada renglón trae el suyo |
| Carpeta de **Salida** | Vista **Ajustes** | Sí es compartida —las dos vistas generan entregables—, así que va con las demás carpetas. Las otras dos vistas la **anuncian** en letra chica |
| Credenciales, Parquet, Descargas, RFC | Vista **Ajustes** | Se tocan una vez |

## 5a. Vista «Un proveedor» — la lista de pasos

```
+- Camino rápido -----------------------------------------+
| Compras -> cruce con CPA -> recálculo -> Validación      |
| +------------------------------------------------------+ |
| |  >     GENERAR TODO                                  | |
| +------------------------------------------------------+ |
+----------------------------------------------------------+
+- Paso a paso -------------------------------------------+
| Para cuando el auditor edita el Compras en Excel         |
|                                                          |
|  v  1  Generar Compras preliminar   Compras_391250.xlsx  |
|  v  2  Descargar de CPA Vision      DAC110216KX3 ...     |
| >   3  Rellenar EDI con los CFDI    <-  siguiente        |
|  ·  4  Recalcular el Compras editado                     |
|  ·  5  Generar Validación de Condiciones                 |
+----------------------------------------------------------+
```

**Cada renglón numerado *es* el botón.** Esto es lo que contesta "¿y ahora qué?" sin que
nadie tenga que preguntar, y es la razón de ser del rediseño.

Decisiones que conviene no deshacer:

- **El estado sale de lo que hay en disco y en los campos, no de la última corrida.** Cerrar
  la aplicación a media faena y volver a abrirla muestra el mismo mapa. La tabla vive en
  `_pasos_hechos()`:

  | Paso | Se da por hecho cuando... |
  |---|---|
  | 1 Compras | hay un `archivo_editado` o `archivo_recalculado` |
  | 2 Descargar CPA | existe la partición `parquet/rfc=<RFC>` |
  | 3 Rellenar EDI | el nombre del archivo en curso contiene `_EDI` |
  | 4 Recalcular | hay un `archivo_recalculado` |
  | 5 Validación | hay un `archivo_validacion` |

- **Lo que no se puede saber barato se deja como pendiente.** Es preferible que la lista se
  quede corta a que asegure algo falso.
- **`> siguiente` marca la ruta habitual, no un candado.** Ningún paso bloquea a otro: un
  proveedor sin CPA se salta el 2 y el 3 sin pelear con la interfaz. Hay una pista bajo la
  lista que lo dice explícitamente.
- **El `exists()` del Parquet se memoriza** (`_cache_parquet`): el acervo vive en una unidad
  de red y esto se consulta en cada repintado. La memoria **se tira entera al terminar
  cualquier operación**, porque una descarga acaba de crear particiones nuevas.
- **El cambio de tema se bloquea mientras algo corre.** Reconstruye la ventana entera, y
  destruir la barra de estado a media operación dejaría al hilo de fondo publicando en
  widgets muertos. Nadie cambia de tema en mitad de una descarga de dos horas.

### Las pestañas no usan `CTkSegmentedButton`

Tiene un **único** `text_color` para todos sus segmentos, y aquí hacen falta dos: blanco
sobre el acento para la activa, y texto oscuro sobre gris claro para las inactivas. Con un
solo color, en modo claro las inactivas quedaban en blanco `#FFFFFF` sobre `#F3F6FA`:
invisibles. Se rehízo con `CTkButton` normales (`ui.Pestanas`), que es el mismo patrón que ya
usa `Paso`. Hay una prueba de contraste automática: ningún par texto/fondo baja de 3.0:1 en
ninguno de los dos temas.

## 5b. El cruce de CPA Vision (paso 3 de la lista)

El paso **3 · "Rellenar EDI con los CFDI"**:

1. Toma el **RFC** y la **carpeta del dataset Parquet** de la vista de Ajustes.
2. Usa como entrada el **"Compras editado"** del paso 1 (pide el archivo si está vacío).
3. Llama a `cruce_cpa.cruzar()` y **vuelca las métricas completas en la bitácora**
   (tasa de cruce, desglose por estrategia, discrepancias de la doble validación).
4. Escribe `<nombre>_EDI.xlsx` y **lo deja seleccionado como "Compras editado"**, de modo
   que el siguiente paso natural sea recalcular.

Si el RFC no tiene datos en el Parquet, lo dice explícitamente en vez de generar un archivo
vacío.

> Detalle del cruce en [CRUCE_IMPLEMENTACION.md](CRUCE_IMPLEMENTACION.md).

## 5c. Vista «Por lotes» — la cola de trabajo (2026-08-24)

El portal **encola por usuario**: hasta que no termina una descarga, la siguiente no arranca.
Por eso el trabajo real es una fila secuencial de proveedores, **cada uno con su periodo**.

Se captura por **número de proveedor**, no por RFC: al agregar, la interfaz resuelve
`(rfc, nombre)` contra SQL con `database.resolver_proveedor` y **muestra el nombre**. Un
dígito mal tecleado se ve al instante y no a media tanda; si el proveedor no tiene compras en
el periodo, la fila se rechaza ahí mismo.

### Qué hacer con cada proveedor

Cada renglón lleva **su propia acción**. No son cuatro caminos distintos, son tres
interruptores (`descarga` · `genera` · `cpa`), y por eso el `if` no se reparte por la
interfaz: vive en la tabla `cola_descarga.ACCIONES`.

| Acción | Descarga | Genera | Cruce EDI |
|---|:--:|:--:|:--:|
| **Solo descargar** *(omisión)* | ✔ | — | — |
| **Descargar y generar** | ✔ | ✔ | ✔ |
| **Generar con lo ya descargado** | — | ✔ | ✔ (con lo que hay en el Parquet) |
| **Generar sin cruce de CPA** | — | ✔ | — (`--sin-cpa`) |

Cada opción lleva **su explicación en letra chica bajo el desplegable** (`Accion.ayuda`), que
cambia al elegir otra: son cuatro opciones parecidas y el nombre solo no alcanza.

> **Sobre los nombres.** Antes eran *"Generar con CPA"* y *"Generar sin CPA"*, y se leían como
> variantes de descargar. El `con/sin CPA` **no acompaña al descargar sino al generar**:
> descargar es siempre de CPA Vision, no hay otra fuente. Las **claves no cambiaron**
> (`generar`, `generar_sin_cpa`), así que las colas guardadas siguen leyéndose, y `_ALIAS`
> mantiene vivos los nombres viejos para un Excel de lote exportado antes del cambio.

### Las dos fases

`▶ Ejecutar la cola` corre **primero todas las descargas y después todas las salidas**. Ese
orden es lo que hace que «Descargar y generar» salga de un solo clic: cuando el pipeline lee
el Parquet, lo descargado ya está ahí.

```
_cola_ejecutar
  ├── _cola_fase_descarga → Excel RFC/FECHAS → cpa_vision.request_vendor_master_batch
  └── _cola_fase_salida   → TrabajoSalida    → ejecutor.ejecutar
```

| Pieza | Dónde | Responsabilidad |
|---|---|---|
| `cola_descarga.py` | paquete | Modelo, acciones y persistencia. **Sin Tk ni Playwright** — se prueba solo |
| `ejecutor.py` | paquete | Qué comandos produce un proveedor. **El mismo que usa la terminal** |
| `ui.tabla()` · `ui.opciones()` | `ui.py` | `ttk.Treeview` y desplegable con la paleta PRGX |
| `app._tarjeta_cola` | `app.py` | Solo el cableado |

Decisiones que conviene no deshacer:

- **El periodo se valida con `cpa_vision._parse_years`**, el mismo parser del CLI. Acepta
  `2020-2025` y años sueltos `2021 2023`, y valida el rango 2014-2026. Duplicar la regla
  sería condenar a las dos copias a separarse.
- **Cada motor recibe lo que ya sabe leer**: un Excel temporal `RFC`/`FECHAS` para la
  descarga, un `TrabajoSalida` para la generación. La interfaz **no reimplementa** ni el
  scraping (reintentos, "Sin valores", métricas, inventario) ni la decisión de "proveedor
  gigante": las dos siguen siendo de sus motores.
- **Las dos fases llevan estado por separado** (`estado` y `estado_salida`). Con un solo
  campo, terminar la descarga sacaría de la fila a un proveedor al que todavía le falta el
  entregable.
- **`listos_para_generar()` ≠ `por_generar()`.** Un «Descargar y generar» cuya descarga
  falló sigue pendiente de generar, pero **no se genera**: saldría un entregable con el
  bloque EDI vacío y sin marcar error. Espera a que su descarga termine bien.
- **Los renglones se cuentan al arrancar la fase de salida**, con `database.contar_compras`
  (un `COUNT` en el servidor, segundos). De ese número depende si el proveedor va por el
  camino normal o por trimestres, y pedirlo al agregar habría cobrado la espera a quien solo
  quería descargar.
- **Cambiar la acción reinicia los estados**: lo que se pide ahora no es lo que se pidió
  antes, y dejar el "listo" de la fase anterior escondería trabajo por hacer.
- **`progreso` y `cancelado` son opcionales** en los dos motores. Por terminal no se pasan y
  todo se comporta igual que antes. `cancelado` se consulta **entre proveedores**, nunca a
  media descarga ni a media escritura de un entregable.
- **`sin_valores` y `omitido` cuentan como terminados**, no como error: en el primero el
  portal confirmó que ese RFC no tiene CFDI en el periodo; en el segundo el entregable ya
  existe en disco, que era justamente el objetivo. Reintentarlos solo gasta tiempo. Para
  forzarlo está el botón **Reintentar**.
- **La cola persiste** en `logs/cola_descarga.json`. Una tanda dura horas y cerrar la ventana
  no puede costar la lista. Una cola de una versión anterior (sin columna de acción) se lee
  como "Solo descargar", que era su significado original.
- **La estimación de tiempo solo aparece desde 4 proveedores pendientes**
  (`MINIMO_PARA_ESTIMAR`). Se muestra en minutos y es la suma de las dos fases:
  `descargas x 7.9 + salidas x 12.0`, así que un renglón «Descargar y generar» cuenta en
  las dos. Los minutos salen de medias reales: 7 m 52 s por descarga sobre 530 intentos, y
  ~12 min por entregable.
  Con 1, 2 o 3 proveedores **no se estima nada**: son promedios, y sobre tan pocos casos el
  promedio no promedia — un gigante solo ya se lleva horas. Un estimado que puede errar por
  un factor de diez es peor que no dar ninguno.

### Límite conocido

La fase de salida lanza `main.py` como **subproceso** con el intérprete del `.venv`. Bajo el
`.exe` empaquetado ese intérprete no existe: `ejecutor.ejecutar` lo comprueba de entrada y
aborta con un mensaje claro, en vez de dejar N fallos enterrados en N logs.

## 6. Concurrencia

`_ejecutar(clave, mensaje, tarea)` centraliza el patrón: arranca la `BarraEstado`, resalta
el paso `clave` como *en curso*, corre la tarea en un hilo daemon y cierra con `_terminado()`,
que además invalida la memoria del Parquet. La bandera `_ocupado` impide lanzar dos
operaciones a la vez.

Los widgets **solo se tocan desde el hilo de Tk**: los hilos de trabajo publican en una
`queue` que se drena con `after(120ms)`, e `Indicadores.estado()` reencola con `after(0)`.

### Widgets muertos tras reconstruir

Los widgets de las vistas se guardan como atributos (`self.tabla_cola`, `self.aviso_cola`,
`self.aviso_salida`...). Al cambiar de tema la ventana se reconstruye entera y esos atributos
quedan apuntando a widgets **destruidos**: configurarlos revienta con `TclError`, y un
`getattr(...) is not None` **no lo detecta**. Por eso existe `_widget(nombre)`, que comprueba
`winfo_exists()`. Úsalo siempre que toques un widget de vista desde fuera de su constructor.

## 7. Cambio de tema

Reconstruye la pantalla: guarda el texto de la bitácora, destruye los hijos, cambia la
paleta, vuelve a construir y restaura el texto. Los `StringVar` sobreviven porque son del
objeto, no de los widgets. Es la misma estrategia de Panoptic.

Dos cosas que hay que recordar al tocarlo: **se bloquea si hay algo corriendo** (ver 5a), y
`_vistas` y `_pasos` **se vacían** — apuntaban a widgets que acaban de morir. Tras el cambio
vuelve a nacer solo la vista activa.

## 8. Ejecutable y .zip

```bash
python scripts/build_release.py                 # compila y empaqueta
python scripts/build_release.py --sin-compilar  # solo re-empaqueta dist/
```

Produce `dist/AutomationCostos.exe` y `dist/AutomationCostos_<version>_<fecha>.zip`.

El `.spec` se actualizó para incluir lo que PyInstaller no detecta solo:

- `collect_submodules("automation_costos")` — los subcomandos de `main.py` importan dentro
  de funciones y el análisis estático no los ve.
- `collect_data_files("customtkinter")` — customtkinter carga sus temas JSON en runtime.
- La carpeta `assets` y `templates`.
- Icono `prgx-icon.ico`.

## 9. Pendiente

- [ ] **Compilar y probar el `.exe` en una máquina limpia.** El script está escrito pero
      no se ha ejecutado un build completo.
- [ ] Valorar un botón de "Detener" como el de Panoptic (hoy no hay cancelación).
