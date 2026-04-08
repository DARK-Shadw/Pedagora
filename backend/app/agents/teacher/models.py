"""Message types for Teacher Agent WebSocket communication."""

from typing import Literal

from pydantic import BaseModel, Field


# ─── Backend → Frontend Messages ───


class TeacherMessage(BaseModel):
    """Base message from teacher to student."""

    type: str


class SpeakMessage(TeacherMessage):
    """Teacher speaks — frontend plays audio + shows subtitle."""

    type: Literal["speak"] = "speak"
    text: str
    audio: str = ""  # base64-encoded WAV (set by FrameNavigator or router)
    segment_id: str = ""
    speech_type: Literal[
        "opening", "teaching", "transition", "question",
        "feedback", "closing", "response",
    ] = "teaching"


class ShowAnimationMessage(TeacherMessage):
    """Control animation playback in presentation area."""

    type: Literal["show_animation"] = "show_animation"
    animation_id: str
    animation_url: str
    action: Literal["play", "pause", "rewind"] = "play"
    duration_seconds: float = 10.0


class AskQuestionMessage(TeacherMessage):
    """Teacher asks a CHECK_UNDERSTANDING question."""

    type: Literal["ask_question"] = "ask_question"
    question: str
    question_type: str = "conceptual"
    hints: list[str] = Field(default_factory=list)
    segment_id: str = ""


class SegmentChangeMessage(TeacherMessage):
    """Notify frontend of segment transition."""

    type: Literal["segment_change"] = "segment_change"
    segment_id: str
    segment_type: str
    segment_title: str = ""
    progress_pct: float = 0.0


class WaitMessage(TeacherMessage):
    """Strategic pause — frontend shows thinking indicator."""

    type: Literal["wait"] = "wait"
    seconds: float = 3.0
    reason: str = "thinking_time"


class SessionCompleteMessage(TeacherMessage):
    """Lesson finished — frontend shows summary."""

    type: Literal["session_complete"] = "session_complete"
    summary: dict = Field(default_factory=dict)


class ShowFrameMessage(TeacherMessage):
    """Load a new animation frame in the iframe."""

    type: Literal["show_frame"] = "show_frame"
    frame_id: str
    frame_url: str


class SeekStepMessage(TeacherMessage):
    """Seek animation to a specific step label (pauses at that point)."""

    type: Literal["seek_step"] = "seek_step"
    label: str


class AnimationControlMessage(TeacherMessage):
    """Play or pause the current animation."""

    type: Literal["animation_control"] = "animation_control"
    action: Literal["play", "pause"]


class FrameChangeMessage(TeacherMessage):
    """Notify frontend of frame transition + progress."""

    type: Literal["frame_change"] = "frame_change"
    frame_id: str
    frame_index: int
    total_frames: int
    progress_pct: float = 0.0


class FrameBundleMessage(TeacherMessage):
    """Bundled frame + per-step audio for the lockstep sync engine.

    Frontend receives one of these per frame and runs the entire lockstep
    sequence locally (seek -> play audio -> tween -> repeat). Eliminates
    per-chunk WebSocket round-trips and guarantees zero animation/audio drift.
    """

    type: Literal["frame_bundle"] = "frame_bundle"
    frame_id: str
    frame_url: str
    frame_index: int
    total_frames: int
    progress_pct: float = 0.0
    frame_title: str = ""
    fallback_description: str = ""
    # Each step: {label, anim_time, text, audio_b64, duration_s}
    steps: list[dict] = Field(default_factory=list)


class ErrorMessage(TeacherMessage):
    """Error during teaching session."""

    type: Literal["error"] = "error"
    message: str
    recoverable: bool = True


# ─── Frontend → Backend Messages ───


class StudentMessage(BaseModel):
    """Base message from student to teacher."""

    type: str


class StudentResponse(StudentMessage):
    """Student answers a CHECK_UNDERSTANDING question."""

    type: Literal["response"] = "response"
    text: str
    segment_id: str = ""


class RaiseHand(StudentMessage):
    """Student raises hand to ask a question."""

    type: Literal["raise_hand"] = "raise_hand"
    student_name: str = ""


class LowerHand(StudentMessage):
    """Student lowers hand (cancel)."""

    type: Literal["lower_hand"] = "lower_hand"


class Reaction(StudentMessage):
    """Quick reaction button."""

    type: Literal["reaction"] = "reaction"
    reaction_type: Literal["got_it", "confused", "repeat"]


class SessionControl(StudentMessage):
    """Session control actions."""

    type: Literal["control"] = "control"
    action: Literal["pause", "resume", "leave"]


class StudentQuestion(StudentMessage):
    """Student asks a question after raising hand."""

    type: Literal["question"] = "question"
    text: str


class SpeechDone(StudentMessage):
    """Frontend signals that TTS finished playing the last speech."""

    type: Literal["speech_done"] = "speech_done"
    segment_id: str = ""


class FrameDone(StudentMessage):
    """Frontend signals that the entire frame bundle finished playing
    (lockstep engine completed all steps)."""

    type: Literal["frame_done"] = "frame_done"
    frame_id: str = ""


# ─── Internal Types ───


class ResponseEvaluation(BaseModel):
    """Result of evaluating a student's answer."""

    verdict: Literal["correct", "wrong", "confused"]
    explanation: str = ""
    confidence: float = 0.5
