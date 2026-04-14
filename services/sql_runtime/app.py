import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import Response

from services.sql_runtime.executor import execute_sql

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="SQL Runtime", version="0.1.0")


class SqlExecuteRequest(BaseModel):
    connection_type: str
    connection_config: dict
    query: str


@app.post("/execute")
def run_query(req: SqlExecuteRequest) -> Response:
    logger.info("Executing SQL on %s connection", req.connection_type)
    try:
        parquet_bytes, row_count, columns = execute_sql(
            connection_type=req.connection_type,
            connection_config=req.connection_config,
            query=req.query,
        )
    except Exception as e:
        logger.error("SQL execution failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=parquet_bytes,
        media_type="application/octet-stream",
        headers={
            "X-Row-Count": str(row_count),
            "X-Columns": ",".join(columns),
        },
    )
