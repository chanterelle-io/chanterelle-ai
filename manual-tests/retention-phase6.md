# Phase 6 Retention Manual Test

This test verifies the current retention foundation: quota tracking, pin/unpin flows, eviction candidates, and quota-driven eviction.

## Setup

1. Start infrastructure with `make infra`.
2. Run the retention migration with `make migrate-phase6`.
3. If you are using previously seeded topic profiles, `make migrate-phase6` now backfills `pin_artifact` and `unpin_artifact` into the seeded Phase 4 profiles. Rerun `make seed` only if you want to refresh all sample data as well.
4. Start at least the artifact service with `make artifact`.
5. If you want to exercise the full chat flow, also start `make execution`, `make runtime-sql`, `make runtime-python`, and `make agent`.

## Direct Artifact Service Flow

1. Create an artifact record:

```bash
curl -s http://localhost:8002/artifacts \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "retention-test",
    "name": "retention_probe",
    "retention_class": "temporary"
  }' | python -m json.tool
```

2. Upload Parquet bytes for that artifact.
Use any existing Parquet file or generate a small one locally, then upload it:

```bash
curl -s -X PUT http://localhost:8002/artifacts/<artifact_id>/upload \
  --data-binary @/path/to/file.parquet
```

3. Check quota status for the session:

```bash
curl -s "http://localhost:8002/artifacts/quota?session_id=retention-test" | python -m json.tool
```

4. Check eviction candidates:

```bash
curl -s "http://localhost:8002/artifacts/eviction-candidates?session_id=retention-test" | python -m json.tool
```

5. Pin the artifact:

```bash
curl -s -X POST http://localhost:8002/artifacts/<artifact_id>/pin | python -m json.tool
```

Expected:
- `is_pinned` is `true`
- `expires_at` is `null`

6. Unpin the artifact:

```bash
curl -s -X POST http://localhost:8002/artifacts/<artifact_id>/unpin | python -m json.tool
```

Expected:
- `is_pinned` is `false`
- `expires_at` is set again according to the retention TTL

7. Trigger eviction manually for the session:

```bash
curl -s -X POST "http://localhost:8002/artifacts/evict?session_id=retention-test" | python -m json.tool
```

Expected:
- If the session is under quota, `evicted_artifacts` is empty
- If the session is over quota and eligible artifacts exist, the response lists evicted artifacts and reclaimed bytes

## Agent Flow

1. Use `/chat` to create an artifact through a normal SQL or Python tool path.
2. Confirm the agent's normal success message includes preview rows without requiring `inspect_artifact`.
3. Ask the agent to pin it, for example: `Pin the revenue_by_product artifact.`
3. Ask the agent to unpin it.
4. Confirm the artifact metadata through the artifact service or by listing session artifacts.

## Session Lifecycle Flow

1. Fetch a live session summary:

```bash
curl -s http://localhost:8000/sessions/<session_id> | python -m json.tool
```

Expected:
- `last_accessed_at` and `expires_at` are populated

2. Force cleanup of expired sessions:

```bash
curl -s -X POST "http://localhost:8000/sessions/cleanup?limit=100" | python -m json.tool
```

Expected:
- `deleted_session_ids` lists any expired sessions removed during the cleanup pass
- unpinned, non-persistent artifacts for those sessions are evicted first with reason `session_expired`
- pinned or persistent artifacts are preserved

3. Reuse an expired `session_id` through `/chat`.

Expected:
- the agent starts a fresh session state for that id instead of loading the expired conversation history

## Notes

- Quota is currently session-scoped through `CHANTERELLE_ARTIFACT_SESSION_QUOTA_BYTES`.
- Automatic eviction currently runs on artifact upload and can also be triggered manually through `POST /artifacts/evict`.
- Evicted artifacts are hidden from normal session artifact listing unless `include_evicted=true` is passed.