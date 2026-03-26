"""Prompts for the Animation Agent's Manim code generation."""

ANIMATION_CODEGEN_PROMPT = """\
You are a Manim Community Edition (ManimCE) expert. Write a complete, \
self-contained Python scene that produces the animation described below.

## Animation Spec
Type: {animation_type}
Description: {description}
Duration: ~{duration_seconds} seconds
Parameters: {parameters}

## Prepared Data Files (REAL DATA — use these file paths)
{prepared_data}

## Research Code (concept implementation)
```python
{reference_code}
```

## Research Formula
LaTeX: {reference_formula_latex}
Variables: {reference_formula_vars}
Values: {reference_values}

## Reference Manim Code (from web search)
{search_results}

## Manim API Reference
{manim_reference}

## Output Rules
- Output ONLY valid Python code — no explanations, no markdown, no comments outside code
- Start with `from manim import *` and `import numpy as np`
- Single class named exactly `AnimationScene` extending `Scene`
- The `construct(self)` method contains all animation logic
- Must be SELF-CONTAINED — no external file dependencies
- For images/data: generate synthetic data using numpy (e.g., np.random.rand(64,64,3))
- Target ~{duration_seconds} seconds total animation length
- Use self.wait(1) for pauses between major visual steps

## Style Rules
- Use colors meaningfully: BLUE for signal/input, RED for noise/error, \
GREEN for output/results, YELLOW for highlights, WHITE for text
- LaTeX IS installed. You CAN use MathTex for beautiful formula rendering. \
Use MathTex for equations: `MathTex(r"E = mc^2")`. Use Text() for plain labels. \
Use DecimalNumber for animated counters. \
For equation_reveal, MathTex is PREFERRED over Text() for proper math rendering.
- For updating numbers: use DecimalNumber or create new Text and Transform.
- Build animations progressively — show one thing at a time, not everything at once
- READ THE DESCRIPTION CAREFULLY. If it says "reverse process" or "denoising", \
start from NOISE and end with a CLEAR image. If it says "forward process" or \
"adding noise", start CLEAR and end with NOISE. Do NOT mix these up.

## Layout Rules (CRITICAL for visual quality)

Standard layout zones — NEVER place elements outside their zone:
```
+--------------------------------------------------+
| TITLE (font_size=32)              .to_edge(UP)    |  <- zone 1: title
|                                                    |
|                                                    |
|         MAIN VISUAL (image/graph)                  |  <- zone 2: center
|         .move_to(ORIGIN)                           |
|         .set_height(3.5)                           |
|                                                    |
|                                                    |
| LABELS (font_size=18)    .to_corner(DL)            |  <- zone 3: info
| beta_t = 0.001           or .to_edge(LEFT)         |
| SNR = 42.5               + shift(DOWN * 0.5)       |
|                                                    |
| [====TIMELINE====]       .to_edge(DOWN)            |  <- zone 4: timeline
+--------------------------------------------------+
```

HARD RULES:
- ONLY the main visual (image/graph) goes at ORIGIN/center
- Text labels NEVER at ORIGIN or center — always to_edge() or to_corner()
- Title ALWAYS at to_edge(UP) with font_size=28-36
- Parameter labels (beta_t, SNR, step count) at to_corner(DL) with font_size=16-20
- Timeline/progress bars at to_edge(DOWN)
- Image/graph height: 3.5 units MAX (leaves room for title + labels)
- Use buff=0.3 minimum between all elements
- For ImageMobject: use .set_resampling_algorithm(RESAMPLING_ALGORITHMS["nearest"]) \
to keep pixel art crisp (prevents blurring when upscaled)
- When updating labels (new values each step), create new Text at SAME position \
and Transform — do NOT move them to center
- Add labels and titles so the animation is self-explanatory
- Use smooth pacing: 0.5-1s for simple animations, 1-2s for transforms, \
1-2s wait between steps

## Animation Type Guidelines

**data_animation** (MOST IMPORTANT — must show visible data transforming):
- Use ImageMobject to load the PREPARED DATA FILES listed in Data Requirements.
- The data files are real images (MNIST digits, CIFAR samples, etc.) already \
downloaded and saved to disk. Just load them by file path.
- Pattern for showing an image with noise progression:
```python
# Load the real image (path from Prepared Data Files section)
img = ImageMobject("path/from/prepared/data.png")
img.set_height(5)  # Make it BIG
img.move_to(ORIGIN)
self.play(FadeIn(img))
self.wait(1)

# Show noisy versions (paths from Prepared Data Files section)
noisy_paths = ["path/to/noise_0.png", "path/to/noise_1.png"]  # from prepared data
for i, noisy_path in enumerate(noisy_paths):
    noisy_img = ImageMobject(noisy_path)
    noisy_img.set_height(5).move_to(ORIGIN)
    label = Text(f"t={{i*125}}", font_size=24).to_edge(DOWN)
    self.play(FadeIn(label), Transform(img, noisy_img), run_time=0.8)
    self.wait(0.5)
    self.play(FadeOut(label), run_time=0.2)
```
- The image MUST be the largest element on screen (set_height(5))
- Labels/text go to edges, NOT in the center
- ALWAYS use the file paths from the "Prepared Data Files" section

**equation_reveal**: Use MathTex for beautiful LaTeX rendering. \
Show full formula greyed out, then highlight parts one by one. Example:
```python
# Show full formula greyed out
formula = MathTex(
    r"q(x_t | x_{{t-1}})", r"=", r"\mathcal{{N}}(",
    r"\sqrt{{1-\beta_t}} x_{{t-1}}", r",", r"\beta_t I", r")"
)
formula.set_color(GRAY)
formula.move_to(ORIGIN)
self.play(Write(formula))
self.wait(1)

# Highlight signal term in blue
self.play(formula[3].animate.set_color(BLUE))
label1 = Text("signal preservation", font_size=18, color=BLUE).next_to(formula, DOWN)
self.play(FadeIn(label1))
self.wait(1)
self.play(FadeOut(label1))

# Highlight noise term in red
self.play(formula[5].animate.set_color(RED))
label2 = Text("noise injection", font_size=18, color=RED).next_to(formula, DOWN)
self.play(FadeIn(label2))
self.wait(1)
```
KEY: Split the formula into separate MathTex arguments so you can color each part \
independently by index (formula[0], formula[1], etc.).

**graph_plot**: Use Axes() with proper ranges, labels. Plot functions with \
axes.plot(). Animate with ValueTracker for smooth parameter changes. \
The graph should be LARGE (take up most of the screen).

**diagram_build**: Build architecture/structure progressively using Rectangles, \
Arrows, Text labels. Show data flow with animated arrows.

**comparison**: Split screen with VGroup — left and right panels with labels. \
Show same input producing different outputs side by side.

**process_flow**: Sequential steps with arrows between them. Animate each \
step appearing one by one, highlight the current step.

**code_walkthrough**: Show code as Text lines. Highlight current line with \
SurroundingRectangle. Step through line by line.
"""

ANIMATION_FIX_PROMPT = """\
The Manim code below failed to render. Fix the error and return the \
corrected COMPLETE Python code.

## Error
```
{error}
```

## Failed Code
```python
{code}
```

## Rules
- Return ONLY the corrected Python code
- Keep the class name as `AnimationScene`
- Keep `from manim import *` and `import numpy as np`
- Fix the specific error — do not rewrite from scratch unless necessary
- Use Text() instead of MathTex() if the error is LaTeX-related
"""
