"""DAG Navigator — the core state machine for the Teacher Agent.

Traverses the teaching DAG segment by segment, yielding TeacherMessages
that the WebSocket handler sends to the frontend. Handles branching
at CHECK_UNDERSTANDING segments based on student responses.
"""

import asyncio
import logging
from typing import AsyncGenerator

from app.agents.teacher import speech_gen
from app.agents.teacher.dialogue_state import DialogueState
from app.agents.teacher.models import (
    AskQuestionMessage,
    ResponseEvaluation,
    SegmentChangeMessage,
    SessionCompleteMessage,
    ShowAnimationMessage,
    SpeakMessage,
    TeacherMessage,
    WaitMessage,
)

logger = logging.getLogger(__name__)


class DagNavigator:
    """Navigates the teaching DAG, yielding messages for the frontend."""

    def __init__(
        self,
        lesson_plan: dict,
        animation_urls: dict[str, str],
        teaching_style: str,
        student_name: str,
        state: DialogueState,
    ):
        self.lesson = lesson_plan
        self.segments: dict[str, dict] = {}
        self.segment_order: list[str] = []
        for seg in lesson_plan.get("segments", []):
            sid = seg.get("segment_id", "")
            self.segments[sid] = seg
            self.segment_order.append(sid)

        self.animation_urls = animation_urls
        self.teaching_style = teaching_style
        self.student_name = student_name
        self.state = state

        # Runtime state
        self.hand_raised: bool = False
        self.hand_raiser_name: str = ""
        self.pending_question: str = ""
        self.paused: bool = False
        self._student_response: str | None = None
        self._response_event = asyncio.Event()
        self._speech_done_event = asyncio.Event()
        self._speech_done_event.set()  # Start as "done" so first message sends immediately

    @property
    def total_segments(self) -> int:
        return len(self.segment_order)

    def acknowledge_speech(self) -> None:
        """Called by WebSocket handler when frontend finishes playing speech."""
        self._speech_done_event.set()

    def receive_response(self, text: str) -> None:
        """Called by WebSocket handler when student responds."""
        self._student_response = text
        self._response_event.set()

    def raise_hand(self, student_name: str) -> None:
        """Called when a student raises their hand."""
        self.hand_raised = True
        self.hand_raiser_name = student_name

    def set_question(self, question: str) -> None:
        """Called when a raised-hand student asks their question."""
        self.pending_question = question
        self._response_event.set()

    async def run(self) -> AsyncGenerator[TeacherMessage, None]:
        """Main teaching loop — yields messages for the frontend."""

        # Determine starting point
        if self.state.current_segment_id and self.state.segments_completed:
            # Resuming — generate welcome back
            scores = self.state.get_score_summary()
            remaining = self.total_segments - len(self.state.segments_completed)
            last_completed = self.state.segments_completed[-1] if self.state.segments_completed else ""
            last_title = self.segments.get(last_completed, {}).get("title", "the previous topic")

            welcome = await speech_gen.generate_welcome_back(
                student_name=self.student_name,
                lesson_title=self.lesson.get("title", ""),
                last_segment=last_title,
                segments_remaining=remaining,
                correct=scores.get("correct", 0),
                total=scores.get("total", 0),
                teaching_style=self.teaching_style,
            )
            yield SpeakMessage(text=welcome, speech_type="opening")
            self.state.add_dialogue("teacher", welcome)
            yield WaitMessage(seconds=2, reason="welcome_pause")

            current_id = self.state.current_segment_id
        else:
            # Fresh start — opening hook
            opening = await speech_gen.generate_opening(
                opening_hook=self.lesson.get("opening_hook", "Let's begin!"),
                lesson_title=self.lesson.get("title", ""),
                student_name=self.student_name,
                teaching_style=self.teaching_style,
            )
            yield SpeakMessage(text=opening, speech_type="opening")
            self.state.add_dialogue("teacher", opening)
            yield WaitMessage(seconds=2, reason="opening_pause")

            current_id = self.segment_order[0] if self.segment_order else None

        # Main segment loop
        prev_title = ""
        while current_id and current_id in self.segments:
            if self.paused:
                await asyncio.sleep(1)
                continue

            segment = self.segments[current_id]
            seg_type = segment.get("segment_type", "TEACH")
            seg_title = segment.get("title", "")

            self.state.start_segment(current_id)
            progress = self.state.get_progress(self.total_segments)

            yield SegmentChangeMessage(
                segment_id=current_id,
                segment_type=seg_type,
                segment_title=seg_title,
                progress_pct=progress,
            )

            # Handle each segment type
            if seg_type == "TEACH":
                async for msg in self._handle_teach(segment):
                    yield msg

            elif seg_type == "DEMONSTRATE":
                async for msg in self._handle_demonstrate(segment):
                    yield msg

            elif seg_type == "CHECK_UNDERSTANDING":
                next_id = None
                async for result in self._handle_check_flow(segment):
                    if isinstance(result, str):
                        # It's the next segment ID (final yield)
                        next_id = result
                    else:
                        yield result
                if next_id:
                    self.state.complete_segment(current_id)
                    prev_title = seg_title
                    current_id = next_id
                    continue

            elif seg_type == "PRACTICE":
                async for msg in self._handle_practice(segment):
                    yield msg

            elif seg_type == "TRANSITION":
                next_title = ""
                next_seg_id = segment.get("next_segment")
                if next_seg_id and next_seg_id in self.segments:
                    next_title = self.segments[next_seg_id].get("title", "")

                speech = await speech_gen.generate_transition(
                    bridge_text=segment.get("bridge_text", ""),
                    prev_topic=prev_title,
                    next_topic=next_title,
                    teaching_style=self.teaching_style,
                )
                yield SpeakMessage(text=speech, segment_id=current_id, speech_type="transition")
                self.state.add_dialogue("teacher", speech)

            # Check for raised hands at segment boundaries
            if self.hand_raised:
                async for msg in self._handle_raised_hand(segment):
                    yield msg

            # Check for "repeat" reactions — re-explain if requested
            if self.state.reactions.get("repeat", 0) > 0 and seg_type == "TEACH":
                # Reset repeat counter and re-explain
                self.state.reactions["repeat"] = 0
                repeat_speech = await speech_gen.generate_segment_speech(
                    segment_title=segment.get("title", ""),
                    key_points=segment.get("key_points", []),
                    formulas=[],
                    analogies=segment.get("analogies", []),
                    misconceptions=[],
                    recent_context=[{"role": "system", "content": "Student asked to repeat. Explain differently."}],
                    teaching_style=self.teaching_style,
                    avoid_phrases=self.state.get_avoid_phrases() or None,
                )
                yield SpeakMessage(text=repeat_speech, segment_id=current_id, speech_type="teaching")
                self.state.add_dialogue("teacher", f"[Repeat] {repeat_speech}")

            self.state.complete_segment(current_id)
            prev_title = seg_title
            current_id = segment.get("next_segment")

        # Lesson complete
        scores = self.state.get_score_summary()
        areas = self.state.get_areas_for_review()
        closing = await speech_gen.generate_closing(
            summary_points=self.lesson.get("closing_summary", []),
            scores=scores,
            areas_for_review=areas,
            teaching_style=self.teaching_style,
        )
        yield SpeakMessage(text=closing, speech_type="closing")
        self.state.add_dialogue("teacher", closing)

        summary = {
            "concepts_covered": [
                self.segments[sid].get("title", "")
                for sid in self.state.segments_completed
                if self.segments.get(sid, {}).get("segment_type") == "TEACH"
            ],
            "time_spent_minutes": round(sum(self.state.time_per_segment.values()) / 60, 1),
            "segments_completed": len(self.state.segments_completed),
            "questions_asked": scores.get("total", 0),
            "questions_correct": scores.get("correct", 0),
            "areas_for_review": areas,
        }
        yield SessionCompleteMessage(summary=summary)

    async def _handle_teach(self, segment: dict) -> AsyncGenerator[TeacherMessage, None]:
        """Handle a TEACH segment."""
        sid = segment.get("segment_id", "")

        # Collect animation metadata for speech context + show animations
        active_animations: list[dict] = []
        for anim in segment.get("animations", []):
            if anim.get("trigger", "auto") == "auto":
                anim_id = anim.get("animation_id", "")
                url = self.animation_urls.get(anim_id, "")
                if url:
                    active_animations.append({
                        "animation_type": anim.get("animation_type", "visual"),
                        "title": anim.get("title", ""),
                        "description": anim.get("description", "")[:100],
                        "duration_seconds": anim.get("duration_seconds", 10),
                    })
                    yield ShowAnimationMessage(
                        animation_id=anim_id,
                        animation_url=url,
                        action="play",
                        duration_seconds=anim.get("duration_seconds", 10),
                    )

        # Generate speech with animation context + avoid repetition
        formulas = [f for f in segment.get("formulas", [])]
        speech = await speech_gen.generate_segment_speech(
            segment_title=segment.get("title", ""),
            key_points=segment.get("key_points", []),
            formulas=formulas,
            analogies=segment.get("analogies", []),
            misconceptions=segment.get("misconceptions_to_address", []),
            recent_context=self.state.get_recent_context(),
            teaching_style=self.teaching_style,
            animations=active_animations or None,
            avoid_phrases=self.state.get_avoid_phrases() or None,
        )
        yield SpeakMessage(text=speech, segment_id=sid, speech_type="teaching")
        self.state.add_dialogue("teacher", speech)
        self.state.record_opening_phrase(speech)

        # Strategic pause after teaching
        yield WaitMessage(seconds=3, reason="absorption_time")

    async def _handle_demonstrate(self, segment: dict) -> AsyncGenerator[TeacherMessage, None]:
        """Handle a DEMONSTRATE segment."""
        sid = segment.get("segment_id", "")

        # Collect animation metadata + show animations
        active_animations: list[dict] = []
        for anim in segment.get("animations", []):
            anim_id = anim.get("animation_id", "")
            url = self.animation_urls.get(anim_id, "")
            if url:
                active_animations.append({
                    "animation_type": anim.get("animation_type", "visual"),
                    "title": anim.get("title", ""),
                    "description": anim.get("description", "")[:100],
                    "duration_seconds": anim.get("duration_seconds", 10),
                })
                yield ShowAnimationMessage(
                    animation_id=anim_id,
                    animation_url=url,
                    action="play",
                    duration_seconds=anim.get("duration_seconds", 10),
                )

        # Generate explanation of the code demo
        code_demos = segment.get("code_demos", [])
        if code_demos:
            demo = code_demos[0]
            key_points = [
                f"Let me show you this code: {demo.get('description', '')}",
            ]
            params = demo.get("parameters_to_modify", [])
            if params:
                param_names = [p.get("name", "") for p in params if p.get("name")]
                if param_names:
                    key_points.append(
                        f"Try changing {', '.join(param_names)} to see what happens."
                    )
        else:
            key_points = segment.get("key_points", ["Let me demonstrate this concept."])

        speech = await speech_gen.generate_segment_speech(
            segment_title=segment.get("title", ""),
            key_points=key_points,
            formulas=[],
            analogies=[],
            misconceptions=[],
            recent_context=self.state.get_recent_context(),
            teaching_style=self.teaching_style,
            animations=active_animations or None,
            avoid_phrases=self.state.get_avoid_phrases() or None,
        )
        yield SpeakMessage(text=speech, segment_id=sid, speech_type="teaching")
        self.state.add_dialogue("teacher", speech)
        self.state.record_opening_phrase(speech)

    async def _handle_check_flow(self, segment: dict) -> AsyncGenerator[TeacherMessage | str, None]:
        """Handle CHECK_UNDERSTANDING as a flow.

        Yields TeacherMessage objects, then yields the next segment_id as a string
        as the final value.
        """
        sid = segment.get("segment_id", "")
        interaction = segment.get("interaction", {})
        if not interaction:
            yield segment.get("next_segment", "")
            return

        question = interaction.get("question", "")
        expected = interaction.get("expected_answer", "")
        hints = interaction.get("hints", [])
        max_attempts = 3

        # Generate question intro
        intro = await speech_gen.generate_question_intro(
            question=question,
            question_type=interaction.get("question_type", "conceptual"),
            teaching_style=self.teaching_style,
        )
        yield SpeakMessage(text=intro, segment_id=sid, speech_type="question")
        self.state.add_dialogue("teacher", intro)

        # Send the question to the frontend
        yield AskQuestionMessage(
            question=question,
            question_type=interaction.get("question_type", "conceptual"),
            hints=hints,
            segment_id=sid,
        )

        # Strategic wait before expecting answer
        yield WaitMessage(seconds=4, reason="thinking_time")

        # Wait for student response (with timeout + retry loop)
        hints_given = 0
        for attempt in range(1, max_attempts + 1):
            self._response_event.clear()
            self._student_response = None

            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                self.state.record_score(sid, "confused", attempt, hints_given, question)
                yield interaction.get("if_confused") or segment.get("next_segment", "")
                return

            answer = self._student_response or ""
            self.state.add_dialogue("student", answer)

            # Evaluate
            evaluation = await speech_gen.evaluate_response(
                question=question,
                expected_answer=expected,
                student_answer=answer,
                hints_given=hints_given,
                attempt=attempt,
            )

            # Generate feedback
            remaining_hints = hints[hints_given:]
            feedback = await speech_gen.generate_feedback(
                question=question,
                student_answer=answer,
                verdict=evaluation.verdict,
                explanation=evaluation.explanation,
                attempt=attempt,
                remaining_hints=remaining_hints,
                teaching_style=self.teaching_style,
            )
            yield SpeakMessage(text=feedback, segment_id=sid, speech_type="feedback")
            self.state.add_dialogue("teacher", feedback)

            if evaluation.verdict == "correct":
                self.state.record_score(sid, "correct", attempt, hints_given, question)
                yield interaction.get("if_correct") or segment.get("next_segment", "")
                return

            if evaluation.verdict == "confused":
                self.state.record_score(sid, "confused", attempt, hints_given, question)
                yield interaction.get("if_confused") or segment.get("next_segment", "")
                return

            # Wrong — give hint if available
            if hints_given < len(hints):
                hints_given += 1

            if attempt >= max_attempts:
                self.state.record_score(sid, "wrong", attempt, hints_given, question)
                yield interaction.get("if_wrong") or segment.get("next_segment", "")
                return

            yield WaitMessage(seconds=3, reason="retry_thinking_time")

        yield segment.get("next_segment", "")

    async def _handle_practice(self, segment: dict) -> AsyncGenerator[TeacherMessage, None]:
        """Handle a PRACTICE segment."""
        sid = segment.get("segment_id", "")
        title = segment.get("exercise_title", segment.get("title", ""))
        description = segment.get("exercise_description", "")

        speech = f"Alright, time for some practice! {description}" if description else \
            f"Let's practice what we've learned with an exercise: {title}"

        yield SpeakMessage(text=speech, segment_id=sid, speech_type="teaching")
        self.state.add_dialogue("teacher", speech)

        # Show hints progressively
        hints = segment.get("exercise_hints", [])
        if hints:
            yield WaitMessage(seconds=5, reason="practice_time")
            speech2 = f"Here's a hint to get you started: {hints[0]}"
            yield SpeakMessage(text=speech2, segment_id=sid, speech_type="feedback")

    async def _handle_raised_hand(self, current_segment: dict) -> AsyncGenerator[TeacherMessage, None]:
        """Handle a student's raised hand."""
        name = self.hand_raiser_name or self.student_name
        self.hand_raised = False

        # Acknowledge
        ack = f"I see you have a question, {name}. Go ahead!"
        yield SpeakMessage(text=ack, speech_type="response")
        self.state.add_dialogue("teacher", ack)

        # Wait for the question
        self._response_event.clear()
        self._student_response = None

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=30)
        except asyncio.TimeoutError:
            yield SpeakMessage(
                text="No worries, you can ask anytime. Let's continue.",
                speech_type="response",
            )
            return

        question = self.pending_question or self._student_response or ""
        self.pending_question = ""
        self.state.add_dialogue("student", question)

        # Generate response
        response = await speech_gen.handle_student_question(
            student_question=question,
            current_topic=current_segment.get("title", ""),
            segment_key_points=current_segment.get("key_points", []),
            recent_context=self.state.get_recent_context(),
            teaching_style=self.teaching_style,
        )
        yield SpeakMessage(text=response, speech_type="response")
        self.state.add_dialogue("teacher", response)

        yield WaitMessage(seconds=2, reason="question_answered")
