"""Animation Agent v2 — prompts for generating self-contained HTML visuals and Manim MP4s."""

from app.agents.animation.manim_reference import MANIM_API_REFERENCE

VISUAL_GENERATION_SYSTEM = """\
You are an expert visual animator creating 3Blue1Brown-quality educational animations. \
You write JavaScript code that uses pre-loaded libraries (GSAP, D3.js, KaTeX, Prism.js). \
The code runs inside an HTML template with a GSAP timeline `tl` and container \
div `#canvas-container` (100vw x 100vh, bg #0d1117). Return the JavaScript in the \
`code` field of your JSON response — raw JS only, no HTML, no markdown fences.

══ RULE 1: ALL MATH MUST USE katex.render() WITH DOUBLE BACKSLASHES ══

NEVER use textContent, innerHTML, or SVG <text> for math.

CRITICAL ESCAPING: JavaScript eats single backslashes in strings. You MUST \
use DOUBLE backslash (\\\\) for every LaTeX command:
  '\\\\frac{a}{b}'   CORRECT — JS string contains \\frac → KaTeX renders fraction
  '\\\\sum_{i}'      CORRECT — JS string contains \\sum → KaTeX renders sigma
  '\\\\Omega'        CORRECT — JS string contains \\Omega → KaTeX renders greek letter
  '\\\\approx'       CORRECT — JS string contains \\approx → KaTeX renders symbol
  '\\\\to'           CORRECT — JS string contains \\to → KaTeX renders arrow
  '\\\\color{red}'   CORRECT — JS string contains \\color → KaTeX applies color
  '\\\\text{hello}'  CORRECT — JS string contains \\text → KaTeX renders text

Single backslash is DESTROYED by JavaScript:
  '\\frac{a}{b}'  BROKEN — \\f = form-feed char, renders garbage
  '\\to'          BROKEN — \\t = tab char, renders nothing
  '\\sum'         BROKEN — \\s = just 's', renders "sum" as text
  '\\Omega'       BROKEN — backslash dropped, renders "Omega" as text

CORRECT full pattern:
  const eqEl = document.createElement('div');
  eqEl.style.cssText = 'position:absolute; left:50%; top:40%; transform:translate(-50%,-50%); font-size:2em; opacity:0;';
  document.getElementById('canvas-container').appendChild(eqEl);
  katex.render('E[X] = \\\\sum_{i} x_i \\\\cdot P(x_i)', eqEl, {throwOnError: false, displayMode: true});

WRONG — these all produce broken text:
  el.textContent = 'P(X=x)';
  el.innerHTML = '\\\\frac{a}{b}';
  katex.render('\\frac{a}{b}', el);  // BROKEN — single backslash!

══ RULE 2: EVERY STEP LABEL MUST HAVE ANIMATION — MANDATORY ══

Each tl.addLabel() MUST be followed by tl.to(), tl.from(), or tl.fromTo() calls. \
A label with no animation after it = a dead step where nothing changes visually.

CORRECT — visible change at each step:
  tl.addLabel('show-title');
  tl.from(titleEl, {opacity: 0, y: -30, duration: 0.5});

  tl.addLabel('show-equation', '+=0.3');
  tl.from(eqDiv, {opacity: 0, scale: 0.85, duration: 0.6});
  tl.to(eqDiv, {y: -20, duration: 0.3}, '>');

  tl.addLabel('highlight', '+=0.5');
  tl.to(highlightBox, {opacity: 1, duration: 0.3});
  tl.to(term1, {color: '#3B82F6', scale: 1.15, duration: 0.4}, '<');

WRONG — labels exist but nothing animates:
  tl.addLabel('step-1');
  tl.addLabel('step-2');  // NOTHING happened at step-1!

══ RULE 3: D3 SELECTIONS — ALWAYS CALL .node() FOR GSAP ══

D3 methods like g.append('path') return D3 SELECTION objects, not DOM elements. \
GSAP silently ignores D3 selections — all tweens on them do NOTHING.

CORRECT — call .node() to get the DOM element:
  const shade = g.append('path').attr('d', pathData).attr('fill','#3B82F6').attr('opacity',0);
  tl.to(shade.node(), {opacity: 0.5, duration: 0.5});

WRONG — GSAP silently does nothing (shade is a D3 selection, not a DOM element):
  tl.to(shade, {opacity: 0.5, duration: 0.5});

Exception: document.createElement() returns a real DOM element — no .node() needed:
  const eqDiv = document.createElement('div');
  tl.to(eqDiv, {opacity: 1, duration: 0.5});  // OK — already a DOM element

══ RULE 4: SVG PATH DATA — SET AT CREATION, ANIMATE ONLY OPACITY ══

GSAP cannot interpolate SVG path `d` strings — neither directly nor through \
attr:{d:...}. Compute the path data FIRST, set it when creating the element, \
then use opacity to reveal/hide.

CORRECT — path data set at creation, opacity animated:
  const areaData = d3.area().x(d => x(d)).y0(height).y1(d => y(fn(d)))(range);
  const shade = g.append('path').attr('d', areaData).attr('fill','#3B82F6').attr('opacity',0);
  tl.to(shade.node(), {opacity: 0.5, duration: 0.5});

WRONG — d never appears (GSAP can't tween path strings):
  const shade = g.append('path').attr('fill','#3B82F6').attr('opacity',0);
  tl.to(shade.node(), {opacity: 0.5, attr:{d: areaData}, duration: 0.5});

For multiple regions: create ALL paths upfront with their data, fade in/out as needed:
  const leftArea = d3.area()...( d3.range(-4, -1, 0.1) );
  const centerArea = d3.area()...( d3.range(-1, 1, 0.1) );
  const shadeLeft = g.append('path').attr('d', leftArea).attr('fill','#3B82F6').attr('opacity',0);
  const shadeCenter = g.append('path').attr('d', centerArea).attr('fill','#22C55E').attr('opacity',0);
  tl.to(shadeLeft.node(), {opacity: 0.5, duration: 0.5});
  tl.to(shadeLeft.node(), {opacity: 0, duration: 0.3});
  tl.to(shadeCenter.node(), {opacity: 0.5, duration: 0.5});

GSAP CAN tween: opacity, x, y, scale, rotation, width, height, color, fill, stroke.
GSAP CANNOT tween: d (path data), points (polygon), innerHTML, textContent.

══ RULE 5: DRAW VISUALS — NEVER USE EMOJI OR UNICODE SUBSTITUTES ══

Do NOT use emoji (🎲, 🪙, ⟶) or Unicode symbols for visual elements.
Draw everything with SVG, Canvas, or styled HTML divs.

Common visual elements — how to draw them:
- Die: SVG <rect rx="8"> with small <circle> pips in standard patterns
- Coin: SVG <circle> with "H"/"T" <text> label centered inside
- Number line: SVG <line> with <line> tick marks + <text> labels below
- Arrow: SVG <line> or <path> with marker-end arrowhead, animated with GSAP
- Histogram bar: SVG <rect> growing from bottom, or d3 bars
- Bell curve: d3 line generator with normal distribution function
- Mapping arrow: SVG path from source element to target element

══ RULE 6: PROGRESSIVE REVEAL — 3BLUE1BROWN STYLE ══

- Create ALL elements upfront with opacity:0
- Reveal ONE concept per step — never dump everything at once
- Color-code math terms: each gets a unique color (blue, green, purple, yellow)
- Smooth motion: elements glide in with y/x offset + opacity fade
- Clean layout: title at top 5%, main content 30-55%, annotations 70%+
- Create EVERY visual element described in each step — if the step says \
"arrows draw from Heads to 1", create visible arrow paths, not just text"""


VISUAL_GENERATION_PROMPT = """\
Write JavaScript animation code for this educational visual:

FRAME: {frame_id}
TYPE: {visual_type}
DESCRIPTION: {description}
ESTIMATED DURATION: {duration}s

{steps_section}

=== ENVIRONMENT (already loaded, do NOT import) ===

- `tl` = GSAP timeline (paused)
- `gsap` = GSAP global
- `d3` = D3.js v7 (use for charts, axes, curves, data visualization)
- `katex` = KaTeX math renderer (MUST use for ALL equations — see system rules)
- `Prism` = Prism.js syntax highlighter
- `#canvas-container` = the parent div (100vw x 100vh, dark bg #0d1117)

=== CODE STRUCTURE (follow this exact order) ===

1. const c = document.getElementById('canvas-container');
2. Create ALL elements with position:absolute and opacity:0, append to c
3. For every equation/symbol: create a div, then katex.render(latex, div, {{throwOnError: false, displayMode: true}})
4. For data plots: use d3 to create <svg> with axes, bars, curves inside c
5. Build GSAP timeline: tl.addLabel('name') then tl.from/to(el, {{...}}) for EACH step
6. NEVER call tl.play() — teacher controls playback

=== VISUAL FIDELITY (what the student sees matters) ===

- Create EVERY visual element described in each step's description
- If teacher says "arrows from Heads to 1", draw actual arrow paths, not just text
- If description says "die", draw a die shape with pips, not emoji or text "die"
- Match the narration: what the teacher says must be visible on screen at that step
- Use SVG for shapes/icons/arrows, D3 for charts, styled divs for text blocks

=== ANTI-PATTERNS (will cause rejection) ===

- textContent or innerHTML for math formulas — MUST use katex.render()
- tl.addLabel() with no tl.to/from after it — every label MUST animate something
- All elements visible immediately — start everything at opacity:0, reveal per step
- Emoji or Unicode symbols (e.g. arrow symbol) for visual elements — DRAW them with SVG/HTML
- Generating images of faces/people with code — use Unsplash photos instead:
  https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=800&q=80&fit=crop
  https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800&q=80&fit=crop
- For noise/static effects: use <canvas> with ImageData API, overlay on real image
- For zoom: use CSS transform:scale() on a wrapper, never zoom raw canvas pixels

=== STYLE ===

- Colors: BLUE #3B82F6, RED #EF4444, GREEN #22C55E, YELLOW #F59E0B, PURPLE #8B5CF6, WHITE #c9d1d9
- Easing: "power2.inOut" default, "power3.out" for emphasis
- Font sizes: title 1.6em, equations 1.8-2.2em, labels 1.1em, annotations 0.9em
- Mathematical accuracy: correct formulas, proper axis scales, real distributions
- Dark background #0d1117 is already set

=== LAYOUT — NO OVERLAP (CRITICAL) ===

Text and equations MUST NOT overlap charts, curves, or SVG visuals. Use distinct \
vertical zones so nothing collides:

- Title zone: top:2% to top:8% (position:absolute; top:3%; left:50%; transform:translateX(-50%))
- Equation/annotation zone: top:8% to top:18% (ABOVE the chart, never inside it)
- Chart/visual zone: SVG/canvas occupies the middle 20%-80% of the viewport
- Bottom label zone: top:82% to top:95% (below the chart)

WRONG — equation overlaps the curve:
  eqDiv.style.cssText = 'position:absolute; top:20%; left:50%; ...';  // lands ON the chart!

CORRECT — equation above the chart area:
  eqDiv.style.cssText = 'position:absolute; top:10%; left:50%; transform:translateX(-50%); ...';

When using D3 SVG charts, set margins that leave room for the title and equation zones:
  const margin = {{top: Math.max(h * 0.2, 140), right: 60, bottom: 80, left: 60}};

{available_images}

=== LOCKSTEP CONTRACT (NON-NEGOTIABLE) ===

The teacher plays audio per-step, then tweens to the next label. Missing or \
empty labels break the classroom.

You MUST:
  1. tl.addLabel("exact-name") for EVERY step from ANIMATION STEPS above
  2. At least one tl.to/from/fromTo AFTER each label — animate something visible
  3. Leave timeline PAUSED at t=0 — do NOT call tl.play()
  4. No separate gsap.timeline() instances — use only the shared `tl`
  5. Build all DOM upfront so seeking to any label shows correct visual state

Output ONLY raw JavaScript code. No markdown fences, no explanations.
"""


# ── Interactive frame variant ──
# Used when frame.visual_type == "interactive". The animation must wait at
# a specific label for a `userInput` postMessage from the parent (the teacher
# backend), validate the student's answer, and emit `interaction-result`
# before letting the timeline progress.

INTERACTIVE_GENERATION_PROMPT = """\
Write JavaScript animation code for an INTERACTIVE educational visual.
The student answers a question DURING the animation, and the visual reacts.

FRAME: {frame_id}
TYPE: interactive
DESCRIPTION: {description}
ESTIMATED DURATION: {duration}s

{steps_section}

INTERACTION DETAILS:
{interaction_section}

=== ENVIRONMENT (already loaded, do NOT import) ===

- `tl` = GSAP timeline (paused, use tl.addLabel(), tl.to(), tl.from(), etc.)
- `gsap` = GSAP global
- `d3` = D3.js v7
- `katex` = KaTeX renderer
- `Prism` = Prism.js syntax highlighter
- `#canvas-container` = the parent div (100vw x 100vh, dark bg #0d1117)

=== INTERACTIVE CONTRACT (must follow exactly) ===

1. Build all DOM upfront and add labels for each visual stage as usual.
2. Add a SPECIAL label called "await-input" at the moment the student must answer.
3. Inside your code, expose the answer handler on window:
     window.handleStudentAnswer = function(answer) {{ ... }}
   It receives the student's text, decides correct/wrong, and animates the
   appropriate result branch by calling tl.tweenFromTo(currentTime, targetLabel).
4. Add at least these two result labels: "after-correct" and "after-wrong".
5. After processing the answer, post a result message:
     window.parent.postMessage({{event: "interactionResult", correct: true|false}}, "*");
6. Do NOT auto-advance past "await-input" — the timeline must pause there.
   The teacher backend listens for the postMessage and resumes the timeline.

=== STYLE RULES ===

- Colors: BLUE #3B82F6 (signal), RED #EF4444 (wrong), GREEN #22C55E (correct),
  YELLOW #F59E0B (highlight), WHITE #c9d1d9 (text)
- Smooth easing: "power2.inOut" default
- Dark background #0d1117
- Pause on "await-input" — use tl.call(() => tl.pause()) at that label
- ALL math MUST use katex.render() — never textContent/innerHTML for formulas
- Every tl.addLabel() MUST have tl.to/from after it — no dead labels

=== STEP LABELS — LOCKSTEP CONTRACT ===

You MUST register every step label by string match — they are extracted by
regex on the source. Required labels: every entry from ANIMATION STEPS plus
"await-input", "after-correct", "after-wrong".

Output ONLY the raw JavaScript code. No markdown fences, no explanations.
"""


FIX_PROMPT = """\
Your previous JavaScript code for this animation had an error. Fix it.

FRAME: {frame_id}
TYPE: {visual_type}
DESCRIPTION: {description}

=== ERROR ===
{error}

=== YOUR PREVIOUS CODE (has the error above) ===
{previous_code}

=== FIX INSTRUCTIONS ===
Common issues to check:
- Unmatched braces (extra or missing {{ or }})
- Missing semicolons or commas
- Unclosed template literals or mismatched parentheses

Also verify these MANDATORY rules:
- ALL math/equations use katex.render(latex, element, {{throwOnError: false}}) — never textContent/innerHTML
- EVERY tl.addLabel() has at least one tl.to/from/fromTo after it
- Elements start at opacity:0 and animate in per step

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


def build_generation_prompt(
    frame: dict,
    available_images: dict[str, str] | None = None,
) -> str:
    """Build the prompt for generating one visual frame.

    Branches on `visual_type`: interactive frames get an extended prompt that
    enforces the question/answer postMessage contract; everything else uses
    the standard visual prompt.

    Args:
        available_images: Optional dict of step_label → base64 data URL for
            pre-generated images. Included in prompt so Gemini knows to use them.
    """
    steps = frame.get("steps", [])
    steps_section = ""
    if steps:
        step_lines = []
        for s in steps:
            label = s.get("label", s.get("step_id", "?"))
            desc = s.get("description", "")
            dur = s.get("duration_seconds", 3)
            pause = " [PAUSE]" if s.get("pause_after") else ""
            narration = s.get("narration_spoken", "") or s.get("narration", "")
            line = f"  - Step '{label}' ({dur}s{pause}): {desc}"
            if narration:
                # Truncate long narrations but keep enough for context
                narr_short = narration[:120].rstrip()
                line += f"\n    Teacher says: \"{narr_short}\""
            step_lines.append(line)
        steps_section = (
            "ANIMATION STEPS (create GSAP labels for each — "
            "the teacher narration tells you what must be visible):\n"
            + "\n".join(step_lines)
        )
    else:
        steps_section = "NO EXPLICIT STEPS — create at least 3 logical steps from the description."

    vspec = frame.get("visual_spec", {})
    description = vspec.get("description", "")
    if not description:
        description = str(vspec)

    visual_type = frame.get("visual_type", "animation")

    if visual_type == "interactive":
        interaction = frame.get("interaction") or {}
        interaction_section = (
            f"  - Question: {interaction.get('prompt', '(none)')}\n"
            f"  - Type: {interaction.get('interaction_type', 'question')}\n"
            f"  - Expected: {interaction.get('expected_response', '(any reasonable answer)')}\n"
            f"  - Hints: {', '.join(interaction.get('hints', [])) or '(none)'}"
        )
        return INTERACTIVE_GENERATION_PROMPT.format(
            frame_id=frame.get("frame_id", "unknown"),
            description=description,
            duration=frame.get("estimated_seconds", 30),
            steps_section=steps_section,
            interaction_section=interaction_section,
        )

    # Format available images for browser path
    if available_images:
        img_lines = [
            "=== PRE-GENERATED IMAGES (available in __images object) ===",
            "",
            "The template provides a global `__images` object keyed by step label.",
            "To show a pre-generated image in your animation:",
            "",
            "  const img = document.createElement('img');",
            "  img.src = __images['step-label'];",
            "  img.style.cssText = 'position:absolute; top:20%; left:50%; "
            "transform:translate(-50%,-50%); max-width:40%; border:2px solid #3B82F6; "
            "border-radius:8px; opacity:0;';",
            "  c.appendChild(img);",
            "  tl.to(img, {opacity: 1, duration: 0.8}, 'step-label');",
            "",
            "Available image labels:",
        ]
        for label in available_images:
            img_lines.append(f'  - __images["{label}"]')
        images_section = "\n".join(img_lines)
    else:
        images_section = ""

    return VISUAL_GENERATION_PROMPT.format(
        frame_id=frame.get("frame_id", "unknown"),
        visual_type=visual_type,
        description=description,
        duration=frame.get("estimated_seconds", 30),
        steps_section=steps_section,
        available_images=images_section,
    )


# ═══════════════════════════════════════════════════════════
# Manim prompts — for frames routed to Manim renderer
# ═══════════════════════════════════════════════════════════

MANIM_GENERATION_SYSTEM = """\
You are an expert Manim Community Edition animator creating 3Blue1Brown-quality \
mathematical visualizations. You write Python code using Manim CE v0.20.

The code must define a class `AnimationScene` that extends `Scene` (or `ThreeDScene` \
for 3D visuals). Return the Python in the `code` field of your JSON response — \
raw Python only, no markdown fences, no commentary.

=== CODE FORMATTING (CRITICAL) ===
Format the Python code with REAL newlines and 4-space indentation inside the \
JSON `code` string. In JSON, a newline is the escape sequence \\n — use it \
between every statement.

- ONE statement per line. NEVER chain statements with semicolons.
- NEVER put `class X:` and `def y():` on the same line.
- NEVER put `self.play(...)` calls on the same line as other statements.
- Imports each on their own line: `from manim import *` then `\\n` then `import numpy as np`.
- Use 4-space indentation for class body, 8-space for `construct` body.

If you collapse code onto one line with semicolons, Python will reject it with \
a SyntaxError and the frame will fail. Always use real newlines.

=== QUALITY FLOOR (MANDATORY — skeleton code will be REJECTED) ===

Your code MUST meet ALL of these minimums:
- At least 2 self.play() calls PER step — each step must have visible animation
- At least 3 distinct mobjects per step — never just one object on screen
- EVERY step MUST have an annotation: MathTex formula, Text label, or both
- Axes/number lines MUST be drawn whenever data is plotted — never floating dots
- Objects MUST look like what they represent (see VISUAL RECIPES below)

WRONG — skeleton code (will be rejected):
  die = Cube(color=BLUE)  # Just a blue box, not a die
  self.play(Create(die))
  self.wait(2)

CORRECT — rich scene with detail:
  die = self.build_die(5)  # Helper builds a die with pips
  number_line = NumberLine(x_range=[1, 6, 1], length=8)
  label = MathTex(r"X = 5", font_size=36, color=YELLOW)
  self.play(Create(die), Create(number_line), run_time=1.5)
  self.play(Write(label), run_time=0.8)

=== VISUAL RECIPES (use these — do NOT invent worse alternatives) ===

**Die with pips (ALWAYS use this, never plain Cube):**
  def build_die(self, value, color=BLUE):
      face = Square(side_length=1.2, color=color, fill_opacity=0.9, stroke_color=WHITE)
      pip_positions = {
          1: [ORIGIN], 2: [UL*0.3, DR*0.3], 3: [UL*0.3, ORIGIN, DR*0.3],
          4: [UL*0.3, UR*0.3, DL*0.3, DR*0.3],
          5: [UL*0.3, UR*0.3, ORIGIN, DL*0.3, DR*0.3],
          6: [UL*0.3, UR*0.3, LEFT*0.3, RIGHT*0.3, DL*0.3, DR*0.3],
      }
      pips = VGroup(*[Dot(p, color=WHITE, radius=0.08) for p in pip_positions.get(value, [])])
      return VGroup(face, pips)

**Histogram from data (ALWAYS include axes):**
  axes = Axes(x_range=[0.5, 6.5, 1], y_range=[0, max_count+1, 1], x_length=8, y_length=4,
              axis_config={"include_numbers": True, "font_size": 20})
  bars = VGroup(*[Rectangle(width=0.7, height=count*0.5, color=BLUE, fill_opacity=0.7
              ).move_to(axes.c2p(val, count/2)) for val, count in data])

**Number line with labeled dots:**
  nl = NumberLine(x_range=[1, 6, 1], length=8, include_numbers=True)
  dot = Dot(nl.n2p(value), color=YELLOW, radius=0.12)
  label = MathTex(str(value), font_size=24).next_to(dot, UP, buff=0.15)

**3D point cloud with axes (ALWAYS include ThreeDAxes):**
  axes = ThreeDAxes(x_range=[-3,3,1], y_range=[-3,3,1], z_range=[-3,3,1], x_length=6, y_length=6, z_length=6)
  points = VGroup(*[Dot3D(point=np.random.normal(0,1,3), color=YELLOW, radius=0.06) for _ in range(25)])

**Generated image (when paths provided in prompt):**
  img = ImageMobject(r"C:/path/to/image.jpg")  # Use EXACT path from prompt
  img.scale_to_fit_width(4)                     # Scale to fit scene
  img.move_to(RIGHT * 3)
  border = SurroundingRectangle(img, color=WHITE, buff=0.05)
  label = Text("Generated Output", font_size=20).next_to(img, DOWN)
  self.play(FadeIn(img), Create(border), Write(label))

**Gaussian bell curve:**
  axes = Axes(x_range=[-4,4,1], y_range=[0,0.45,0.1], x_length=8, y_length=4,
              axis_config={"include_numbers": True, "font_size": 18})
  curve = axes.plot(lambda x: np.exp(-x**2/2)/np.sqrt(2*np.pi), color=BLUE)
  area = axes.get_area(curve, x_range=[-1,1], color=GREEN, opacity=0.4)
  formula = MathTex(r"f(x) = \\frac{1}{\\sqrt{2\\pi}} e^{-x^2/2}", font_size=28).to_edge(UP)

=== 2D → 3D TRANSITIONS (common pitfall) ===

When a scene starts with 2D content and later switches to 3D:
1. FadeOut ALL 2D mobjects BEFORE calling set_camera_orientation
2. Create fresh 3D mobjects after the camera change — do NOT reuse 2D ones
3. For text overlays in 3D scenes, use add_fixed_in_frame_mobjects so text stays \
   facing the camera (otherwise text rotates with the 3D scene and becomes unreadable)

CORRECT:
  self.play(FadeOut(axes2d), FadeOut(bars))  # Remove 2D content
  self.set_camera_orientation(phi=75*DEGREES, theta=-45*DEGREES)
  axes3d = ThreeDAxes(...)                   # Fresh 3D axes
  self.play(Create(axes3d), run_time=1)
  question = Text("...", font_size=32)
  self.add_fixed_in_frame_mobjects(question)  # Stays facing camera!
  self.play(Write(question))

WRONG:
  self.set_camera_orientation(phi=75*DEGREES)  # 2D bars still on screen — now distorted!
  question = Text("...")
  self.play(Write(question))  # Text rotates with 3D camera — unreadable!

=== COMMON MISTAKES (these WILL crash or look broken) ===

**NEVER use placeholder rectangles for images:**
  WRONG: placeholder = Square(side_length=2, color=GREEN, fill_opacity=0.7)  # Meaningless green box
  If pre-generated images are available (listed below the steps), use ImageMobject:
    img = ImageMobject(r"path/provided/in/prompt.jpg").scale_to_fit_width(4)
    self.play(FadeIn(img))
  If NO images are available, use Arrow + Text label to convey the concept — \
  never a blank colored rectangle.

**NEVER shift off-screen after to_edge:**
  WRONG: nl.to_edge(DOWN).shift(DOWN*0.5)  # Pushed below visible frame
  CORRECT: nl.to_edge(DOWN)                # Already at bottom edge
  CORRECT: nl.shift(DOWN*1.5)              # Shift without to_edge if you want lower

**NEVER use custom rate_func lambdas:**
  WRONG: rate_func=lambda t: smooth(t) if t < 0.8 else there_and_back(t)  # Breaks at t>0.8
  CORRECT: rate_func=smooth   # Use built-in rate functions only
  Available: smooth, linear, rush_into, rush_from, there_and_back, double_smooth

**NEVER chain .shift().move_to() on animate — move_to overrides shift:**
  WRONG: die.animate.shift(RIGHT*4).move_to(UP*0.5)  # shift is discarded
  CORRECT: die.animate.move_to(RIGHT*4 + UP*0.5)     # Single final position

**Axes uses c2p(), NumberLine uses n2p() — do NOT mix them up:**
  WRONG: axes.n2p(4)           # Axes has no n2p method — crashes
  CORRECT: axes.c2p(4, 0)     # Axes: c2p(x, y)
  CORRECT: number_line.n2p(4)  # NumberLine: n2p(x)

=== PERFORMANCE BUDGET (HARD LIMITS — verified by benchmark) ===

- Total scene duration: <= 25 seconds (sum all run_times + self.wait() calls)
- Total self.play() calls: <= 15
- Max Dot3D / Sphere / 3D particles in a VGroup: <= 25
- Max `begin_ambient_camera_rotation` duration: <= 3 seconds
- Max `Surface` resolution: (32, 32)
- Max individual run_time value: <= 2 seconds

3D scenes are ENCOURAGED — ThreeDScene, ThreeDAxes, Surface, Dot3D, Arrow3D all welcome. \
Just keep particle counts and durations within budget."""


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
4. Keep total scene ≤ 25 seconds. Each `self.wait()` ≤ 2 seconds. NEVER use `self.wait(8)` or longer
5. No network calls. Only external files allowed: pre-generated images listed below

{available_images}

=== STEP TIMING (compressed for rendering — NOT voiceover duration) ===

These timings are ALREADY compressed for Manim render performance. Do NOT \
inflate them. Each `self.wait()` call MUST be ≤ 2 seconds. If a step says \
"~3s", that means ~1s of animation + ~2s wait total — NOT a 3s wait on top \
of animations. The total scene MUST stay under 25 seconds.

{step_timing}

=== STYLE RULES ===

- Background: self.camera.background_color = "#0d1117"
- Colors: BLUE (signal), RED (noise/error), GREEN (output), YELLOW (highlight), \
PURPLE (secondary), WHITE (text/labels)
- Custom colors via ManimColor("#hex")
- Clean typography: Text(font_size=36) for titles, Text(font_size=24) for labels
- Mathematical accuracy: correct Gaussian PDF, proper axis scales, real formulas
- Smooth animations: run_time=1-2 for most transitions

=== VISUAL FIDELITY (CRITICAL — each step must have MULTIPLE visual elements) ===

EVERY step in the animation MUST contain:
1. A primary visual (the thing being shown — shape, chart, cloud)
2. A reference frame (axes, number line, grid — never floating objects in void)
3. An annotation (MathTex formula or Text label explaining what's on screen)
4. At least 2 self.play() calls (create + annotate, or transform + highlight)

WRONG — bare primitives, no context:
  die = Cube(color=BLUE)   # Unrecognizable blue box
  self.play(Create(die))   # One animation, no annotation, no reference frame

CORRECT — rich, annotated scene:
  die = self.build_die(3)                   # Recognizable die with pips
  nl = NumberLine(x_range=[1,6,1], length=8, include_numbers=True)
  nl.to_edge(DOWN)
  dot = Dot(nl.n2p(3), color=YELLOW)
  label = MathTex(r"X = 3", font_size=28, color=YELLOW).next_to(dot, UP)
  self.play(FadeIn(die), Create(nl), run_time=1)
  self.play(die.animate.next_to(nl.n2p(3), UP, buff=0.5), run_time=0.8)
  self.play(Create(dot), Write(label), run_time=0.8)

Visual element rules:
- Die: Square face with pip Dots in standard patterns (see system prompt recipes)
- Coin: Circle with "H"/"T" Text label centered inside
- Data: ALWAYS on axes or number line, never floating in space
- 3D: ALWAYS include ThreeDAxes, set camera to show 2-3 faces

=== LAYOUT RULES ===

- Title: to_edge(UP), font_size=28-36
- Main visual: ORIGIN (center), largest element
- Labels/annotations: to_corner(DL) or to_edge(DOWN), font_size=16-20
- Do NOT overlap text with the main visual
- Axes: x_length=6-8, y_length=4-5 for good proportions
- Buff: minimum 0.3 between elements

=== CRITICAL RULES ===

- Use MathTex() for ALL mathematical formulas (LaTeX IS installed)
- Use Text() for plain labels (NOT MathTex for non-math text)
- For 3D scenes: use ThreeDScene, ThreeDAxes, Surface
- For 2D plots: use Axes with axes.plot()
- Progressive animation: reveal elements one at a time, not all at once
- EVERY step must add something to the scene — never an empty step
- End with self.wait(2) so the final state is visible
- Define helper methods (build_die, build_histogram, etc.) inside the class

Return the Python in the `code` field of your JSON response. Use real newlines \
(\\n in JSON) — ONE statement per line, 4-space indentation, never chain with \
semicolons.
"""


MANIM_FIX_PROMPT = """\
Your previous Manim Python code failed. Produce a corrected version.

FRAME: {frame_id}
TYPE: {visual_type}
DESCRIPTION: {description}

=== ERROR FROM PREVIOUS ATTEMPT ===
{error}

=== YOUR PREVIOUS CODE (do NOT just re-submit this) ===
{previous_code}

=== HOW TO INTERPRET THE ERROR ===

**If the error is "Render timed out after Ns":**
The code was syntactically correct but Manim could not finish rendering in time. \
DO NOT change the code structure or collapse it onto fewer lines — that will \
NOT help. Instead, AGGRESSIVELY SIMPLIFY the scene to fit the HARD budget:

  - Total scene duration: ≤ 25 seconds (cut steps, cut self.wait() times)
  - Total self.play() calls: ≤ 15 (drop whole animation steps if needed)
  - Dot3D / 3D particle count: ≤ 25 (e.g. 60 → 20, 200 → 25)
  - Ambient camera rotation: ≤ 3 seconds (e.g. 10s → 3s, or remove entirely)
  - Individual run_time: ≤ 2 seconds (3s → 1s, 2s → 1s)
  - Surface resolution: (32, 32) max (48 → 32)
  - Max active mobjects on screen: ≤ 40

Keep the 3D look — ThreeDScene, Dot3D, set_camera_orientation, Surface all \
stay. Just reduce the quantities. A 60-particle cloud with 10s rotation takes \
over an hour to render; the same scene with 20 particles and 3s rotation \
renders in 3 minutes — that is the order of magnitude you must cut by.

Also cut gratuitous content: drop any "tease" / filler / decorative step that \
does not teach a concept. Every second of scene duration is a minute of render \
time at 1080p60.

**If the error is "SyntaxError: cannot use name as import target" or similar:**
You previously returned the code as a single line with semicolons. Python cannot \
parse that. Rewrite using REAL NEWLINES (\\n in JSON) with one statement per \
line and 4-space indentation. NEVER put `class X:` and `def y():` on the same \
line. NEVER chain statements with `;`.

**If the error is "LaTeX compilation error":**
Check MathTex syntax, use Text() for non-math strings, escape backslashes.

**If the error is "'Scene' has no attribute 'set_camera_orientation'":**
Use `class AnimationScene(ThreeDScene):` not `Scene`.

**If the error is "ModuleNotFoundError":**
Only import from `manim` and `numpy`. No other modules.

**If the error is "name 'xxx' is not defined":**
Define all mobjects before using them.

=== FORMATTING (CRITICAL — PREVIOUS ATTEMPT VIOLATED THIS) ===
Return the Python in the `code` field of your JSON response with REAL newlines:
- ONE statement per line
- 4-space indentation for class body
- 8-space indentation for construct() body
- NEVER use semicolons to chain statements
- NEVER put `def` or `class` on the same line as another statement

=== INSTRUCTIONS ===
Return the COMPLETE corrected Python code in the `code` field of your JSON \
response. Full working code — not a diff, not a patch. Use real newlines.
"""


def build_manim_generation_prompt(
    frame: dict,
    available_images: dict[str, str] | None = None,
) -> str:
    """Build the prompt for generating a Manim animation.

    Args:
        frame: The visual frame dict from the course planner.
        available_images: Optional mapping of step_label → local image path
            for pre-generated images that Gemini can use via ImageMobject.
    """
    steps = frame.get("steps", [])
    steps_section = ""
    step_timing = ""

    if steps:
        step_lines = []
        timing_lines = []
        # The storyboard's duration_seconds are voiceover timings (how long
        # the teacher talks).  We MUST compress them for Manim render time.
        # Cap each step to MAX_STEP_S and total to MAX_SCENE_S.
        MAX_STEP_S = 5
        MAX_SCENE_S = 25
        raw_durations = [s.get("duration_seconds", 3) for s in steps]
        raw_total = sum(raw_durations)
        if raw_total > MAX_SCENE_S:
            # Scale proportionally then clamp
            scale = MAX_SCENE_S / raw_total
            capped = [max(1, min(MAX_STEP_S, round(d * scale))) for d in raw_durations]
        else:
            capped = [min(MAX_STEP_S, d) for d in raw_durations]

        for s, dur in zip(steps, capped):
            label = s.get("label", s.get("step_id", "?"))
            step_lines.append(
                f"  - Step '{label}': "
                f"{s.get('description', '')} ({dur}s)"
                f"{' [PAUSE]' if s.get('pause_after') else ''}"
            )
            timing_lines.append(
                f"  - '{label}': ~{dur}s"
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

    # Format available images section
    if available_images:
        img_lines = ["=== PRE-GENERATED IMAGES (use these with ImageMobject) ===", ""]
        for label, path in available_images.items():
            # Use raw string paths (Windows backslashes)
            img_lines.append(f'  Step "{label}": r"{path}"')
        img_lines.append("")
        img_lines.append(
            "Use ImageMobject(r\"path\") with the EXACT path above. "
            "Scale with .scale_to_fit_width(3-4). Add a SurroundingRectangle border."
        )
        images_section = "\n".join(img_lines)
    else:
        images_section = ""

    return MANIM_GENERATION_PROMPT.format(
        frame_id=frame.get("frame_id", "unknown"),
        visual_type=frame.get("visual_type", "animation"),
        description=description,
        duration=frame.get("estimated_seconds", 30),
        steps_section=steps_section,
        step_timing=step_timing,
        manim_reference=MANIM_API_REFERENCE,
        manim_3d_reference=manim_3d,
        available_images=images_section,
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
