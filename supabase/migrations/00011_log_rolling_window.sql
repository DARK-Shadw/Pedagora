-- Migration 00011: Rolling window cap on agent_tasks.logs
--
-- Rewrites append_agent_task_log so each task row never holds more than
-- MAX_LOG_ENTRIES entries. Older entries are evicted from the front when the
-- cap is reached, keeping the most recent 25 in chronological order.
--
-- Also includes a one-time backfill that trims any existing oversized rows.

CREATE OR REPLACE FUNCTION append_agent_task_log(
    p_goal_id    UUID,
    p_agent_type agent_type,
    p_log_entry  JSONB
) RETURNS VOID AS $$
DECLARE
  v_max CONSTANT INT := 25;
BEGIN
  UPDATE agent_tasks
  SET logs = CASE
    -- Fast path: still under the cap after appending
    WHEN jsonb_array_length(logs) + 1 <= v_max
      THEN logs || jsonb_build_array(p_log_entry)
    -- Slow path: evict the oldest entry and append the new one.
    -- We take the combined array, sort descending by ordinality (newest last =
    -- highest ord), keep the top v_max, then re-sort ascending so the final
    -- array is chronological oldest→newest.
    ELSE (
      SELECT COALESCE(jsonb_agg(elem ORDER BY ord ASC), '[]'::jsonb)
      FROM (
        SELECT elem, ord
        FROM jsonb_array_elements(logs || jsonb_build_array(p_log_entry))
             WITH ORDINALITY AS t(elem, ord)
        ORDER BY ord DESC
        LIMIT v_max
      ) recent
    )
  END,
  updated_at = NOW()
  WHERE goal_id    = p_goal_id
    AND agent_type = p_agent_type::agent_type;
END;
$$ LANGUAGE plpgsql;

-- ── One-time backfill ─────────────────────────────────────────────────────────
-- Truncate any existing rows that already exceed the new cap so the UI never
-- shows a stale wall of old log entries on first load.

UPDATE agent_tasks
SET logs = (
  SELECT COALESCE(jsonb_agg(elem ORDER BY ord ASC), '[]'::jsonb)
  FROM (
    SELECT elem, ord
    FROM jsonb_array_elements(logs) WITH ORDINALITY AS t(elem, ord)
    ORDER BY ord DESC
    LIMIT 25
  ) recent
)
WHERE jsonb_array_length(logs) > 25;


-- ── One-time goal cleanup (run manually, NOT auto-applied) ───────────────────
-- Copy the block below and run it in the Supabase SQL editor to delete all but
-- the newest learning goal for a given user. Cascade deletes agent_tasks,
-- course_plans, research_results, research_sources, and lesson_animations.
--
--   REPLACE <user_id> with the target user's UUID before running.
--
-- DO $$
-- DECLARE v_user UUID := '<user_id>';
-- BEGIN
--   DELETE FROM learning_goals
--   WHERE user_id = v_user
--     AND id <> (
--       SELECT id FROM learning_goals
--       WHERE user_id = v_user
--       ORDER BY created_at DESC
--       LIMIT 1
--     );
--   RAISE NOTICE 'Deleted % old goal(s).', (SELECT COUNT(*) FROM learning_goals WHERE user_id = v_user) - 1;
-- END $$;
