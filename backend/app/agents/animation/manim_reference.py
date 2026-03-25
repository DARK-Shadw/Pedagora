"""Curated Manim Community Edition API reference for LLM code generation.

This is NOT templates — it's API documentation so the LLM knows what's available.
Included in every animation codegen prompt.
"""

MANIM_API_REFERENCE = """\
## Manim Community Edition API Reference

### Imports
```python
from manim import *
import numpy as np
```

### Text & Formulas
```python
# IMPORTANT: LaTeX is NOT installed. Do NOT use MathTex, Tex, or DecimalNumber.
# Use Text() for everything. Use ONLY ASCII — no Unicode subscripts.

text = Text("Hello World", font_size=36, color=WHITE)
text = Text("Bold text", weight=BOLD)

# Formulas using Text (ASCII only, no Unicode subscripts):
formula = Text("q(x_t | x_t-1) = N(sqrt(1-beta_t) * x_t-1, beta_t * I)", font_size=24)
formula = Text("x_t = sqrt(alpha_bar_t) * x_0 + sqrt(1-alpha_bar_t) * eps", font_size=24)
formula = Text("L = E[ ||eps - eps_theta(x_t, t)||^2 ]", font_size=24)

# Color parts of text (by character index):
formula[0:3].set_color(BLUE)

# Updating numbers (no DecimalNumber — use Transform):
old_text = Text(f"beta = 0.0010", font_size=24)
new_text = Text(f"beta = 0.0100", font_size=24).move_to(old_text)
self.play(Transform(old_text, new_text))
```

### Shapes & Objects
```python
square = Square(side_length=2, color=BLUE, fill_opacity=0.5)
circle = Circle(radius=1, color=RED)
rect = Rectangle(width=4, height=2, color=GREEN)
dot = Dot(point=ORIGIN, color=YELLOW)
arrow = Arrow(start=LEFT * 2, end=RIGHT * 2, color=WHITE)
line = Line(start=UP, end=DOWN, color=GRAY)
brace = Brace(obj, direction=DOWN)

# Grouping
group = VGroup(obj1, obj2, obj3)
group.arrange(RIGHT, buff=0.5)  # Horizontal layout
group.arrange(DOWN, buff=0.3)   # Vertical layout
group.arrange_in_grid(rows=4, cols=4, buff=0.1)  # Grid layout
```

### Axes & Plots
```python
axes = Axes(
    x_range=[0, 10, 1],  # [min, max, step]
    y_range=[0, 1, 0.2],
    x_length=6, y_length=4,
    axis_config={"include_numbers": True, "font_size": 20},
)
x_label = axes.get_x_axis_label("t")
y_label = axes.get_y_axis_label("\\\\beta_t")

graph = axes.plot(lambda x: x**2 / 100, color=BLUE)
area = axes.get_area(graph, x_range=[2, 8], color=BLUE, opacity=0.3)
dot = Dot(axes.c2p(5, 0.25), color=RED)  # coords to point

# Multiple graphs
graph1 = axes.plot(lambda x: np.sin(x), color=BLUE)
graph2 = axes.plot(lambda x: np.cos(x), color=RED)
```

### Images (load from prepared data files)
```python
# Load a real image from file path (provided by data preparation step)
img = ImageMobject("/path/to/mnist_3.png")
img.set_height(4)  # Good size — leaves room for title and labels
img.set_resampling_algorithm(RESAMPLING_ALGORITHMS["nearest"])  # Keep pixels crisp
img.move_to(ORIGIN)
self.play(FadeIn(img))

# Load noisy version and transform
noisy_img = ImageMobject("/path/to/mnist_3_noise_3.png")
noisy_img.set_height(5).move_to(ORIGIN)
self.play(Transform(img, noisy_img), run_time=1)

# Load from numpy array (uint8, shape HxWx3 for RGB or HxW for grayscale)
arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
img = ImageMobject(arr)
img.set_height(5)
```

### Animations
```python
# Create / Write
self.play(Create(obj), run_time=1)       # Draw shape
self.play(Write(text), run_time=2)       # Write text/formula
self.play(FadeIn(obj), run_time=0.5)     # Fade in
self.play(FadeOut(obj), run_time=0.5)    # Fade out

# Transform
self.play(Transform(obj1, obj2))          # Morph obj1 into obj2
self.play(ReplacementTransform(obj1, obj2))  # Replace obj1 with obj2

# Animate properties
self.play(obj.animate.shift(RIGHT * 2))   # Move
self.play(obj.animate.scale(1.5))         # Scale
self.play(obj.animate.set_color(RED))     # Change color
self.play(obj.animate.set_opacity(0.5))   # Change opacity
self.play(obj.animate.rotate(PI / 4))     # Rotate

# Multiple simultaneous animations
self.play(obj1.animate.shift(UP), obj2.animate.shift(DOWN))

# Timing
self.wait(1)  # Pause for 1 second
self.play(Write(text), run_time=2)  # 2-second animation
```

### Layout & Positioning
```python
obj.to_edge(UP)          # Top of screen
obj.to_edge(DOWN)        # Bottom
obj.to_edge(LEFT)        # Left
obj.to_corner(UL)        # Upper-left corner
obj.move_to(ORIGIN)      # Center
obj.move_to(RIGHT * 3 + UP * 2)  # Specific position
obj.next_to(other, RIGHT, buff=0.3)  # Next to another object

# Screen coordinates
ORIGIN = [0, 0, 0]
UP = [0, 1, 0]; DOWN = [0, -1, 0]
LEFT = [-1, 0, 0]; RIGHT = [1, 0, 0]
UL = UP + LEFT; UR = UP + RIGHT
DL = DOWN + LEFT; DR = DOWN + RIGHT
```

### Colors
```python
# Main colors
RED, BLUE, GREEN, YELLOW, WHITE, GRAY, PURPLE, ORANGE, PINK, TEAL

# Shades (A=lightest, E=darkest)
BLUE_A, BLUE_B, BLUE_C, BLUE_D, BLUE_E
RED_A, RED_B, RED_C, RED_D, RED_E

# Custom color
color = ManimColor("#1a73e8")

# Color conversion
rgb_to_color([0.5, 0.5, 0.5])  # Gray from RGB values
```

### Scene Structure
```python
class AnimationScene(Scene):
    def construct(self):
        # All animation code goes here
        # Objects exist only within construct()
        pass
```

### Common Patterns

**Progressive reveal:**
```python
items = VGroup(*[Text(f"Step {i+1}") for i in range(4)])
items.arrange(DOWN, buff=0.3)
for item in items:
    self.play(FadeIn(item, shift=RIGHT * 0.5), run_time=0.5)
    self.wait(0.3)
```

**Split screen comparison:**
```python
left_group = VGroup(Text("Before"), obj1).arrange(DOWN)
right_group = VGroup(Text("After"), obj2).arrange(DOWN)
VGroup(left_group, right_group).arrange(RIGHT, buff=2)
divider = Line(UP * 3, DOWN * 3, color=GRAY)
```

**Highlight with surrounding rectangle:**
```python
highlight = SurroundingRectangle(obj, color=YELLOW, buff=0.1)
self.play(Create(highlight))
```

**Number tracker with graph:**
```python
tracker = ValueTracker(0)
dot = always_redraw(lambda: Dot(axes.c2p(tracker.get_value(), func(tracker.get_value()))))
self.play(tracker.animate.set_value(10), run_time=3)
```
"""
