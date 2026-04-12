"""f01 budgeted variant — same 3D concept, but with performance budget:
- 20 Dot3D (was 60)
- 3s ambient rotation (was 10)
- ~30s total scene (was 76)
- 3D preserved (ThreeDScene, camera move, 3D dots)
"""
from manim import *
import numpy as np


class AnimationScene(ThreeDScene):
    def construct(self):
        self.camera.background_color = "#0d1117"

        # Step 1: Single Die (short)
        die = Cube(side_length=1, fill_opacity=0.8, color=BLUE)
        self.play(Create(die), run_time=1)
        self.play(Rotate(die, angle=PI, axis=RIGHT), run_time=1)
        number_line = NumberLine(x_range=[0, 7, 1], length=8, include_numbers=True)
        number_line.to_edge(DOWN)
        self.play(Create(number_line), run_time=1)
        dot = Dot(number_line.n2p(4), color=YELLOW)
        self.play(FadeIn(dot), run_time=0.5)
        self.wait(1)

        # Step 2: Many Dice (fewer, faster)
        self.play(FadeOut(die), FadeOut(dot))
        dots = VGroup(*[Dot(number_line.n2p(np.random.randint(1, 7)), color=BLUE_B) for _ in range(15)])
        self.play(LaggedStart(*[FadeIn(d) for d in dots], lag_ratio=0.1), run_time=2)
        self.wait(1)

        # Step 3: Higher Dimensions (20 particles, 3s rotation)
        self.play(FadeOut(dots), FadeOut(number_line))
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
        axes = ThreeDAxes(x_range=[-3, 3], y_range=[-3, 3], z_range=[-3, 3], x_length=5, y_length=5, z_length=5)
        self.play(Create(axes), run_time=1)
        points = VGroup(*[Dot3D(point=np.random.normal(0, 1, 3), color=PURPLE, radius=0.05) for _ in range(20)])
        self.play(FadeIn(points), run_time=1)
        self.begin_ambient_camera_rotation(rate=0.3)
        self.wait(3)
        self.stop_ambient_camera_rotation()

        # Step 4: Question
        self.move_camera(phi=0, theta=-90 * DEGREES, run_time=1)
        text = Text("What language describes this?", font_size=36, color=WHITE)
        text.to_edge(UP)
        self.play(Write(text), run_time=1)
        self.wait(2)
