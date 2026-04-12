from manim import *
import numpy as np

class AnimationScene(ThreeDScene):
    def build_die(self, value, color=BLUE):
        face = Square(side_length=1.0, color=color, fill_opacity=0.9, stroke_color=WHITE)
        pip_positions = {
            1: [ORIGIN], 2: [UL*0.3, DR*0.3], 3: [UL*0.3, ORIGIN, DR*0.3],
            4: [UL*0.3, UR*0.3, DL*0.3, DR*0.3],
            5: [UL*0.3, UR*0.3, ORIGIN, DL*0.3, DR*0.3],
            6: [UL*0.3, UR*0.3, LEFT*0.3, RIGHT*0.3, DL*0.3, DR*0.3],
        }
        pips = VGroup(*[Dot(p, color=WHITE, radius=0.08) for p in pip_positions.get(value, [])])
        return VGroup(face, pips)

    def construct(self):
        self.camera.background_color = "#0d1117"
        
        # Step 1: Single Die
        nl = NumberLine(x_range=[1, 6, 1], length=6, include_numbers=True).to_edge(DOWN)
        die = self.build_die(4)
        label = MathTex(r"X = 4", font_size=36, color=YELLOW).to_edge(UP)
        self.play(Create(nl), FadeIn(die), run_time=1.5)
        self.play(die.animate.next_to(nl.n2p(4), UP, buff=0.5), Write(label), run_time=1.5)
        self.wait(1)

        # Step 2: Many Dice
        self.play(FadeOut(die), FadeOut(label))
        axes = Axes(x_range=[0.5, 6.5, 1], y_range=[0, 10, 2], x_length=6, y_length=3, axis_config={"include_numbers": True}).to_edge(DOWN)
        bars = VGroup(*[Rectangle(width=0.6, height=np.random.randint(1, 8)*0.3, color=BLUE, fill_opacity=0.7).move_to(axes.c2p(i, 0)) for i in range(1, 7)])
        bars.arrange(RIGHT, buff=0.2).next_to(axes.x_axis, UP, aligned_edge=DOWN)
        self.play(Create(axes), FadeIn(bars), run_time=2)
        self.wait(1)

        # Step 3: Higher Dimensions
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
        axes3d = ThreeDAxes(x_range=[-2, 2, 1], y_range=[-2, 2, 1], z_range=[-2, 2, 1], x_length=5, y_length=5, z_length=5)
        points = VGroup(*[Dot3D(point=np.random.normal(0, 0.8, 3), color=PURPLE, radius=0.05) for _ in range(25)])
        self.play(FadeOut(axes), FadeOut(bars), Create(axes3d), run_time=1)
        self.play(FadeIn(points), run_time=1.5)
        self.begin_ambient_camera_rotation(rate=0.2)
        self.wait(2)

        # Step 4: Question
        question = Text("What language describes this?", font_size=32, color=WHITE).to_edge(UP)
        self.play(Write(question), run_time=1.5)
        self.play(points.animate.set_color(YELLOW), run_time=1.5)
        self.wait(2)

        # Step 5: Connection
        img = Square(side_length=1.5, color=GREEN, fill_opacity=0.5).next_to(points, RIGHT, buff=1)
        img_label = Text("Generative Model", font_size=20).next_to(img, DOWN)
        self.play(FadeIn(img), Write(img_label), run_time=1.5)
        self.stop_ambient_camera_rotation()
        self.wait(2)