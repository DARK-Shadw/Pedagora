-- Atomic log append function for agent_tasks.
-- Eliminates read-modify-write race condition when multiple
-- concurrent tasks update logs simultaneously.

CREATE OR REPLACE FUNCTION append_agent_task_log(
    p_goal_id UUID,
    p_agent_type agent_type,
    p_log_entry JSONB
) RETURNS VOID AS $$
BEGIN
    UPDATE agent_tasks
    SET logs = logs || jsonb_build_array(p_log_entry),
        updated_at = NOW()
    WHERE goal_id = p_goal_id AND agent_type = p_agent_type::agent_type;
END;
$$ LANGUAGE plpgsql;
