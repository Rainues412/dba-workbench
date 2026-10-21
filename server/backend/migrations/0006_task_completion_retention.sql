-- Undated historical completions receive a full retention period on upgrade.
-- Preserve bodies, statuses, creation times and valid completion timestamps.
UPDATE tasks
SET completed_at = CURRENT_TIMESTAMP, revision = revision + 1
WHERE status = '已完成'
  AND (completed_at IS NULL OR julianday(completed_at) IS NULL);
