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
