import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from services.python_runtime.executor import execute_python_transform, load_parquet_as_dataframe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Python Runtime", version="0.1.0")


class ArtifactInput(BaseModel):
    alias: str
    data: str  # base64-encoded parquet bytes


class PythonExecuteRequest(BaseModel):
    code: str
    inputs: list[ArtifactInput] = []


@app.post("/execute")
def run_transform(req: PythonExecuteRequest) -> Response:
    logger.info("Executing Python transform with %d inputs", len(req.inputs))

    import base64

    # Load input DataFrames
    input_dataframes = {}
    for inp in req.inputs:
        try:
            parquet_bytes = base64.b64decode(inp.data)
            df = load_parquet_as_dataframe(parquet_bytes)
            input_dataframes[inp.alias] = df
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to load input '{inp.alias}': {e}")

    # Execute the transform
    try:
        parquet_bytes, row_count, columns = execute_python_transform(
            code=req.code,
            input_dataframes=input_dataframes,
        )
    except Exception as e:
        logger.error("Python transform failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=parquet_bytes,
        media_type="application/octet-stream",
        headers={
            "X-Row-Count": str(row_count),
            "X-Columns": ",".join(columns),
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}
