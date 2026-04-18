to check the sessions:
```sql
-- All messages for a session
SELECT messages FROM sessions WHERE id = 'test-1';

-- Pretty-printed, one message per row
SELECT jsonb_array_elements(messages) AS message
FROM sessions WHERE id = 'test-1';

-- Just the role and a preview of each message
SELECT
  msg->>'role' AS role,
  LEFT(msg->>'content', 120) AS content_preview
FROM sessions,
     jsonb_array_elements(messages) AS msg
WHERE id = 'test-1';

-- Count messages per session
SELECT id, jsonb_array_length(messages) AS msg_count
FROM sessions ORDER BY updated_at DESC;
```