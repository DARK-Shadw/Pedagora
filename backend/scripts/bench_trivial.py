"""Trivial 1-animation scene to test if OpenGL renderer works at all."""
from manim import *


class AnimationScene(Scene):
    def construct(self):
        c = Circle(color=BLUE)
        self.play(Create(c), run_time=1)
        self.wait(0.5)
