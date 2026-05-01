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

## Quota Pressure Flow

This flow validates the live `quota_pressure` path directly. Because the default session quota is 50 MiB, temporarily lower it so the test can use small local files.

1. Restart the artifact service with a smaller quota for the test session:

If another artifact service is already running on port 8002, stop it first so the restarted process picks up the lower quota value.

```bash
CHANTERELLE_ARTIFACT_SESSION_QUOTA_BYTES=200000 make artifact
```

2. Generate two parquet files that are each large enough to matter against that quota:

```bash
python - <<'PY'
import uuid
import pyarrow as pa
import pyarrow.parquet as pq


def write_file(path: str, rows: int) -> None:
    payloads = [uuid.uuid4().hex * 8 for _ in range(rows)]
    table = pa.table({
        "row_id": list(range(rows)),
        "payload": payloads,
    })
    pq.write_table(table, path, compression=None)


write_file("/tmp/quota_a.parquet", 450)
write_file("/tmp/quota_b.parquet", 450)
PY

ls -lh /tmp/quota_a.parquet /tmp/quota_b.parquet
```

Expected:
- each file is typically around or above 100 KiB

3. Create the first artifact record:

```bash
curl -s http://localhost:8002/artifacts \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "quota-pressure-test",
    "name": "quota_probe_a",
    "retention_class": "temporary"
  }' | python -m json.tool
```

4. Upload the first file and confirm the session is still under quota:

```bash
curl -s -X PUT http://localhost:8002/artifacts/<artifact_a_id>/upload \
  --data-binary @/tmp/quota_a.parquet | python -m json.tool

curl -s "http://localhost:8002/artifacts/quota?session_id=quota-pressure-test" | python -m json.tool
```

Expected:
- `over_quota` is `false`
- `used_bytes` is non-zero

5. Create the second artifact record:

```bash
curl -s http://localhost:8002/artifacts \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "quota-pressure-test",
    "name": "quota_probe_b",
    "retention_class": "temporary"
  }' | python -m json.tool
```

6. Upload the second file. This upload should push the session over quota and trigger automatic eviction:

```bash
curl -s -X PUT http://localhost:8002/artifacts/<artifact_b_id>/upload \
  --data-binary @/tmp/quota_b.parquet | python -m json.tool
```

Expected:
- `evicted_artifact_ids` contains one eligible artifact id once the quota is exceeded
- if no eligible artifact can be evicted, `evicted_artifact_ids` can remain empty even while the session stays over quota

7. Inspect both artifacts and the full session list, including evicted artifacts:

```bash
curl -s http://localhost:8002/artifacts/<artifact_a_id> | python -m json.tool
curl -s http://localhost:8002/artifacts/<artifact_b_id> | python -m json.tool
curl -s "http://localhost:8002/artifacts?session_id=quota-pressure-test&include_evicted=true" | python -m json.tool
```

Expected:
- one artifact remains `ready`
- one eligible artifact is now `evicted`
- the evicted artifact has `storage_uri` set to `null`
- the evicted artifact includes `extra_metadata.eviction.reason` set to `quota_pressure`

8. Confirm quota returned to a non-over-quota state after eviction:

```bash
curl -s "http://localhost:8002/artifacts/quota?session_id=quota-pressure-test" | python -m json.tool
```

Expected:
- `over_quota` is `false`
- `available_bytes` increased after eviction

9. Optional pinned-artifact variation: pin one artifact before uploading the second file, then verify the unpinned artifact is the one evicted.

10. Optional pinned-only over-quota variation: pin the only stored artifact before upload, then call `POST /artifacts/evict`.

Expected:
- `evicted_artifacts` is empty because there is nothing eligible to evict
- `preserved_artifacts` includes the pinned artifact with reason `pinned`
- `over_quota` can remain `true` after the eviction attempt because the remaining bytes belong only to preserved artifacts

Verified example from a live run on 2026-05-01 with `CHANTERELLE_ARTIFACT_SESSION_QUOTA_BYTES=200000`:

```text
session_id: quota-pressure-test-live
quota_a.parquet: 123387 bytes
quota_b.parquet: 123387 bytes
artifact_a_id: 7131d513-5652-4c19-990b-71fde3cae56b
artifact_b_id: 570d7542-4df5-4d6d-91eb-a39d1641617a

upload_a:
  storage_uri: s3://artifacts/quota-pressure-test-live/7131d513-5652-4c19-990b-71fde3cae56b.parquet
  size_bytes: 123387
  evicted_artifact_ids: []

upload_b:
  storage_uri: s3://artifacts/quota-pressure-test-live/570d7542-4df5-4d6d-91eb-a39d1641617a.parquet
  size_bytes: 123387
  evicted_artifact_ids:
    - 7131d513-5652-4c19-990b-71fde3cae56b

artifact_a_final:
  status: evicted
  storage_uri: null
  size_bytes: 0
  extra_metadata.eviction.reason: quota_pressure
  extra_metadata.eviction.reclaimed_bytes: 123387

artifact_b_final:
  status: ready
  size_bytes: 123387

quota_after_second_upload:
  quota_bytes: 200000
  used_bytes: 123387
  available_bytes: 76613
  over_quota: false
  evictable_bytes: 123387

pinned_only_over_quota_example:
  artifact_id: 11e24974-d7f5-4d4c-b1b2-4a0efad4b161
  file_size: 322703
  quota_before_evict:
    quota_bytes: 200000
    used_bytes: 322703
    available_bytes: 0
    over_quota: true
    evictable_bytes: 0
  evict_result:
    evicted_artifacts: []
    preserved_artifacts:
      - artifact_id: 11e24974-d7f5-4d4c-b1b2-4a0efad4b161
        name: quota_preserved_pinned
        reason: pinned
  quota_after_evict:
    quota_bytes: 200000
    used_bytes: 322703
    available_bytes: 0
    over_quota: true
    evictable_bytes: 0
```

## Agent Flow

1. Use `/chat` to create an artifact through a normal SQL or Python tool path.
2. Confirm the agent's normal success message includes preview rows without requiring `inspect_artifact`.
3. Ask the agent to pin it, for example: `Pin the revenue_by_product artifact.`
4. Ask the agent to unpin it.
5. Confirm the artifact metadata through the artifact service or by listing session artifacts.

## Session Lifecycle Flow

1. Create or reuse a live session, then fetch its summary:

You can create one through `/chat` first if needed:

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-lifecycle-test",
    "message": "Run a SQL query on sample_db: select * from customers limit 3. Save the result as artifact lifecycle_probe."
  }' | python -m json.tool
```

Then inspect the session:

```bash
curl -s http://localhost:8000/sessions/session-lifecycle-test | python -m json.tool
```

Expected:
- `last_accessed_at` and `expires_at` are populated

2. Force the session into the expired state:

```bash
curl -s -X POST http://localhost:8000/sessions/session-lifecycle-test/expire | python -m json.tool
```

Expected:
- the response includes the same `session_id`
- `expires_at` is returned in the past so the next cleanup pass will remove it

3. Run expired-session cleanup:

```bash
curl -s -X POST "http://localhost:8000/sessions/cleanup?limit=100" | python -m json.tool
```

Expected:
- `deleted_session_ids` includes `session-lifecycle-test`
- `deleted_sessions` includes an entry for `session-lifecycle-test` with `tracked_artifact_ids`, `evicted_artifact_ids`, `non_evicted_artifact_ids`, and `preserved_artifacts`
- unpinned, non-persistent artifacts for those sessions are evicted first with reason `session_expired`
- pinned or persistent artifacts are preserved and appear in `preserved_artifacts` with a reason such as `pinned`
- if strict artifact cleanup fails for any expired session, that session appears in `skipped_session_ids` / `skipped_sessions` instead of being deleted blindly

4. Confirm the original session is gone:

```bash
curl -s -i http://localhost:8000/sessions/session-lifecycle-test
```

Expected:
- the endpoint returns `404`

5. Reuse the same `session_id` through `/chat`.

Expected:
- the agent starts a fresh session state for that id instead of loading the expired conversation history

## Notes

- Quota is currently session-scoped through `CHANTERELLE_ARTIFACT_SESSION_QUOTA_BYTES`.
- Automatic eviction currently runs on artifact upload and can also be triggered manually through `POST /artifacts/evict`.
- Evicted artifacts are hidden from normal session artifact listing unless `include_evicted=true` is passed.