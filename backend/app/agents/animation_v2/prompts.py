"""Animation Agent v2 — prompts for generating self-contained HTML visuals."""

VISUAL_GENERATION_SYSTEM = """\
You are an expert visual animator creating 3Blue1Brown-quality animations. \
You write ONLY JavaScript code that uses the pre-loaded libraries \
(GSAP, D3.js, KaTeX, Prism.js). The code runs inside an HTML template \
that already has these loaded plus a GSAP timeline `tl` and a container \
div `#canvas-container`. Return ONLY JavaScript code. No HTML, no markdown."""


VISUAL_GENERATION_PROMPT = """\
Write JavaScript animation code for this educational visual:

FRAME: {frame_id}
TYPE: {visual_type}
DESCRIPTION: {description}
ESTIMATED DURATION: {duration}s

{steps_section}

=== ENVIRONMENT (already loaded, do NOT import) ===

- `tl` = GSAP timeline (paused, use tl.addLabel(), tl.to(), tl.from(), etc.)
- `gsap` = GSAP global
- `d3` = D3.js v7
- `katex` = KaTeX renderer
- `Prism` = Prism.js syntax highlighter
- `#canvas-container` = the parent div (100vw x 100vh, dark bg #0d1117)

=== YOUR CODE MUST ===

1. Create DOM elements (SVG, Canvas, divs) inside `#canvas-container`
2. Add GSAP labels to `tl` for each logical step: `tl.addLabel("step-name")`
3. Animate using `tl.to()`, `tl.from()`, `tl.fromTo()` on the timeline
4. Use D3 for math plots (Gaussian curves, axes, histograms)
5. Use KaTeX for equations: `katex.render(latex, element, {{throwOnError: false}})`
6. Use Prism for code: `Prism.highlight(code, Prism.languages.python, 'python')`

=== STYLE RULES ===

- Colors: BLUE #3B82F6 (signal), RED #EF4444 (noise/error), GREEN #22C55E (output),
  YELLOW #F59E0B (highlight), PURPLE #8B5CF6 (secondary), WHITE #c9d1d9 (text)
- Smooth easing: "power2.inOut" default
- Clean typography, proper spacing
- Mathematical accuracy (correct Gaussian PDF, proper axis scales)
- For images: `https://image.pollinations.ai/prompt/DESCRIPTION?width=800&height=600`

=== STEP LABELS ===

Create at least 3 GSAP labels so the teacher can seek to specific moments.
Example: tl.addLabel("intro").to(...).addLabel("formula").to(...).addLabel("result")

Write the JavaScript code to a file at: {{output_path}}
Use the Write tool. Do NOT output the code to stdout.
"""


def build_generation_prompt(frame: dict) -> str:
    """Build the prompt for generating one visual frame."""
    steps = frame.get("steps", [])
    steps_section = ""
    if steps:
        step_lines = []
        for s in steps:
            step_lines.append(
                f"  - Step '{s.get('label', s.get('step_id', '?'))}': "
                f"{s.get('description', '')} ({s.get('duration_seconds', 3)}s)"
                f"{' [PAUSE]' if s.get('pause_after') else ''}"
            )
        steps_section = "ANIMATION STEPS (create GSAP labels for each):\n" + "\n".join(step_lines)
    else:
        steps_section = "NO EXPLICIT STEPS — create at least 3 logical steps from the description."

    vspec = frame.get("visual_spec", {})
    description = vspec.get("description", "")
    if not description:
        description = str(vspec)

    return VISUAL_GENERATION_PROMPT.format(
        frame_id=frame.get("frame_id", "unknown"),
        visual_type=frame.get("visual_type", "animation"),
        description=description,
        duration=frame.get("estimated_seconds", 30),
        steps_section=steps_section,
    )
