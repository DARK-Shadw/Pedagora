"""Test arrange_in_grid with OpenGL renderer — regression test for Vector3D bug."""
from manim import *


class AnimationScene(ThreeDScene):
    def construct(self):
        self.camera.background_color = "#0d1117"
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
        cubes = VGroup(*[Cube(side_length=0.3, color=BLUE, fill_opacity=0.7) for _ in range(16)])
        cubes.arrange_in_grid(rows=4, cols=4, buff=0.2)
        self.play(FadeIn(cubes), run_time=1)
        self.wait(1)
