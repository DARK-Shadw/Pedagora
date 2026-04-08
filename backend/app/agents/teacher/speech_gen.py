"""Speech generation for the Teacher Agent via Groq LLM.

Converts structured teaching data (key_points, formulas, interactions)
into natural spoken English. Each call is short (~200 tokens in, ~100 out)
and takes 200-400ms on Groq.
"""

import json
import logging
import re

from pydantic_ai import Agent

from app.agents.models import create_model
from app.agents.retry import run_with_retry
from app.agents.teacher.models import ResponseEvaluation
from app.agents.teacher.prompts import (
    CLOSING_PROMPT,
    COMMON_CONSTRAINTS,
    EVALUATE_RESPONSE_PROMPT,
    FEEDBACK_PROMPT,
    OPENING_PROMPT,
    PERSONALITY_PROMPTS,
    QUESTION_INTRO_PROMPT,
    SEGMENT_SPEECH_PROMPT,
    STUDENT_QUESTION_PROMPT,
    TRANSITION_PROMPT,
    WELCOME_BACK_PROMPT,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def sanitize_for_tts(text: str) -> str:
    """Convert math notation in speech text to spoken form for TTS.

    Applied as post-processing on all LLM-generated speech to catch any
    mathematical notation the prompt instructions didn't prevent.
    """
    # Step 1: LaTeX commands
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'\1 over \2', text)
    text = re.sub(r'\\sqrt\{([^}]*)\}', r'square root of \1', text)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathbb\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\cdot', ' times ', text)
    text = re.sub(r'\\times', ' times ', text)
    text = re.sub(r'\\leq', ' less than or equal to ', text)
    text = re.sub(r'\\geq', ' greater than or equal to ', text)
    text = re.sub(r'\\neq', ' not equal to ', text)
    text = re.sub(r'\\(?:rightarrow|to)\b', ' goes to ', text)
    text = re.sub(r'\\infty', ' infinity ', text)
    text = re.sub(r'\\approx', ' approximately ', text)
    text = re.sub(r'\\sum', ' sum of ', text)
    text = re.sub(r'\\prod', ' product of ', text)
    text = re.sub(r'\\int', ' integral of ', text)
    text = re.sub(r'\\partial', ' partial ', text)
    # Greek letters — convert to spoken form before stripping
    greek = {
        'alpha': 'alpha', 'beta': 'beta', 'gamma': 'gamma',
        'delta': 'delta', 'epsilon': 'epsilon', 'zeta': 'zeta',
        'eta': 'eta', 'theta': 'theta', 'iota': 'iota',
        'kappa': 'kappa', 'lambda': 'lambda', 'mu': 'mu',
        'nu': 'nu', 'xi': 'xi', 'pi': 'pi', 'rho': 'rho',
        'sigma': 'sigma', 'tau': 'tau', 'phi': 'phi',
        'chi': 'chi', 'psi': 'psi', 'omega': 'omega',
        'Alpha': 'Alpha', 'Beta': 'Beta', 'Gamma': 'Gamma',
        'Delta': 'Delta', 'Sigma': 'Sigma', 'Omega': 'Omega',
        'Pi': 'Pi', 'Theta': 'Theta', 'Lambda': 'Lambda',
    }
    for cmd, spoken in greek.items():
        text = text.replace(f'\\{cmd}', f' {spoken} ')
    # Strip remaining LaTeX commands
    text = re.sub(r'\\[a-zA-Z]+', '', text)

    # Step 2: Superscripts
    text = re.sub(r'\^\{([^}]*)\}', r' to the \1', text)
    text = re.sub(r'\^2\b', ' squared', text)
    text = re.sub(r'\^3\b', ' cubed', text)
    text = re.sub(r'\^([a-zA-Z0-9])', r' to the \1', text)

    # Step 3: Subscripts
    text = re.sub(r'_\{([^}]*)\}', r' \1', text)
    text = re.sub(r'_([a-zA-Z0-9])', r' \1', text)

    # Step 4: Cleanup
    text = text.replace('$', '')
    text = text.replace('{', '')
    text = text.replace('}', '')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _get_personality(teaching_style: str) -> str:
    """Get the personality prompt for the given teaching style."""
    template = PERSONALITY_PROMPTS.get(teaching_style, PERSONALITY_PROMPTS["lecture"])
    return template.format(common_constraints=COMMON_CONSTRAINTS)


async def _generate(prompt: str, model_string: str | None = None) -> str:
    """Run a single Groq LLM call and return the text."""
    import os
    settings = get_settings()

    # Ensure GROQ_API_KEY is in os.environ (PydanticAI reads it directly)
    if settings.groq_api_key and not os.environ.get("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = settings.groq_api_key

    model = model_string or settings.teacher_model
    agent = Agent(create_model(model), output_type=str)

    async def _run():
        result = await agent.run(prompt)
        return result.output

    return await run_with_retry(_run)


async def generate_opening(
    opening_hook: str,
    lesson_title: str,
    student_name: str,
    teaching_style: str,
) -> str:
    """Generate the opening speech for a lesson."""
    prompt = OPENING_PROMPT.format(
        personality=_get_personality(teaching_style),
        student_name=student_name or "there",
        opening_hook=opening_hook,
        lesson_title=lesson_title,
    )
    return sanitize_for_tts(await _generate(prompt))


async def generate_segment_speech(
    segment_title: str,
    key_points: list[str],
    formulas: list[dict],
    analogies: list[str],
    misconceptions: list[str],
    recent_context: list[dict],
    teaching_style: str,
    animations: list[dict] | None = None,
    avoid_phrases: list[str] | None = None,
) -> str:
    """Convert a TEACH segment into natural speech."""
    formula_text = "\n".join(
        f"- {f.get('formula_plain', '')} — {f.get('context', '')}"
        for f in formulas
    ) if formulas else "None"

    context_text = "\n".join(
        f"[{d.get('role', '?')}]: {d.get('content', '')[:100]}"
        for d in recent_context
    ) if recent_context else "Start of lesson"

    animation_text = "\n".join(
        f"- [{a.get('animation_type', 'visual')}] {a.get('title', '')}: "
        f"{a.get('description', '')[:100]}"
        for a in animations
    ) if animations else "None"

    avoid_text = "\n".join(
        f'- "{p}"' for p in avoid_phrases
    ) if avoid_phrases else "None"

    prompt = SEGMENT_SPEECH_PROMPT.format(
        personality=_get_personality(teaching_style),
        segment_title=segment_title,
        key_points="\n".join(f"- {kp}" for kp in key_points) if key_points else "None",
        formulas=formula_text,
        analogies="\n".join(f"- {a}" for a in analogies) if analogies else "None",
        misconceptions="\n".join(f"- {m}" for m in misconceptions) if misconceptions else "None",
        animations=animation_text,
        avoid_phrases=avoid_text,
        recent_context=context_text,
    )
    return sanitize_for_tts(await _generate(prompt))


async def generate_question_intro(
    question: str,
    question_type: str,
    teaching_style: str,
) -> str:
    """Generate a natural intro before asking a CHECK_UNDERSTANDING question."""
    prompt = QUESTION_INTRO_PROMPT.format(
        personality=_get_personality(teaching_style),
        question=question,
        question_type=question_type,
    )
    return sanitize_for_tts(await _generate(prompt))


async def evaluate_response(
    question: str,
    expected_answer: str,
    student_answer: str,
    hints_given: int,
    attempt: int,
) -> ResponseEvaluation:
    """Evaluate a student's answer to a CHECK_UNDERSTANDING question."""
    settings = get_settings()
    prompt = EVALUATE_RESPONSE_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        student_answer=student_answer,
        hints_given=hints_given,
        attempt=attempt,
    )

    raw = await _generate(prompt, model_string=settings.teacher_fast_model)

    # Parse the JSON response
    try:
        # Extract JSON from response (might have extra text)
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return ResponseEvaluation(
                verdict=data.get("verdict", "confused"),
                explanation=data.get("explanation", ""),
                confidence=float(data.get("confidence", 0.5)),
            )
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: try to determine verdict from text
    raw_lower = raw.lower()
    if "correct" in raw_lower:
        return ResponseEvaluation(verdict="correct", explanation=raw[:200])
    elif "confused" in raw_lower or "don't know" in raw_lower:
        return ResponseEvaluation(verdict="confused", explanation=raw[:200])
    return ResponseEvaluation(verdict="wrong", explanation=raw[:200])


async def generate_feedback(
    question: str,
    student_answer: str,
    verdict: str,
    explanation: str,
    attempt: int,
    remaining_hints: list[str],
    teaching_style: str,
) -> str:
    """Generate teacher feedback after evaluating a student response."""
    if verdict == "correct":
        instruction = "Celebrate their correct answer. Briefly explain WHY it's right."
    elif verdict == "wrong" and remaining_hints:
        instruction = (
            f"They got it wrong. Don't give the answer. Give this hint: "
            f"'{remaining_hints[0]}'. Encourage them to try again."
        )
    elif verdict == "wrong":
        instruction = (
            "They've used all hints. Gently explain the correct answer "
            "and WHY it's correct. Be encouraging about the effort."
        )
    else:  # confused
        instruction = (
            "The student is confused. Simplify the concept using a different "
            "analogy or approach. Be warm and patient."
        )

    prompt = FEEDBACK_PROMPT.format(
        personality=_get_personality(teaching_style),
        question=question,
        student_answer=student_answer,
        verdict=verdict,
        explanation=explanation,
        attempt=attempt,
        remaining_hints=len(remaining_hints),
        feedback_instruction=instruction,
    )
    return sanitize_for_tts(await _generate(prompt))


async def generate_transition(
    bridge_text: str,
    prev_topic: str,
    next_topic: str,
    teaching_style: str,
) -> str:
    """Generate a transition speech between segments."""
    prompt = TRANSITION_PROMPT.format(
        personality=_get_personality(teaching_style),
        bridge_text=bridge_text,
        prev_topic=prev_topic,
        next_topic=next_topic,
    )
    return sanitize_for_tts(await _generate(prompt))


async def generate_closing(
    summary_points: list[str],
    scores: dict,
    areas_for_review: list[str],
    teaching_style: str,
) -> str:
    """Generate the closing speech for a lesson."""
    prompt = CLOSING_PROMPT.format(
        personality=_get_personality(teaching_style),
        summary_points="\n".join(f"- {p}" for p in summary_points),
        questions_asked=scores.get("total", 0),
        questions_correct=scores.get("correct", 0),
        areas_for_review="\n".join(f"- {a}" for a in areas_for_review) if areas_for_review else "None",
    )
    return sanitize_for_tts(await _generate(prompt))


async def handle_student_question(
    student_question: str,
    current_topic: str,
    segment_key_points: list[str],
    recent_context: list[dict],
    teaching_style: str,
) -> str:
    """Generate a response to a student's raised-hand question."""
    context_text = "\n".join(
        f"[{d.get('role', '?')}]: {d.get('content', '')[:100]}"
        for d in recent_context
    ) if recent_context else ""

    prompt = STUDENT_QUESTION_PROMPT.format(
        personality=_get_personality(teaching_style),
        current_topic=current_topic,
        segment_key_points="\n".join(f"- {kp}" for kp in segment_key_points),
        student_question=student_question,
        recent_context=context_text,
    )
    return sanitize_for_tts(await _generate(prompt))


async def generate_welcome_back(
    student_name: str,
    lesson_title: str,
    last_segment: str,
    segments_remaining: int,
    correct: int,
    total: int,
    teaching_style: str,
) -> str:
    """Generate a welcome-back message for a resuming student."""
    prompt = WELCOME_BACK_PROMPT.format(
        personality=_get_personality(teaching_style),
        student_name=student_name or "there",
        lesson_title=lesson_title,
        last_segment=last_segment,
        segments_remaining=segments_remaining,
        correct=correct,
        total=total,
    )
    return sanitize_for_tts(await _generate(prompt))


# ═══════════════════════════════════════════════════════════
# Frame-based speech generation (v2 classroom)
# ═══════════════════════════════════════════════════════════

FRAME_SPEECHES_PROMPT = """\
{personality}

You are explaining a visual that is currently on screen. The student can SEE it.

VISUAL TYPE: {visual_type}
WHAT'S ON SCREEN: {description}
FRAME {frame_index} of {total_frames}

{context_section}

Generate {num_chunks} separate speech chunks to teach this visual. Each chunk should be \
1-3 sentences. Together they should cover ~{target_seconds} seconds of speaking.

RULES:
- Reference what the student can SEE: "Look at...", "Notice how...", "See where..."
- Use the student's name ({student_name}) in one of the chunks
- Don't rush — each chunk explains ONE aspect of the visual
- Connect to previous visuals when possible
- Ask a rhetorical question in one chunk to keep engagement
- NEVER use LaTeX, math notation, or symbols — write everything as spoken English
- Be warm, enthusiastic, genuinely excited about the material

Return ONLY a JSON array of strings, like:
["First chunk here.", "Second chunk here.", "Third chunk here."]
"""

STEP_SPEECH_PROMPT = """\
{personality}

The student is looking at an animation. You are explaining ONE specific step of it.

FRAME: {frame_id} ({visual_type})
CURRENT STEP: "{step_label}" — {step_description}
OVERALL CONTEXT: {frame_description}

{context_section}

Generate ONE speech paragraph (2-4 sentences) explaining what's happening at this step.

RULES:
- Reference what the student can SEE right now at this step
- Be specific about THIS step, not the whole animation
- NEVER use LaTeX or math notation — write everything as spoken English
- Keep it natural and conversational

Return ONLY the speech text, nothing else.
"""


STEP_SPEECHES_PROMPT = """\
{personality}

You are teaching {student_name} live. The student is looking at an animation.
The animation has {step_count} discrete steps. At each step the animation will
PAUSE on a specific visual state. You must explain what is visible at each step.

Animation description: {frame_description}

Steps (in order):
{steps_list}

For EACH step, write ONE short speech (1-2 sentences, ~15 words max) that:
- Describes what the student sees AT THAT EXACT STEP
- Builds on what was said in previous steps (reference earlier steps when natural)
- Sounds natural and conversational, not scripted
- Uses spoken English only — NO LaTeX, NO math notation, NO symbols

Output a JSON array with EXACTLY {step_count} strings, in step order.
Example format: ["First step speech here.", "Second step speech here."]

Return ONLY the JSON array. No markdown fences. No commentary.
"""


async def generate_frame_speeches(
    description: str,
    visual_type: str,
    frame_index: int,
    total_frames: int,
    student_name: str,
    recent_context: list[dict],
    teaching_style: str,
    estimated_seconds: int = 30,
) -> list[str]:
    """Generate 2-4 speech chunks that teach a visual frame's content.

    Returns a list of speech strings, each 1-3 sentences.
    """
    # Calculate how many chunks we need (~8-10 seconds of speech each)
    num_chunks = max(2, min(4, estimated_seconds // 10))
    target_seconds = max(15, estimated_seconds)

    context_section = ""
    if recent_context:
        context_section = "RECENT DIALOGUE:\n" + "\n".join(
            f"[{d.get('role', '?')}]: {d.get('content', '')[:80]}"
            for d in recent_context[-4:]
        )

    prompt = FRAME_SPEECHES_PROMPT.format(
        personality=_get_personality(teaching_style),
        visual_type=visual_type,
        description=description[:500],
        frame_index=frame_index + 1,
        total_frames=total_frames,
        context_section=context_section,
        num_chunks=num_chunks,
        target_seconds=target_seconds,
        student_name=student_name or "there",
    )

    raw = await _generate(prompt)

    # Parse JSON array from response
    try:
        import re as _re
        match = _re.search(r"\[.*\]", raw, _re.DOTALL)
        if match:
            chunks = json.loads(match.group())
            if isinstance(chunks, list) and all(isinstance(c, str) for c in chunks):
                return [sanitize_for_tts(c) for c in chunks if c.strip()]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: split raw text into chunks by sentence boundaries
    sentences = [s.strip() for s in raw.replace("\n", " ").split(". ") if s.strip()]
    if len(sentences) >= 2:
        mid = len(sentences) // 2
        return [
            sanitize_for_tts(". ".join(sentences[:mid]) + "."),
            sanitize_for_tts(". ".join(sentences[mid:]) + "."),
        ]

    return [sanitize_for_tts(raw)]


async def generate_step_speech(
    frame: dict,
    step: dict,
    recent_context: list[dict],
    teaching_style: str,
) -> str:
    """Generate speech for one step within a frame animation."""
    vspec = frame.get("visual_spec", {})
    frame_description = str(vspec.get("description", ""))[:200]

    context_section = ""
    if recent_context:
        context_section = "RECENT DIALOGUE:\n" + "\n".join(
            f"[{d.get('role', '?')}]: {d.get('content', '')[:80]}"
            for d in recent_context[-4:]
        )

    prompt = STEP_SPEECH_PROMPT.format(
        personality=_get_personality(teaching_style),
        frame_id=frame.get("frame_id", "?"),
        visual_type=frame.get("visual_type", "animation"),
        step_label=step.get("label", step.get("step_id", "?")),
        step_description=step.get("description", ""),
        frame_description=frame_description,
        context_section=context_section,
    )

    return sanitize_for_tts(await _generate(prompt))


async def generate_step_speeches(
    frame: dict,
    step_labels: list[str],
    student_name: str,
    teaching_style: str,
) -> list[str]:
    """Generate one short speech per animation step.

    Each speech is 1-2 sentences (~15 words max) describing what is visible
    at that specific step. The animation will be paused at each step while
    the speech plays — this guarantees zero desync.

    On any failure, returns generic fallback speeches so the lesson still plays.
    """
    if not step_labels:
        return []

    vspec = frame.get("visual_spec", {})
    description = str(vspec.get("description", ""))[:300]
    if not description:
        description = str(vspec)[:300]

    steps_text = "\n".join(
        f"{i + 1}. {label}" for i, label in enumerate(step_labels)
    )

    prompt = STEP_SPEECHES_PROMPT.format(
        personality=_get_personality(teaching_style),
        student_name=student_name or "the student",
        frame_description=description or "an animation",
        step_count=len(step_labels),
        steps_list=steps_text,
    )

    def _fallback() -> list[str]:
        return [
            f"Now, notice the {label.replace('-', ' ').replace('_', ' ')}."
            for label in step_labels
        ]

    try:
        raw = await _generate(prompt)
    except Exception as e:
        logger.warning(f"[step_speeches] LLM call failed: {e}")
        return _fallback()

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        speeches = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"[step_speeches] JSON parse failed: {e}, raw={cleaned[:120]!r}")
        return _fallback()

    if not isinstance(speeches, list):
        logger.warning(f"[step_speeches] expected list, got {type(speeches).__name__}")
        return _fallback()

    if len(speeches) != len(step_labels):
        logger.warning(
            f"[step_speeches] count mismatch: got {len(speeches)} for {len(step_labels)} steps"
        )
        # Pad or truncate to match
        if len(speeches) < len(step_labels):
            speeches = list(speeches) + _fallback()[len(speeches):]
        else:
            speeches = speeches[: len(step_labels)]

    return [sanitize_for_tts(str(s)) for s in speeches]
