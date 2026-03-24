"""Async-safe progress tracker for parallel topic extraction.

Ensures progress increases monotonically regardless of which topic
completes first, and uses atomic DB updates.
"""

import asyncio
import logging

from app.services.agent_task import update_agent_task

logger = logging.getLogger(__name__)


class ParallelProgressTracker:
    """Track progress across parallel topic extractions."""

    def __init__(
        self,
        total: int,
        range_start: float,
        range_end: float,
        goal_id: str,
        agent_type: str,
    ) -> None:
        self._total = total
        self._range_start = range_start
        self._range_end = range_end
        self._goal_id = goal_id
        self._agent_type = agent_type
        self._completed = 0
        self._lock = asyncio.Lock()

    async def report_start(self, topic_name: str, index: int) -> None:
        """Log topic extraction start (no progress change)."""
        logger.info(f"Starting extraction [{index + 1}/{self._total}]: {topic_name}")

    async def mark_completed(
        self, topic_name: str, success: bool, detail: str = ""
    ) -> None:
        """Increment completed count and update DB progress."""
        async with self._lock:
            self._completed += 1
            completed = self._completed

        # Calculate monotonically increasing progress
        progress = self._range_start + (
            (self._range_end - self._range_start) * completed / self._total
        )

        level = "success" if success else "error"
        message = (
            f"[{completed}/{self._total}] {topic_name}: {detail}"
            if detail
            else f"[{completed}/{self._total}] {topic_name} {'done' if success else 'failed'}"
        )

        await update_agent_task(
            self._goal_id,
            self._agent_type,
            progress=round(progress, 1),
            log_message=message,
            log_level=level,
        )
