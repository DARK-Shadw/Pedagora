"""f01 benchmark — the exact code that timed out at 600s."""
from manim import *
import numpy as np


class AnimationScene(ThreeDScene):
    def construct(self):
        self.camera.background_color = "#0d1117"

        # Step 1: Single Die
        die = Cube(side_length=1, fill_opacity=0.8, color=BLUE)
        self.play(Create(die), run_time=2)
        self.play(Rotate(die, angle=PI, axis=RIGHT), run_time=2)
        number_line = NumberLine(x_range=[0, 7, 1], length=8, include_numbers=True)
        number_line.to_edge(DOWN)
        self.play(Create(number_line), run_time=2)
        dot = Dot(number_line.n2p(4), color=YELLOW)
        self.play(FadeIn(dot), run_time=2)
        self.wait(4)

        # Step 2: Many Dice
        self.play(FadeOut(die), FadeOut(dot))
        dots = VGroup(*[Dot(number_line.n2p(np.random.randint(1, 7)), color=BLUE_B) for _ in range(40)])
        self.play(LaggedStart(*[FadeIn(d) for d in dots], lag_ratio=0.1), run_time=6)
        self.wait(8)

        # Step 3: Higher Dimensions
        self.play(FadeOut(dots), FadeOut(number_line))
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
        axes = ThreeDAxes(x_range=[-3, 3], y_range=[-3, 3], z_range=[-3, 3], x_length=5, y_length=5, z_length=5)
        self.play(Create(axes), run_time=2)
        points = VGroup(*[Dot3D(point=np.random.normal(0, 1, 3), color=PURPLE, radius=0.05) for _ in range(60)])
        self.play(FadeIn(points), run_time=4)
        self.begin_ambient_camera_rotation(rate=0.2)
        self.wait(10)

        # Step 4: Question Posed
        self.stop_ambient_camera_rotation()
        self.move_camera(phi=0, theta=-90 * DEGREES, run_time=2)
        text = Text("What language describes this?", font_size=36, color=WHITE)
        text.to_edge(UP)
        self.play(Write(text), run_time=3)
        for _ in range(3):
            self.play(points.animate.scale(1.1), run_time=1)
            self.play(points.animate.scale(1 / 1.1), run_time=1)
        self.wait(8)

        # Step 5: Connection Tease
        sample = points[0].copy()
        self.play(sample.animate.move_to(RIGHT * 3), run_time=2)
        image_placeholder = Square(side_length=2, color=GREEN, fill_opacity=0.5).next_to(sample, RIGHT)
        self.play(Create(image_placeholder), run_time=2)
        self.wait(10)
