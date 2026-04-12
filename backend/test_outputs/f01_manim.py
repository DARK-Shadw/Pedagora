from manim import *
import numpy as np

class AnimationScene(ThreeDScene):
    def construct(self):
        self.camera.background_color = "#0d1117"
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
        
        # Step 1: Single Die
        die = Cube(side_length=1, fill_opacity=0.8, color=BLUE)
        pip = Dot(point=die.get_center() + OUT * 0.5 + UP * 0.2, color=WHITE, radius=0.1)
        die_group = VGroup(die, pip)
        self.play(Create(die_group), run_time=1.5)
        self.play(die_group.animate.shift(DOWN * 2), run_time=1)
        
        # Step 2: Many Dice
        dice = VGroup(*[Cube(side_length=0.4, fill_opacity=0.6, color=BLUE).shift(np.random.uniform(-3, 3, 3)) for _ in range(20)])
        self.play(ReplacementTransform(die_group, dice), run_time=1.5)
        
        # Step 3: Higher Dimensions
        points = VGroup(*[Dot3D(point=np.random.normal(0, 1, 3), color=YELLOW, radius=0.05) for _ in range(25)])
        self.play(ReplacementTransform(dice, points), run_time=2)
        self.begin_ambient_camera_rotation(rate=0.2)
        
        # Step 4: Question
        text = Text("What language describes this?", font_size=36, color=WHITE)
        text.to_edge(UP)
        self.add_fixed_in_frame_mobjects(text)
        self.play(Write(text), run_time=1.5)
        
        # Step 5: Connection Tease
        sample = Dot3D(point=points[0].get_center(), color=RED, radius=0.15)
        self.add(sample)
        self.play(sample.animate.scale(2), run_time=1)
        self.play(FadeOut(sample), run_time=1)
        
        self.wait(2)
        self.stop_ambient_camera_rotation()