from __future__ import annotations

import io
import logging

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


def execute_python_transform(
    code: str,
    input_dataframes: dict[str, pd.DataFrame],
) -> tuple[bytes, int, list[str]]:
    """Execute Python code with input DataFrames and return (parquet_bytes, row_count, column_names).

    The code must assign the final result to a variable called `result`.
    """
    # Build a restricted namespace with pandas and the input DataFrames
    namespace: dict = {"pd": pd, "__builtins__": _safe_builtins()}
    namespace.update(input_dataframes)

    exec(code, namespace)  # noqa: S102

    result = namespace.get("result")
    if result is None:
        raise ValueError("Code must assign the output to a variable called `result`")
    if not isinstance(result, pd.DataFrame):
        raise TypeError(f"Expected `result` to be a DataFrame, got {type(result).__name__}")

    table = pa.Table.from_pandas(result, preserve_index=False)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    parquet_bytes = buf.getvalue()

    return parquet_bytes, len(result), list(result.columns)


def load_parquet_as_dataframe(parquet_bytes: bytes) -> pd.DataFrame:
    buf = io.BytesIO(parquet_bytes)
    table = pq.read_table(buf)
    return table.to_pandas()


def _safe_builtins() -> dict:
    """Return a restricted set of builtins for code execution."""
    import builtins

    allowed = [
        "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
        "frozenset", "getattr", "hasattr", "int", "isinstance", "issubclass",
        "iter", "len", "list", "map", "max", "min", "next", "print", "range",
        "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
        "tuple", "type", "zip", "True", "False", "None",
    ]
    return {name: getattr(builtins, name) for name in allowed if hasattr(builtins, name)}
