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


def analyze_query(
    connection_type: str,
    connection_config: dict,
    query: str,
) -> dict:
    """Analyze a SQL query and return metadata for policy evaluation.

    Returns table names, per-table row counts (from catalog metadata),
    and basic query pattern detection — without executing the query.
    """
    import re

    source_tables = _extract_table_names(query)
    has_where = _has_clause(query, "WHERE")
    has_limit = _has_clause(query, "LIMIT")

    if connection_type == "sqlite":
        table_counts = _get_sqlite_table_counts(connection_config, source_tables)
    elif connection_type == "postgresql":
        table_counts = _get_postgresql_table_counts(connection_config, source_tables)
    else:
        table_counts = {}

    max_rows = max(table_counts.values()) if table_counts else None

    return {
        "source_tables": source_tables,
        "table_row_counts": table_counts,
        "max_source_table_rows": max_rows,
        "has_where_clause": has_where,
        "has_limit_clause": has_limit,
    }


def _extract_table_names(query: str) -> list[str]:
    """Extract table names from FROM and JOIN clauses using simple regex."""
    import re

    # Strip comments
    cleaned = re.sub(r"--.*$", "", query, flags=re.MULTILINE)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

    sql_keywords = {
        "select", "where", "group", "order", "having", "limit", "union",
        "values", "set", "into", "lateral", "each", "as", "on", "and", "or",
        "not", "null", "true", "false", "case", "when", "then", "else", "end",
    }
    tables: set[str] = set()
    for match in re.finditer(
        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", cleaned, re.IGNORECASE,
    ):
        name = match.group(1).lower()
        if name not in sql_keywords:
            tables.add(name)

    return sorted(tables)


def _has_clause(query: str, keyword: str) -> bool:
    import re

    cleaned = re.sub(r"--.*$", "", query, flags=re.MULTILINE)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    return bool(re.search(rf"\b{keyword}\b", cleaned, re.IGNORECASE))


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


def _get_sqlite_table_counts(config: dict, tables: list[str]) -> dict[str, int]:
    """Get row counts for individual base tables from SQLite (fast — no full scan)."""
    import re

    db_path = config.get("path")
    if not db_path or not tables:
        return {}

    conn = sqlite3.connect(db_path)
    counts: dict[str, int] = {}
    try:
        for table in tables:
            # Validate table name is safe (alphanumeric + underscore only)
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
                continue
            try:
                cursor = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
                row = cursor.fetchone()
                counts[table] = int(row[0]) if row else 0
            except sqlite3.OperationalError:
                pass  # table doesn't exist
    finally:
        conn.close()

    return counts


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


def _get_postgresql_table_counts(config: dict, tables: list[str]) -> dict[str, int]:
    """Get approximate row counts from PostgreSQL catalog statistics (free)."""
    import psycopg2

    if not tables:
        return {}

    conn = psycopg2.connect(
        host=config.get("host", "localhost"),
        port=config.get("port", 5432),
        dbname=config.get("database"),
        user=config.get("user"),
        password=config.get("password"),
        options=config.get("options", ""),
    )
    counts: dict[str, int] = {}
    try:
        cursor = conn.cursor()
        # pg_stat_user_tables gives approximate live-row counts — essentially free
        placeholders = ",".join(["%s"] * len(tables))
        cursor.execute(
            f"SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE relname IN ({placeholders})",
            tables,
        )
        for relname, n_live_tup in cursor.fetchall():
            counts[relname] = int(n_live_tup)
    finally:
        conn.close()

    return counts


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
