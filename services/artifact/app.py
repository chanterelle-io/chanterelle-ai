import logging

from fastapi import FastAPI, HTTPException, Query, Request, Response

from shared.contracts.artifact import ArtifactRecord, CreateArtifactRequest
from services.artifact.catalog import ArtifactCatalog
from services.artifact.store import ArtifactStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Artifact Service", version="0.1.0")

catalog = ArtifactCatalog()
store = ArtifactStore()


@app.post("/artifacts", response_model=ArtifactRecord)
def create_artifact(req: CreateArtifactRequest) -> ArtifactRecord:
    record = catalog.create(req)
    logger.info("Created artifact %s (%s) for session %s", record.id, record.name, record.session_id)
    return record


@app.put("/artifacts/{artifact_id}/upload")
async def upload_artifact_data(artifact_id: str, request: Request) -> dict:
    record = catalog.get(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    data = await request.body()
    key = f"{record.session_id}/{artifact_id}.parquet"
    uri = store.upload(key, data)
    size_bytes = len(data)

    catalog.update_storage(artifact_id, storage_uri=uri, size_bytes=size_bytes)
    logger.info("Uploaded %d bytes for artifact %s", size_bytes, artifact_id)
    return {"storage_uri": uri, "size_bytes": size_bytes}


@app.get("/artifacts/{artifact_id}", response_model=ArtifactRecord)
def get_artifact(artifact_id: str) -> ArtifactRecord:
    record = catalog.get(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return record


@app.get("/artifacts/{artifact_id}/download")
def download_artifact_data(artifact_id: str) -> Response:
    record = catalog.get(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if record.storage_uri is None:
        raise HTTPException(status_code=404, detail="Artifact has no stored data")

    key = record.storage_uri.replace(f"s3://{store.bucket}/", "")
    data = store.download(key)
    return Response(content=data, media_type="application/octet-stream")


@app.get("/artifacts", response_model=list[ArtifactRecord])
def list_artifacts(session_id: str = Query(...)) -> list[ArtifactRecord]:
    return catalog.list_by_session(session_id)
