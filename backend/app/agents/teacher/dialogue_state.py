"""Dialogue state tracking for teaching sessions.

Tracks student performance, hints given, misconceptions detected,
and adaptive scaffolding level across the entire session.
"""

from __future__ import annotations

from datetime import datetime, timezone


class DialogueState:
    """Mutable session state that persists across reconnections."""

    def __init__(self):
        self.current_segment_id: str = ""
        self.segments_completed: list[str] = []
        self.student_scores: dict[str, dict] = {}
        # segment_id -> {verdict, attempts, hints_used, question}
        self.dialogue_history: list[dict] = []
        # [{role: "teacher"|"student", content: str, timestamp: str}]
        self.time_per_segment: dict[str, float] = {}
        # segment_id -> seconds spent
        self.reactions: dict[str, int] = {
            "got_it": 0, "confused": 0, "repeat": 0,
        }
        self.scaffold_level: float = 1.0
        # 1.0 = full scaffolding, 0.0 = no scaffolding
        self.recent_opening_phrases: list[str] = []
        # Tracks first ~10 words of recent teacher speech openings
        # Frame tracking (v2 classroom)
        self.current_frame_id: str = ""
        self.frames_completed: list[str] = []
        self.time_per_frame: dict[str, float] = {}
        self._frame_start_time: float | None = None

        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.last_active_at: str = datetime.now(timezone.utc).isoformat()
        self._segment_start_time: float | None = None

    def to_dict(self) -> dict:
        """Serialize for JSONB storage."""
        return {
            "current_segment_id": self.current_segment_id,
            "segments_completed": self.segments_completed,
            "student_scores": self.student_scores,
            "dialogue_history": self.dialogue_history[-20:],  # keep last 20
            "time_per_segment": self.time_per_segment,
            "reactions": self.reactions,
            "scaffold_level": self.scaffold_level,
            "recent_opening_phrases": self.recent_opening_phrases,
            "started_at": self.started_at,
            "last_active_at": self.last_active_at,
            # Frame tracking (v2)
            "current_frame_id": self.current_frame_id,
            "frames_completed": self.frames_completed,
            "time_per_frame": self.time_per_frame,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DialogueState:
        """Deserialize from JSONB."""
        state = cls()
        state.current_segment_id = data.get("current_segment_id", "")
        state.segments_completed = data.get("segments_completed", [])
        state.student_scores = data.get("student_scores", {})
        state.dialogue_history = data.get("dialogue_history", [])
        state.time_per_segment = data.get("time_per_segment", {})
        state.reactions = data.get("reactions", {
            "got_it": 0, "confused": 0, "repeat": 0,
        })
        state.scaffold_level = data.get("scaffold_level", 1.0)
        state.recent_opening_phrases = data.get("recent_opening_phrases", [])
        state.started_at = data.get("started_at", datetime.now(timezone.utc).isoformat())
        state.last_active_at = data.get("last_active_at", datetime.now(timezone.utc).isoformat())
        # Frame tracking (v2)
        state.current_frame_id = data.get("current_frame_id", "")
        state.frames_completed = data.get("frames_completed", [])
        state.time_per_frame = data.get("time_per_frame", {})
        return state

    def start_segment(self, segment_id: str) -> None:
        """Mark the start of a new segment."""
        import time
        self.current_segment_id = segment_id
        self._segment_start_time = time.time()
        self.last_active_at = datetime.now(timezone.utc).isoformat()

    def complete_segment(self, segment_id: str) -> None:
        """Mark a segment as completed and record time spent."""
        import time
        if segment_id not in self.segments_completed:
            self.segments_completed.append(segment_id)
        if self._segment_start_time:
            elapsed = time.time() - self._segment_start_time
            self.time_per_segment[segment_id] = elapsed
            self._segment_start_time = None

    # ── Frame tracking (v2 classroom) ──

    def start_frame(self, frame_id: str) -> None:
        """Mark the start of a new frame."""
        import time
        self.current_frame_id = frame_id
        self._frame_start_time = time.time()
        self.last_active_at = datetime.now(timezone.utc).isoformat()

    def complete_frame(self, frame_id: str) -> None:
        """Mark a frame as completed and record time spent."""
        import time
        if frame_id not in self.frames_completed:
            self.frames_completed.append(frame_id)
        if self._frame_start_time:
            elapsed = time.time() - self._frame_start_time
            self.time_per_frame[frame_id] = elapsed
            self._frame_start_time = None

    def get_frame_progress(self, total_frames: int) -> float:
        """Calculate frame-based progress percentage."""
        if total_frames == 0:
            return 0.0
        return len(self.frames_completed) / total_frames * 100

    def record_score(
        self,
        segment_id: str,
        verdict: str,
        attempts: int,
        hints_used: int,
        question: str = "",
    ) -> None:
        """Record a CHECK_UNDERSTANDING result."""
        self.student_scores[segment_id] = {
            "verdict": verdict,
            "attempts": attempts,
            "hints_used": hints_used,
            "question": question,
        }
        # Adjust scaffold level based on performance
        self._adjust_scaffolding(verdict)

    def add_dialogue(self, role: str, content: str) -> None:
        """Add a dialogue entry (teacher or student speech)."""
        self.dialogue_history.append({
            "role": role,
            "content": content[:500],  # truncate long entries
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep only last 20 entries to limit memory
        if len(self.dialogue_history) > 20:
            self.dialogue_history = self.dialogue_history[-20:]

    def add_reaction(self, reaction_type: str) -> None:
        """Record a student reaction."""
        if reaction_type in self.reactions:
            self.reactions[reaction_type] += 1

    def record_opening_phrase(self, speech: str) -> None:
        """Extract and store the opening phrase from teacher speech."""
        words = speech.strip().split()[:10]
        if words:
            phrase = " ".join(words)
            self.recent_opening_phrases.append(phrase)
            if len(self.recent_opening_phrases) > 5:
                self.recent_opening_phrases = self.recent_opening_phrases[-5:]

    def get_avoid_phrases(self) -> list[str]:
        """Return recently used opening phrases for the LLM to avoid."""
        return list(self.recent_opening_phrases)

    def get_recent_context(self, n: int = 8) -> list[dict]:
        """Get the last N dialogue entries for LLM context."""
        return self.dialogue_history[-n:]

    def get_progress(self, total_segments: int) -> float:
        """Calculate progress percentage."""
        if total_segments == 0:
            return 0.0
        return len(self.segments_completed) / total_segments * 100

    def get_score_summary(self) -> dict:
        """Get aggregate score summary."""
        total = len(self.student_scores)
        correct = sum(
            1 for s in self.student_scores.values()
            if s.get("verdict") == "correct"
        )
        return {
            "total": total,
            "correct": correct,
            "accuracy": correct / total if total > 0 else 0.0,
        }

    def get_areas_for_review(self) -> list[str]:
        """Get questions the student got wrong for review."""
        return [
            score["question"]
            for score in self.student_scores.values()
            if score.get("verdict") != "correct" and score.get("question")
        ]

    def is_confused(self) -> bool:
        """Check if recent reactions indicate confusion."""
        total = sum(self.reactions.values())
        if total < 3:
            return False
        return self.reactions.get("confused", 0) / total > 0.3

    def _adjust_scaffolding(self, verdict: str) -> None:
        """Adaptively adjust scaffolding level.

        Correct answers reduce scaffolding (student needs less help).
        Wrong/confused answers increase it.
        """
        if verdict == "correct":
            self.scaffold_level = max(0.0, self.scaffold_level - 0.15)
        elif verdict == "wrong":
            self.scaffold_level = min(1.0, self.scaffold_level + 0.1)
        elif verdict == "confused":
            self.scaffold_level = min(1.0, self.scaffold_level + 0.2)
