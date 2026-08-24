# Qué es dbt — explicado con la lógica de este proyecto

> **Esto es material de estudio, no una propuesta.** No se usa dbt en Automation-Costos y
> nada de esta carpeta se ejecuta. Es para entender qué es la herramienta y qué haría (y qué
> NO haría) si algún día se evaluara.

---

## 1. La idea en una frase

**dbt convierte una carpeta de archivos `.sql` en un pipeline de datos versionado, probado y
documentado.** Tú escribes puros `SELECT`; dbt se encarga de crear las tablas, ponerlas en el
orden correcto, probarlas y dibujar el diagrama de dependencias.

Su lema es *"transformación como código"*. La T de **ELT**: extraer y cargar los datos crudos
lo hace otra cosa; dbt solo transforma **lo que ya está dentro de la base**.

## 2. El problema que resuelve

Cualquiera que haya mantenido lógica de negocio en SQL conoce estos dolores:

| Dolor | Qué hace dbt |
|---|---|
| "¿Cuál era la consulta buena?" `costos_v2_FINAL_ok.sql` | Cada modelo es **un archivo en git**, con historial y revisión |
| "Cambié algo y rompí un reporte que ni sabía que dependía de esto" | dbt conoce el **grafo de dependencias** y te dice qué se rompe |
| "Hay que correr 12 consultas en cierto orden y nadie recuerda cuál" | dbt **deduce el orden solo** a partir de las referencias |
| "El folio debería ser único... creo" | **Tests declarativos**: `unique`, `not_null`, y los tuyos propios |
| "¿De dónde sale `imp_aud`?" | **Documentación** que se genera sola, con linaje navegable |
| "En desarrollo apunto a otra base y siempre se me olvida cambiarlo" | **Entornos** (dev/prod) con la misma definición |

## 3. Las tres piezas que hay que entender

### a) Un modelo es un `SELECT`, no un `CREATE TABLE`

Escribes esto en `models/marts/fct_costo_auditado.sql`:

```sql
select folio, sum(imp_aud) as debio_pagar
from {{ ref('int_costo_auditado') }}
group by folio
```

y dbt genera el `CREATE TABLE ... AS SELECT` (o la vista) por ti. **Nunca escribes DDL.**
El nombre del archivo es el nombre de la tabla resultante.

### b) `ref()` es lo que hace toda la magia

`{{ ref('int_costo_auditado') }}` significa "la tabla que produce ese otro modelo". Con eso
dbt sabe dos cosas a la vez:

1. **El orden**: ese modelo va antes que este.
2. **El linaje**: si tocas el de arriba, este se ve afectado.

Es la diferencia central contra un montón de scripts sueltos: las dependencias son
**declaradas**, no algo que vive en la cabeza de quien lo escribió.

### c) Los tests son parte del modelo

En un `schema.yml` declaras qué debe cumplirse:

```yaml
- name: folio
  tests: [unique, not_null]
```

y `dbt test` lo verifica contra los datos reales. Un test que falla **detiene el pipeline**,
en vez de que el error llegue al entregable del auditor.

## 4. Cómo se vería ESTE proyecto en dbt

Estos son los archivos de la carpeta, y qué módulo real reemplazaría cada uno:

| Modelo dbt | Qué hace | Módulo real hoy |
|---|---|---|
| `stg_compras.sql` | Limpia `F_COMPRAS`, arma el **folio** | `calculations.add_derived_base_columns` |
| `stg_cpa_vision.sql` | Normaliza los CFDI del Parquet | `cpa_parquet.py` |
| `int_compras_con_cfdi.sql` | **El cruce**: pega el CFDI por factura + código de barras | `cruce_cpa.py` |
| `int_costo_auditado.sql` | **El corazón**: `cto_aud`, impuestos, `imp_aud` | `calculations.recalculate_dataframe` |
| `fct_validacion_consolidado.sql` | Suma por folio, compara contra lo pagado | `validation_exporter.py` |
| `schema.yml` | Los tests y la documentación | *(hoy: nada equivalente)* |

El linaje que dbt dibujaría solo:

```
stg_compras ─────┐
                 ├──> int_compras_con_cfdi ──> int_costo_auditado ──> fct_validacion_consolidado
stg_cpa_vision ──┘
```

Ese diagrama **no se dibuja a mano**: sale de los `ref()` que hay en el SQL.

## 5. Lo que dbt NO haría por este proyecto

Esto es lo más importante de todo, y la razón por la que no es una recomendación:

| Parte del proyecto | ¿dbt? |
|---|---|
| Scraping de CPA Vision con Playwright | ❌ Nada. dbt no extrae datos |
| Descargar ZIPs y convertirlos a Parquet | ❌ Nada. Eso es la E y la L de ELT |
| **Escribir el Excel** con formato, fórmulas y hojas | ❌ **Nada.** Y es buena parte del valor del entregable |
| La GUI | ❌ Nada |
| Cruce, recálculo y consolidado | ✅ Aquí sí encaja bien |

Es decir: dbt cubriría **el centro** del pipeline (la transformación), y seguirías necesitando
Python para todo lo de los extremos. No es un reemplazo de Automation-Costos; sería, en el
mejor de los casos, un inquilino de una parte.

### Dos fricciones concretas si se intentara aquí

1. **dbt trabaja dentro de una base de datos.** Hoy los CFDI viven en Parquet y el cruce se
   hace en DuckDB/pandas. Habría que cargar todo a SQL Server, o adoptar `dbt-duckdb`.
2. **`F_COMPRAS` es una función con parámetros**, no una tabla. dbt asume tablas y vistas; una
   función con `(proveedor, fecha_ini, fecha_fin)` no encaja de forma natural en un `source`.

## 6. Lo que sí vale la pena robarle a dbt

Aunque no se adopte la herramienta, tres ideas suyas aplican tal cual y son gratis:

1. **Tests declarativos sobre el resultado.** El cuadre que hicimos a mano con ARCA — "los
   75,717 folios están, ninguno falta, ninguno sobra" — es exactamente un test de dbt. Hoy se
   verifica cuando alguien se acuerda; podría correr siempre.
2. **Nombrar las capas.** `stg_` / `int_` / `fct_` obliga a separar "limpiar" de "calcular la
   regla de negocio" de "armar el entregable". El proyecto ya lo hace, pero sin nombrarlo.
3. **Que el linaje viva en el código.** Hoy el orden de los pasos está en la cabeza y en
   `docs/`. Cuando el orden es una consecuencia del código, no se desincroniza.

## 7. Los cinco comandos que existen

```bash
dbt run      # construye las tablas, en el orden correcto
dbt test     # corre las pruebas contra los datos reales
dbt build    # run + test, modelo por modelo (lo normal en producción)
dbt docs generate && dbt docs serve   # la web con el linaje navegable
dbt run --select int_costo_auditado+  # ese modelo y TODO lo que depende de él
```

Ese `+` del final es el argumento de venta en una frase: *"cambié la regla del costo
auditado, reconstruye todo lo que se vea afectado"* — y dbt sabe qué es.
