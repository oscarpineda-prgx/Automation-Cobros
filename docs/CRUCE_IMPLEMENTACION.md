# Implementación del cruce CPA Vision → Compras

> Cómo quedó construido el cruce y por qué. La **especificación funcional** (qué columna
> viene de dónde y con qué evidencia) está en
> [MAPEO_CRUCE_CPA_COMPRAS.md](MAPEO_CRUCE_CPA_COMPRAS.md).
>
> **Creado:** 2026-07-22 · **Módulo:** [`automation_costos/cruce_cpa.py`](../automation_costos/cruce_cpa.py)

---

## 0. Pipeline de una sola acción (lo que produce el entregable)

`automation_costos/pipeline.py` encadena las cuatro etapas post-descarga **en memoria**:

```
SQL (compras) → cruce CPA Vision → recálculo → Validación de Condiciones
```

Genera dos archivos: el **Compras** completo (opción B, se escribe aunque sea grande) y la
**Validación de Condiciones** (el entregable: Resumen + Consolidado + Detalle PAGOS). La
Validación se arma desde el DataFrame en memoria, sin releer el Compras gigante.

**No descarga nada** — asume que el Parquet ya existe.

Desde la GUI: botón **"Generar salida completa (1 clic)"** (usa Proveedor y fechas de la
barra superior). Desde terminal:

```bash
python main.py cpa-salida --vendor 741 --start 2020-01-01 --end 2025-12-31 \
    --parquet outputs/cpa_vision/parquet --output-dir outputs
```

**Piloto real (Selecta 741, 2020-2025):** 55,375 renglones, 27.3% con CFDI, Consolidado de
195 filas (las diferencias). Compras 27.6 MB, Validación 135 KB. Funcionó de punta a punta.

---

## 1. Cómo se usa (solo el cruce)

```bash
python main.py cpa-cruce \
    --compras "outputs/Compras_383612_ALCEDA.xlsx" \
    --parquet "outputs/cpa_vision/parquet" \
    --rfc ALC0011111Y9 \
    --output "outputs/Compras_383612_ALCEDA_cruzado.xlsx"
```

Imprime un resumen de métricas y escribe el Excel con las columnas EDI llenas.

## 2. Arquitectura

Un solo módulo con funciones puras y una estructura de resultado. Sin estado global,
sin clases innecesarias.

| Función | Responsabilidad |
|---|---|
| `cruzar_proveedor(compras_path, parquet_root, rfc=None)` | **Orquestador.** Lee Compras, resuelve RFC, carga CPA filtrado y cruza. Lo que llaman GUI y CLI |
| `leer_compras(ruta)` | Lee la hoja `Compras` localizando la fila de encabezados (`cnpj`) |
| `rfc_de_compras(df)` | RFC del proveedor desde la columna `cnpj` |
| `cargar_cpa(rfc, parquet_root, barcodes=None)` | Trae de DuckDB los conceptos del RFC, deduplicados y filtrados por código de barras |
| `normalizar_factura(v)` | `FN-21226` → `FN21226` |
| `solo_digitos(v)` | `FN-21226` → `21226` |
| `cruzar(compras, cpa)` | Hace el cruce y devuelve `ResultadoCruce` |
| `ResultadoCruce.resumen()` | Métricas legibles de la corrida |

**Por qué DuckDB y no pandas para leer el Parquet:** el dataset son 66M de filas
particionadas por RFC. DuckDB aplica el filtro de partición sin cargar todo a memoria.

### 2.1 Filtrado por código de barras — obligatorio para escala

Un proveedor grande tiene millones de conceptos en CPA Vision (Pepsico ≈ 16M, Sigma ≈ 12M).
Cargar todo eso a pandas **agota la memoria** (`ArrowMemoryError`).

`cargar_cpa` recibe el conjunto de **códigos de barras que aparecen en el Compras** y filtra
en DuckDB con `... IN (SELECT bc FROM codigos)`. Solo llega a memoria lo que puede cruzar —
tras el filtro, los conceptos caben de sobra. `cruzar_proveedor` arma ese conjunto solo.

El código de barras se normaliza igual en ambos lados
(`ltrim(regexp_replace(x,'[^0-9]',''),'0')` en SQL = `solo_digitos()` en Python).

### 2.2 Deduplicación de descargas

Un RFC puede tener varias descargas (`request_id`) con años solapados —típico: una de
2020-2025 y otra de solo 2025 (ver duplicaciones de Pepsico y Nestlé en
[PLANEACION.md](PLANEACION.md)). `cargar_cpa` asigna cada `year` al `request_id` **más
completo** (más años distintos; a igualdad, más filas) y descarta el resto. Así el año
repetido no se cuenta dos veces, sin necesidad de borrar particiones del disco.

## 3. Estrategia de cruce en dos pasadas

`invnbr` en Compras tiene formato inconsistente (ver MAPEO §1.1), así que no se puede
cruzar directo.

```
Pasada 1 (principal)   codbarra + (Serie‖Folio) normalizados
Pasada 2 (respaldo)    codbarra + solo la parte numérica del folio
```

La pasada 2 solo se aplica a los renglones que no cruzaron en la 1. El riesgo de falso
positivo se acota porque el cruce ya va restringido por RFC y código de barras.

### Manejo de ambigüedad
Si una llave apunta a **más de un** concepto del CFDI, se descarta (`keep=False`) en vez
de tomar uno al azar. Se reporta en `descartados_ambiguos`.
**Preferimos no llenar un dato a llenarlo mal.**

### Código de barras
Se normaliza con `solo_digitos()`, lo que además resuelve el problema de la notación
científica (`7.50102E+12`) al no depender del formato de texto.

## 3.5 🔑 Regla de negocio: solo se rellenan celdas VACÍAS

**Definida por Óscar el 2026-07-23.** El cruce **no busca llenar todo** el bloque EDI: solo
**completa las celdas que vienen vacías** en Compras. Si un renglón ya traía datos EDI (los
que el sistema origen sí cruzó), **no se tocan**. Y si al final **muchas quedan sin llenar,
está bien** — es esperable que un porcentaje no tenga CFDI (código de barras que no coincide,
o factura ausente; ver reunión 1, R3).

Implicaciones en el código:
- Cada columna se escribe solo donde `_vacio()` es cierto **y** hay valor cruzado.
- Las derivadas (`ctobto_edi`, `impart_edi`) se calculan solo en celdas vacías con insumo.
- **Nunca se sobrescribe** un dato existente ni se rellena con `0` un renglón sin CFDI.
- La métrica principal ya no es "tasa de cruce" sino **`celdas vacías rellenadas`**.

> **Techo real medido (Nestlé 2024):** el 82.8% de los renglones tienen un CFDI que empata
> por código de barras + factura. El ~17% restante simplemente no tiene match — se deja como
> está, por diseño.

## 4. Qué se escribe

| Columna | Origen |
|---|---|
| `canfac_edi`, `ctonto_edi`, `prieps_edi`, `imieps_edi`, `poriva_edi`, `impiva_edi`, `totfactura`, `uuid` | Copiadas del CFDI |
| `factem_edi` | Copiada de `fact_empaq` (ya está en Compras) |
| `ctobto_edi` | `ctonto_edi × factem_edi` |
| `impart_edi` | `ctobto_edi × canfac_edi × (1 + poriva_edi)` |

**Nada fuera de este bloque se modifica** (regla de alcance, MAPEO §0).

## 5. Doble validación permanente

Además de copiar el importe del CFDI, se calcula la fórmula sobre `totfactura` y se
guarda en columnas de control:

```
impiva_edi_formula  = totfactura ÷ (1 + poriva_edi) × poriva_edi
imieps_edi_formula  = totfactura ÷ (1 + prieps_edi) × prieps_edi
```

`ResultadoCruce` reporta cuántos renglones difieren en más de $0.01.

> **El valor bueno es el copiado del CFDI.** La fórmula queda como testigo, porque medida
> sobre 66M de filas solo acierta en el 0.9% de los renglones (MAPEO §4.0.2.1). Sirve para
> detectar proveedores que se comporten distinto y como evidencia para Luis y Mónica.

## 6. Métricas que devuelve

```
Renglones de Compras      : 400
Cruzados                  : 394 (98.5%)
  - por serie + folio     : 394
  - por folio (respaldo)  : 0
Sin cruce                 : 6
CFDI ambiguos descartados : 0
Doble validacion (copiado vs. formula sobre totfactura):
  - difieren en IVA       : 0
  - difieren en IEPS      : 0
```

> ⚠️ **Siempre revisar la tasa de cruce antes de dar el resultado por bueno.** Un cruce que
> corre sin errores pero cruza el 40% produce un archivo que parece correcto y no lo es.

## 7. Pruebas

[`test_cruce_cpa.py`](../test_cruce_cpa.py) usa `invnbr` y `codbarra` **reales** del archivo
de Alceda y arma el lado de CPA Vision imitando su estructura (`Serie` y `Folio` separados).

```bash
python test_cruce_cpa.py
```

Valida: tasa de cruce contra formatos reales · `factem_edi = fact_empaq` ·
`ctobto_edi` · `impart_edi`.

**Resultado 2026-07-22:** 98.5% de cruce sobre 400 renglones; los 6 sin cruce son renglones
sin `invnbr` o sin `codbarra`. Las tres validaciones de cálculo pasan.

## 8. Bug encontrado durante la implementación

La primera versión leía `factem_edi` de Compras asumiendo que ya venía lleno.
**Medido en el archivo de Alceda: `fact_empaq` está lleno al 100% (400/400) pero
`factem_edi` solo al 24% (98/400).** `factem_edi` es una columna del bloque EDI que hay
que **llenar** desde `fact_empaq`, no leer.

Sin la corrección, `ctobto_edi` e `impart_edi` habrían salido en `0` para el 76% de los
renglones.

## 9. Pendiente antes de producción

- [ ] **Validar contra un proveedor real que exista en ambos lados.** Hoy ninguno de los 43
      RFC descargados coincide con los archivos de Compras disponibles
      (Alceda `ALC0011111Y9` y Degasa `DEG9807015H8` no están en el Parquet).
      La prueba actual valida la mecánica, **no el cruce real**.
- [ ] Revisar la tasa de cruce real y decidir si la pasada de respaldo aporta o mete ruido.
- [ ] Definir si el Excel de salida debe conservar el formato de la plantilla
      (hoy se escribe plano con `to_excel`).
