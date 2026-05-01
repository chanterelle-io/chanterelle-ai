import logging
import io

from fastapi import FastAPI, HTTPException, Query, Request, Response
import pyarrow.parquet as pq

from shared.contracts.artifact import (
    ArtifactEvictionCandidate,
    ArtifactEvictionReason,
    ArtifactEvictionResult,
    ArtifactPreview,
    ArtifactQuotaSummary,
    ArtifactRecord,
    CreateArtifactRequest,
)
from services.artifact.catalog import ArtifactCatalog
from services.artifact.store import ArtifactStore
from shared.settings import settings

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


@app.get("/artifacts/eviction-candidates", response_model=list[ArtifactEvictionCandidate])
def list_eviction_candidates(
    session_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[ArtifactEvictionCandidate]:
    return catalog.list_eviction_candidates(session_id=session_id, limit=limit)


@app.get("/artifacts/quota", response_model=ArtifactQuotaSummary)
def get_artifact_quota(session_id: str = Query(...)) -> ArtifactQuotaSummary:
    return catalog.get_quota_summary(session_id, settings.artifact_session_quota_bytes)


@app.post("/artifacts/evict", response_model=ArtifactEvictionResult)
def evict_artifacts(session_id: str = Query(...)) -> ArtifactEvictionResult:
    return _evict_to_quota(session_id)


@app.post("/artifacts/session-cleanup", response_model=ArtifactEvictionResult)
def cleanup_session_artifacts(session_id: str = Query(...)) -> ArtifactEvictionResult:
    return _evict_for_session_cleanup(session_id)


@app.post("/artifacts/{artifact_id}/pin", response_model=ArtifactRecord)
def pin_artifact(artifact_id: str) -> ArtifactRecord:
    record = catalog.set_pinned(artifact_id, is_pinned=True)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return record


@app.post("/artifacts/{artifact_id}/unpin", response_model=ArtifactRecord)
def unpin_artifact(artifact_id: str) -> ArtifactRecord:
    record = catalog.set_pinned(artifact_id, is_pinned=False)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
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
    preview = _build_preview(data)

    catalog.update_storage(
        artifact_id,
        storage_uri=uri,
        size_bytes=size_bytes,
        preview=preview,
    )
    eviction_result = _evict_to_quota(record.session_id)
    logger.info("Uploaded %d bytes for artifact %s", size_bytes, artifact_id)
    return {
        "storage_uri": uri,
        "size_bytes": size_bytes,
        "evicted_artifact_ids": [item.artifact_id for item in eviction_result.evicted_artifacts],
    }


@app.get("/artifacts/{artifact_id}", response_model=ArtifactRecord)
def get_artifact(artifact_id: str) -> ArtifactRecord:
    record = catalog.get(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    catalog.touch_access(artifact_id)
    updated_record = catalog.get(artifact_id)
    return updated_record or record


@app.get("/artifacts/{artifact_id}/download")
def download_artifact_data(artifact_id: str) -> Response:
    record = catalog.get(artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if record.storage_uri is None:
        raise HTTPException(status_code=404, detail="Artifact has no stored data")

    key = record.storage_uri.replace(f"s3://{store.bucket}/", "")
    data = store.download(key)
    catalog.touch_access(artifact_id)
    return Response(content=data, media_type="application/octet-stream")


@app.get("/artifacts", response_model=list[ArtifactRecord])
def list_artifacts(
    session_id: str = Query(...),
    include_evicted: bool = Query(default=False),
) -> list[ArtifactRecord]:
    return catalog.list_by_session(session_id, include_evicted=include_evicted)


def _build_preview(data: bytes, row_limit: int = 5) -> ArtifactPreview | None:
    try:
        table = pq.read_table(io.BytesIO(data))
        sample_rows = table.slice(0, row_limit).to_pylist()
    except Exception as exc:
        logger.warning("Failed to generate preview rows: %s", exc)
        return None

    return ArtifactPreview(sample_rows=sample_rows, row_limit=row_limit)


def _evict_to_quota(session_id: str) -> ArtifactEvictionResult:
    quota_bytes = settings.artifact_session_quota_bytes
    quota_summary = catalog.get_quota_summary(session_id, quota_bytes)
    used_bytes_before = quota_summary.used_bytes
    evicted_artifacts = []
    candidates = catalog.list_eviction_candidates(session_id=session_id, limit=500)

    if not candidates:
        preserved_artifacts = catalog.list_session_preserved_artifacts(
            session_id,
            evicted_artifact_ids=set(),
        )
        return ArtifactEvictionResult(
            session_id=session_id,
            quota_bytes=quota_bytes,
            used_bytes_before=used_bytes_before,
            used_bytes_after=used_bytes_before,
            reclaimed_bytes=0,
            evicted_artifacts=[],
            preserved_artifacts=preserved_artifacts,
        )

    for candidate in candidates:
        current_quota = catalog.get_quota_summary(session_id, quota_bytes)
        if (
            candidate.reason == ArtifactEvictionReason.QUOTA_PRESSURE
            and not current_quota.over_quota
        ):
            break

        record = catalog.get(candidate.artifact_id)
        if record is None or not record.storage_uri:
            continue

        key = record.storage_uri.replace(f"s3://{store.bucket}/", "")
        store.delete(key)
        evicted = catalog.mark_evicted(candidate.artifact_id, reason=candidate.reason)
        if evicted is not None:
            evicted_artifacts.append(evicted)

    preserved_artifacts = catalog.list_session_preserved_artifacts(
        session_id,
        evicted_artifact_ids={artifact.artifact_id for artifact in evicted_artifacts},
    )

    return catalog.build_eviction_result(
        session_id=session_id,
        quota_bytes=quota_bytes,
        used_bytes_before=used_bytes_before,
        evicted_artifacts=evicted_artifacts,
        preserved_artifacts=preserved_artifacts,
    )


def _evict_for_session_cleanup(session_id: str) -> ArtifactEvictionResult:
    quota_bytes = settings.artifact_session_quota_bytes
    quota_summary = catalog.get_quota_summary(session_id, quota_bytes)
    used_bytes_before = quota_summary.used_bytes
    evicted_artifacts = []
    candidates = catalog.list_session_cleanup_candidates(session_id)

    for candidate in candidates:
        if not candidate.storage_uri:
            continue

        key = candidate.storage_uri.replace(f"s3://{store.bucket}/", "")
        store.delete(key)
        evicted = catalog.mark_evicted(
            candidate.id,
            reason=ArtifactEvictionReason.SESSION_EXPIRED,
        )
        if evicted is not None:
            evicted_artifacts.append(evicted)

    preserved_artifacts = catalog.list_session_preserved_artifacts(
        session_id,
        evicted_artifact_ids={artifact.artifact_id for artifact in evicted_artifacts},
    )

    return catalog.build_eviction_result(
        session_id=session_id,
        quota_bytes=quota_bytes,
        used_bytes_before=used_bytes_before,
        evicted_artifacts=evicted_artifacts,
        preserved_artifacts=preserved_artifacts,
    )
