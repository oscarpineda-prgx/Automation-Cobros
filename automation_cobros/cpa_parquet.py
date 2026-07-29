from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from zipfile import ZipFile

import pandas as pd

from automation_cobros.utils import ensure_parent, safe_filename

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - reported clearly at runtime.
    pa = None
    pq = None


CHUNK_ROWS = 100_000


@dataclass(slots=True)
class ParquetWriteResult:
    output_root: Path
    files: int
    rows: int
    csv_files: int


def zip_to_parquet_dataset(
    zip_path: Path | str,
    output_root: Path | str,
    *,
    rfc: str,
    request_id: str,
) -> ParquetWriteResult:
    """Store CPA Vision ZIP CSV contents as a partitioned Parquet dataset."""
    if pa is None or pq is None:
        raise RuntimeError("Falta pyarrow. Ejecuta: python -m pip install pyarrow")

    zip_path = Path(zip_path)
    output_root = Path(output_root)
    total_rows = 0
    parquet_files = 0
    csv_files = 0

    with ZipFile(zip_path) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        for csv_name in csv_names:
            csv_files += 1
            year = _extract_year(csv_name)
            parquet_path = _parquet_path(output_root, rfc, year, request_id, csv_name)
            rows = _write_csv_member_to_parquet(
                zf,
                csv_name,
                parquet_path,
                rfc=rfc,
                request_id=request_id,
                zip_name=zip_path.name,
                year=year,
            )
            total_rows += rows
            parquet_files += 1

    return ParquetWriteResult(
        output_root=output_root,
        files=parquet_files,
        rows=total_rows,
        csv_files=csv_files,
    )


def _write_csv_member_to_parquet(
    zf: ZipFile,
    csv_name: str,
    parquet_path: Path,
    *,
    rfc: str,
    request_id: str,
    zip_name: str,
    year: str,
) -> int:
    ensure_parent(parquet_path)
    writer = None
    rows = 0
    try:
        with zf.open(csv_name) as csv_file:
            for chunk in _read_csv_chunks(csv_file):
                chunk.columns = [_clean_column_name(column) for column in chunk.columns]
                chunk.insert(0, "rfc_proveedor", rfc)
                chunk.insert(1, "request_id", request_id)
                chunk.insert(2, "archivo_zip", zip_name)
                chunk.insert(3, "archivo_csv", Path(csv_name).name)
                chunk.insert(4, "anio", year)
                table = pa.Table.from_pandas(chunk, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(str(parquet_path), table.schema, compression="snappy")
                writer.write_table(table)
                rows += len(chunk)
    finally:
        if writer is not None:
            writer.close()
    return rows


def _read_csv_chunks(csv_file):
    for encoding in ("utf-8-sig", "latin1", "cp1252"):
        try:
            yield from pd.read_csv(
                csv_file,
                sep=",",
                encoding=encoding,
                dtype=str,
                keep_default_na=False,
                chunksize=CHUNK_ROWS,
                low_memory=False,
            )
            return
        except UnicodeDecodeError:
            csv_file.seek(0)
    csv_file.seek(0)
    yield from pd.read_csv(
        csv_file,
        sep=",",
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_ROWS,
        low_memory=False,
    )


def _parquet_path(output_root: Path, rfc: str, year: str, request_id: str, csv_name: str) -> Path:
    csv_stem = safe_filename(Path(csv_name).stem) or "archivo_csv"
    return (
        output_root
        / f"rfc={safe_filename(rfc)}"
        / f"year={year or 'sin_anio'}"
        / f"request_id={safe_filename(request_id)}"
        / f"{csv_stem}.parquet"
    )


def _clean_column_name(column: object) -> str:
    return str(column).replace("\ufeff", "").strip()


def _extract_year(filename: str) -> str:
    match = re.search(r"(20\d{2})", filename)
    return match.group(1) if match else ""
