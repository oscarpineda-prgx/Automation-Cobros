import duckdb
import pandas as pd

# Ruta raíz donde quedaron los parquet
PARQUET_ROOT = r"X:\Soriana\00 - AUDITORIA 2020 - 2024\00 - Auditores\Oscar\Proyectos Python\Automation-Cobros\outputs\cpa_vision\parquet"

# Crear conexión
con = duckdb.connect()

print("=" * 80)
print("1. TOTAL DE REGISTROS")
print("=" * 80)

total = con.execute(f"""
SELECT COUNT(*) total_registros
FROM read_parquet('{PARQUET_ROOT}/**/*.parquet', hive_partitioning=true)
""").fetchone()[0]

print(f"Total registros: {total:,}")


print("\n" + "=" * 80)
print("2. ESTRUCTURA DE COLUMNAS")
print("=" * 80)

df = con.execute(f"""
SELECT *
FROM read_parquet('{PARQUET_ROOT}/**/*.parquet', hive_partitioning=true)
LIMIT 1
""").fetchdf()

for col in df.columns:
    print(col)


print("\n" + "=" * 80)
print("3. RFCS ENCONTRADOS")
print("=" * 80)

df_rfc = con.execute(f"""
SELECT
    rfc_proveedor,
    COUNT(*) registros
FROM read_parquet('{PARQUET_ROOT}/**/*.parquet', hive_partitioning=true)
GROUP BY rfc_proveedor
ORDER BY registros DESC
""").fetchdf()

print(df_rfc)


print("\n" + "=" * 80)
print("4. ARCHIVOS PROCESADOS")
print("=" * 80)

df_archivos = con.execute(f"""
SELECT
    archivo_csv,
    COUNT(*) registros
FROM read_parquet('{PARQUET_ROOT}/**/*.parquet', hive_partitioning=true)
GROUP BY archivo_csv
ORDER BY registros DESC
LIMIT 20
""").fetchdf()

print(df_archivos)


print("\n" + "=" * 80)
print("5. REQUEST ID")
print("=" * 80)

df_request = con.execute(f"""
SELECT
    request_id,
    COUNT(*) registros
FROM read_parquet('{PARQUET_ROOT}/**/*.parquet', hive_partitioning=true)
GROUP BY request_id
ORDER BY registros DESC
""").fetchdf()

print(df_request)


print("\n" + "=" * 80)
print("6. AÑOS")
print("=" * 80)

df_year = con.execute(f"""
SELECT
    year,
    COUNT(*) registros
FROM read_parquet('{PARQUET_ROOT}/**/*.parquet', hive_partitioning=true)
GROUP BY year
ORDER BY year
""").fetchdf()

print(df_year)


print("\n" + "=" * 80)
print("7. PRIMEROS 20 REGISTROS")
print("=" * 80)

df_top = con.execute(f"""
SELECT *
FROM read_parquet('{PARQUET_ROOT}/**/*.parquet', hive_partitioning=true)
LIMIT 20
""").fetchdf()

print(df_top)


print("\n" + "=" * 80)
print("8. GUARDAR MUESTRA A EXCEL")
print("=" * 80)

df_top.to_excel("muestra_duckdb.xlsx", index=False)

print("Archivo generado: muestra_duckdb.xlsx")