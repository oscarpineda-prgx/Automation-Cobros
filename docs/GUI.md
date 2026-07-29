# Interfaz gráfica — PRGX Soriana Audit Suite

> **Última actualización:** 2026-07-22
> **Archivos:** [`automation_cobros/ui.py`](../automation_cobros/ui.py) (presentación) ·
> [`automation_cobros/app.py`](../automation_cobros/app.py) (aplicación)

---

## 1. Qué cambió y por qué

La GUI original era Tkinter plano y **no tenía nada de CPA Vision**: solo los tres botones
de la Etapa 1. Se rehízo con dos objetivos:

1. **Integrar el cruce de CPA Vision**, que hasta ahora solo existía por terminal.
2. **Alinear el aspecto visual con `Conciliacion_Memo_Panoptic`**, para que las herramientas
   de la suite se vean como una sola familia.

## 2. Separación de responsabilidades

| Archivo | Contiene |
|---|---|
| `ui.py` | Paletas, `Tema`, `Indicadores` y fábricas de widgets. **Cero lógica de negocio.** |
| `app.py` | La aplicación: composición de pantalla y llamadas a los módulos del paquete. |

`ui.py` no importa nada del dominio, así que puede reutilizarse en otra herramienta de la
suite sin arrastrar dependencias.

## 3. Lenguaje visual (heredado de Panoptic)

- **Paleta PRGX** en dos modos, claro y oscuro, con el mismo juego de claves
  (`bg1`, `card`, `accent`, `t1`, `s_ok`…). El acento morado `#611EEC` es la firma PRGX.
- **Franja de acento** de 3 px arriba del encabezado y de cada tarjeta.
- **Encabezado**: icono PRGX · título + `PRGX · Soriana Audit Suite` · logo Soriana ·
  botón de tema.
- **Tarjetas** con esquinas redondeadas, borde de 1 px e insignia numerada (`01`, `02`).
- **Botones con indicador**: punto de estado + barra de progreso indeterminada.
  El punto parpadea mientras corre y queda verde o rojo al terminar.
- **Bitácora** con timestamp en gris y el mensaje coloreado según sea info, ok o error.

### Assets
`automation_cobros/assets/` — `prgx-icon.png`, `prgx-icon.ico`, `Soriana-Logo.png`
(copiados de Panoptic para mantener la identidad).

## 4. Estructura de la pantalla

```
┌──────────────────────────────────────────────────────────┐
│ [PRGX] Automation Cobros            [Soriana]  [🌙 Tema] │  encabezado
├──────────────────────────────────────────────────────────┤
│ Proveedor · Desde · Hasta · Salida            [Elegir]   │  barra de configuración
├───────────────────────────┬──────────────────────────────┤
│ 01  ETAPA 1               │ 02  ETAPA 2                  │
│ Pipeline de Compras       │ CPA Vision                   │
│ ▶ Generar Compras         │ ▶ Rellenar EDI               │
│ ⟳ Recalcular              │ RFC · Parquet                │
│ ✦ Generar Validación      │                              │
│ ⚡ Probar conexión         │                              │
├───────────────────────────┴──────────────────────────────┤
│ BITÁCORA DE EJECUCIÓN                       [Limpiar]    │
└──────────────────────────────────────────────────────────┘
```

## 5. Etapa 2 — el cruce de CPA Vision

Es la funcionalidad nueva. El botón **"Rellenar EDI desde CPA Vision"**:

1. Toma el **RFC** y la **carpeta del dataset Parquet** de los campos de la tarjeta.
2. Usa como entrada el **"Compras editado"** de la Etapa 1 (pide el archivo si está vacío).
3. Llama a `cruce_cpa.cruzar()` y **vuelca las métricas completas en la bitácora**
   (tasa de cruce, desglose por estrategia, discrepancias de la doble validación).
4. Escribe `<nombre>_EDI.xlsx` y **lo deja seleccionado como "Compras editado"**, de modo
   que el siguiente paso natural sea recalcular.

Si el RFC no tiene datos en el Parquet, lo dice explícitamente en vez de generar un archivo
vacío.

> Detalle del cruce en [CRUCE_IMPLEMENTACION.md](CRUCE_IMPLEMENTACION.md).

## 6. Concurrencia

`_ejecutar()` centraliza el patrón: marca el indicador en `running`, corre la tarea en un
hilo daemon y deja el indicador en `ok` o `error`. La bandera `_ocupado` impide lanzar dos
operaciones a la vez.

Los widgets **solo se tocan desde el hilo de Tk**: los hilos de trabajo publican en una
`queue` que se drena con `after(120ms)`, e `Indicadores.estado()` reencola con `after(0)`.

## 7. Cambio de tema

Reconstruye la pantalla: guarda el texto de la bitácora, destruye los hijos, cambia la
paleta, vuelve a construir y restaura el texto. Los `StringVar` sobreviven porque son del
objeto, no de los widgets. Es la misma estrategia de Panoptic.

## 8. Ejecutable y .zip

```bash
python scripts/build_release.py                 # compila y empaqueta
python scripts/build_release.py --sin-compilar  # solo re-empaqueta dist/
```

Produce `dist/Automation Cobros.exe` y `dist/AutomationCobros_<version>_<fecha>.zip`.

El `.spec` se actualizó para incluir lo que PyInstaller no detecta solo:

- `collect_submodules("automation_cobros")` — los subcomandos de `main.py` importan dentro
  de funciones y el análisis estático no los ve.
- `collect_data_files("customtkinter")` — customtkinter carga sus temas JSON en runtime.
- La carpeta `assets` y `templates`.
- Icono `prgx-icon.ico`.

## 9. Pendiente

- [ ] **Compilar y probar el `.exe` en una máquina limpia.** El script está escrito pero
      no se ha ejecutado un build completo.
- [ ] Valorar un botón de "Detener" como el de Panoptic (hoy no hay cancelación).
