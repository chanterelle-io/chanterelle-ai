from __future__ import annotations

import io
import sqlite3
import logging

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# Map common SQLite type affinity strings to Arrow-friendly logical type names.
_SQLITE_TYPE_MAP = {
    "INTEGER": "int64",
    "REAL": "float64",
    "TEXT": "string",
    "BLOB": "binary",
    "NUMERIC": "string",
    "DATE": "string",
    "DATETIME": "string",
    "BOOLEAN": "bool",
}


def execute_sql(
    connection_type: str,
    connection_config: dict,
    query: str,
) -> tuple[bytes, int, list[str]]:
    """Execute a SQL query and return (parquet_bytes, row_count, column_names)."""

    if connection_type == "sqlite":
        return _execute_sqlite(connection_config, query)
    elif connection_type == "postgresql":
        return _execute_postgresql(connection_config, query)
    else:
        raise ValueError(f"Unsupported connection type: {connection_type}")


def _execute_sqlite(config: dict, query: str) -> tuple[bytes, int, list[str]]:
    db_path = config.get("path")
    if not db_path:
        raise ValueError("SQLite connection requires 'path' in config")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(query)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()

    table = _rows_to_arrow(columns, rows)
    parquet_bytes = _arrow_to_parquet(table)
    return parquet_bytes, len(rows), columns


def _execute_postgresql(config: dict, query: str) -> tuple[bytes, int, list[str]]:
    import psycopg2

    conn = psycopg2.connect(
        host=config.get("host", "localhost"),
        port=config.get("port", 5432),
        dbname=config.get("database"),
        user=config.get("user"),
        password=config.get("password"),
        options=config.get("options", ""),
    )
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()

    table = _rows_to_arrow(columns, rows)
    parquet_bytes = _arrow_to_parquet(table)
    return parquet_bytes, len(rows), columns


def _rows_to_arrow(columns: list[str], rows: list[tuple]) -> pa.Table:
    if not rows:
        arrays = [pa.array([], type=pa.string()) for _ in columns]
    else:
        arrays = []
        for col_idx in range(len(columns)):
            values = [row[col_idx] for row in rows]
            arrays.append(pa.array(values))
    return pa.table(dict(zip(columns, arrays)))


def _arrow_to_parquet(table: pa.Table) -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    return buf.getvalue()
