"""Animation Agent v2 — prompts for generating self-contained HTML visuals and Manim MP4s."""

from app.agents.animation.manim_reference import MANIM_API_REFERENCE

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

=== CRITICAL RULES ===

- NEVER procedurally generate images of faces, people, objects, or scenes with code.
  Always use REAL photographs from Unsplash via direct URL:
  `https://images.unsplash.com/photo-PHOTO_ID?w=800&q=80&fit=crop`
  Good photo IDs to use:
    Face closeup: photo-1531746020798-e6953c6e8e04
    Portrait:     photo-1507003211169-0a1dd7228f2d
    Landscape:    photo-1506744038136-46273834b3fb
    City:         photo-1477959858617-67f85cf4f1df
    Abstract:     photo-1550684376-efcbd6e3f031
  Load images via `new Image()` or `<img>` tag with crossOrigin="anonymous".
  Use opacity/filter CSS transitions to reveal, fade, blur, or transform images.

- For noise/static effects, use a `<canvas>` with random pixel data (ImageData API).
  Overlay noise canvas ON TOP of the image, then fade the noise opacity to reveal.
  This creates the "noise resolving into image" effect properly.

- For zoom effects, use CSS transform: scale() + transform-origin on a wrapper div.
  Do NOT zoom into a canvas pixel grid (it looks terrible). Zoom the wrapper
  containing the real image so it stays sharp.

=== STYLE RULES ===

- Colors: BLUE #3B82F6 (signal), RED #EF4444 (noise/error), GREEN #22C55E (output),
  YELLOW #F59E0B (highlight), PURPLE #8B5CF6 (secondary), WHITE #c9d1d9 (text)
- Smooth easing: "power2.inOut" default
- Clean typography, proper spacing
- Mathematical accuracy (correct Gaussian PDF, proper axis scales)
- Dark background #0d1117, never show raw canvas background color when zooming

=== STEP LABELS ===

Create at least 3 GSAP labels so the teacher can seek to specific moments.
Example: tl.addLabel("intro").to(...).addLabel("formula").to(...).addLabel("result")

Output ONLY the raw JavaScript code. No markdown fences, no explanations, no comments before/after the code.
"""


FIX_PROMPT = """\
Your previous JavaScript code for this animation had a syntax error. Fix it.

FRAME: {frame_id}
TYPE: {visual_type}
DESCRIPTION: {description}

=== ERROR ===
{error}

=== YOUR PREVIOUS CODE (has the error above) ===
{previous_code}

=== INSTRUCTIONS ===
Fix the syntax error in the code above. The most common issues are:
- Unmatched braces (extra or missing {{ or }})
- Missing semicolons or commas
- Unclosed template literals
- Mismatched parentheses

Return the COMPLETE FIXED JavaScript code. Not a diff, not a patch — the full working code.
Output ONLY the raw JavaScript code. No markdown fences, no explanations.
"""


def build_fix_prompt(frame: dict, previous_code: str, error: str) -> str:
    """Build a prompt to fix a syntax error in previously generated code."""
    vspec = frame.get("visual_spec", {})
    description = vspec.get("description", "")
    if not description:
        description = str(vspec)

    return FIX_PROMPT.format(
        frame_id=frame.get("frame_id", "unknown"),
        visual_type=frame.get("visual_type", "animation"),
        description=description[:200],
        error=error,
        previous_code=previous_code,
    )


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


# ═══════════════════════════════════════════════════════════
# Manim prompts — for frames routed to Manim renderer
# ═══════════════════════════════════════════════════════════

MANIM_GENERATION_SYSTEM = """\
You are an expert Manim Community Edition animator creating 3Blue1Brown-quality \
mathematical visualizations. You write ONLY Python code using Manim CE v0.20. \
The code must define a class `AnimationScene` that extends `Scene` (or `ThreeDScene` \
for 3D visuals). Return ONLY the raw Python code. No markdown fences, no explanations."""


MANIM_3D_REFERENCE = """\

### 3D Scenes (use ThreeDScene instead of Scene)
```python
class AnimationScene(ThreeDScene):
    def construct(self):
        # Set initial camera angle
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)

        # 3D Axes
        axes = ThreeDAxes(
            x_range=[-3, 3, 1], y_range=[-3, 3, 1], z_range=[0, 1, 0.2],
            x_length=6, y_length=6, z_length=4,
        )

        # Parametric Surface (e.g. Gaussian)
        surface = Surface(
            lambda u, v: axes.c2p(u, v, np.exp(-(u**2 + v**2) / 2) / (2 * np.pi)),
            u_range=[-3, 3], v_range=[-3, 3],
            resolution=(32, 32),
        )
        surface.set_style(
            fill_opacity=0.7, fill_color=BLUE,
            stroke_color=WHITE, stroke_width=0.5,
        )

        self.play(Create(axes), run_time=1)
        self.play(Create(surface), run_time=2)

        # Animate camera
        self.begin_ambient_camera_rotation(rate=0.15)
        self.wait(3)
        self.stop_ambient_camera_rotation()

        # Move camera to specific angle
        self.move_camera(phi=60 * DEGREES, theta=-30 * DEGREES, run_time=2)

        # 3D objects
        sphere = Sphere(radius=0.3, color=RED).move_to(axes.c2p(1, 1, 0.2))
        dot3d = Dot3D(point=axes.c2p(0, 0, 0.15), color=YELLOW)
        arrow3d = Arrow3D(start=axes.c2p(0, 0, 0), end=axes.c2p(1, 1, 0.3))

        # 3D surface from function
        def gaussian_2d(u, v):
            z = np.exp(-(u**2 + v**2) / 2) / (2 * np.pi)
            return axes.c2p(u, v, z)
```

### Heatmap / Contour (top-down view of 2D function)
```python
class AnimationScene(ThreeDScene):
    def construct(self):
        # Top-down view for heatmap effect
        self.set_camera_orientation(phi=0 * DEGREES, theta=-90 * DEGREES)

        axes = ThreeDAxes(x_range=[-3, 3, 1], y_range=[-3, 3, 1], z_range=[0, 1, 0.2])

        surface = Surface(
            lambda u, v: axes.c2p(u, v, np.exp(-(u**2 + v**2) / 2)),
            u_range=[-3, 3], v_range=[-3, 3], resolution=(48, 48),
        )
        # Color gradient for heatmap effect
        surface.set_fill_by_value(
            axes=axes, colorscale=[(BLUE, 0), (GREEN, 0.3), (YELLOW, 0.6), (RED, 1.0)],
        )
        surface.set_stroke(width=0)
```

### Camera Transitions
```python
# Start with 3D perspective, then transition to 2D top-down
self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
self.play(Create(surface), run_time=2)
self.wait(1)
# Transition to top-down (heatmap view)
self.move_camera(phi=0 * DEGREES, theta=-90 * DEGREES, run_time=3)
```
"""


MANIM_GENERATION_PROMPT = """\
Write Manim CE Python code for this educational visualization:

FRAME: {frame_id}
TYPE: {visual_type}
DESCRIPTION: {description}
TARGET DURATION: {duration}s

{steps_section}

=== MANIM API REFERENCE ===

{manim_reference}

{manim_3d_reference}

=== YOUR CODE MUST ===

1. Define `class AnimationScene(Scene):` (or `ThreeDScene` for 3D visuals)
2. Implement `def construct(self):`
3. Import from manim: `from manim import *` and `import numpy as np`
4. Match the target duration using `self.wait()` calls between steps
5. Be fully self-contained — no external files, no network calls

=== STEP TIMING ===

Each step in the animation should match these approximate durations.
Insert `self.wait()` calls to create natural pauses between steps:
{step_timing}

=== STYLE RULES ===

- Background: self.camera.background_color = "#0d1117"
- Colors: BLUE (signal), RED (noise/error), GREEN (output), YELLOW (highlight), \
PURPLE (secondary), WHITE (text/labels)
- Custom colors via ManimColor("#hex")
- Clean typography: Text(font_size=36) for titles, Text(font_size=24) for labels
- Mathematical accuracy: correct Gaussian PDF, proper axis scales, real formulas
- Smooth animations: run_time=1-2 for most transitions

=== LAYOUT RULES ===

- Title: to_edge(UP), font_size=28-36
- Main visual: ORIGIN (center), largest element
- Labels/annotations: to_corner(DL) or to_edge(DOWN), font_size=16-20
- Do NOT overlap text with the main visual
- Images: set_height(4-5), center at ORIGIN
- Axes: x_length=6-8, y_length=4-5 for good proportions
- Buff: minimum 0.3 between elements

=== CRITICAL RULES ===

- Use MathTex() for ALL mathematical formulas (LaTeX IS installed)
- Use Text() for plain labels (NOT MathTex for non-math text)
- For 3D scenes: use ThreeDScene, ThreeDAxes, Surface
- For 2D plots: use Axes with axes.plot()
- Progressive animation: reveal elements one at a time, not all at once
- End with self.wait(2) so the final state is visible

Output ONLY the raw Python code. No markdown fences, no explanations, no comments \
before or after the code.
"""


MANIM_FIX_PROMPT = """\
Your previous Manim Python code had an error. Fix it.

FRAME: {frame_id}
TYPE: {visual_type}
DESCRIPTION: {description}

=== ERROR ===
{error}

=== YOUR PREVIOUS CODE (has the error above) ===
{previous_code}

=== COMMON MANIM ISSUES ===
- "LaTeX compilation error" → check MathTex syntax, use Text() for non-math strings
- "'Scene' has no attribute 'set_camera_orientation'" → use ThreeDScene, not Scene
- "ModuleNotFoundError" → only use `from manim import *` and `import numpy as np`
- "name 'xxx' is not defined" → define all mobjects before using them
- Indentation errors → ensure all code is inside construct()
- "cannot unpack non-sequence" → check function signatures and return types

=== INSTRUCTIONS ===
Fix the error in the code above. Return the COMPLETE FIXED Python code.
Not a diff, not a patch — the full working code.
Output ONLY the raw Python code. No markdown fences, no explanations.
"""


def build_manim_generation_prompt(frame: dict) -> str:
    """Build the prompt for generating a Manim animation."""
    steps = frame.get("steps", [])
    steps_section = ""
    step_timing = ""

    if steps:
        step_lines = []
        timing_lines = []
        for s in steps:
            label = s.get("label", s.get("step_id", "?"))
            step_lines.append(
                f"  - Step '{label}': "
                f"{s.get('description', '')} ({s.get('duration_seconds', 3)}s)"
                f"{' [PAUSE]' if s.get('pause_after') else ''}"
            )
            timing_lines.append(
                f"  - '{label}': ~{s.get('duration_seconds', 3)}s"
            )
        steps_section = "ANIMATION STEPS:\n" + "\n".join(step_lines)
        step_timing = "\n".join(timing_lines)
    else:
        steps_section = "NO EXPLICIT STEPS — create at least 3 logical phases from the description."
        step_timing = "Create ~3 phases of roughly equal duration."

    vspec = frame.get("visual_spec", {})
    description = vspec.get("description", "")
    if not description:
        description = str(vspec)

    # Include 3D reference if description suggests 3D content
    desc_lower = description.lower()
    needs_3d = any(kw in desc_lower for kw in [
        "3d", "surface", "heatmap", "contour", "camera", "sphere", "rotation",
    ])
    manim_3d = MANIM_3D_REFERENCE if needs_3d else ""

    return MANIM_GENERATION_PROMPT.format(
        frame_id=frame.get("frame_id", "unknown"),
        visual_type=frame.get("visual_type", "animation"),
        description=description,
        duration=frame.get("estimated_seconds", 30),
        steps_section=steps_section,
        step_timing=step_timing,
        manim_reference=MANIM_API_REFERENCE,
        manim_3d_reference=manim_3d,
    )


def build_manim_fix_prompt(frame: dict, previous_code: str, error: str) -> str:
    """Build a prompt to fix an error in Manim code."""
    vspec = frame.get("visual_spec", {})
    description = vspec.get("description", "")
    if not description:
        description = str(vspec)

    return MANIM_FIX_PROMPT.format(
        frame_id=frame.get("frame_id", "unknown"),
        visual_type=frame.get("visual_type", "animation"),
        description=description[:200],
        error=error[-1500:],
        previous_code=previous_code,
    )
