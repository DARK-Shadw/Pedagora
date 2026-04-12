from manim import *
import numpy as np

class AnimationScene(ThreeDScene):
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

    def construct(self):
        self.camera.background_color = "#0d1117"

        # --- Step 'single-die' (4s) ---
        title_single = Text("Single Die Roll", font_size=36, color=WHITE).to_edge(UP)
        single_die_value = np.random.randint(1, 7)
        single_die = self.build_die(single_die_value, color=BLUE)
        single_die.move_to(LEFT * 4 + UP * 0.5)

        number_line = NumberLine(x_range=[0.5, 6.5, 1], length=8, include_numbers=True, font_size=20)
        number_line.to_edge(DOWN).shift(DOWN*0.5)

        dot_single = Dot(number_line.n2p(single_die_value), color=YELLOW, radius=0.12)
        label_single = MathTex(f"X = {single_die_value}", font_size=28, color=YELLOW).next_to(dot_single, UP, buff=0.15)

        self.play(Write(title_single), Create(number_line), run_time=1.5)
        self.play(
            single_die.animate.shift(RIGHT * 4).rotate(PI * 2).move_to(UP * 0.5),
            run_time=1.5,
            rate_func=lambda t: smooth(t) if t < 0.8 else there_and_back(t)
        )
        self.play(Create(dot_single), Write(label_single), run_time=1)
        self.wait(0.5)

        # --- Step 'many-dice' (5s) ---
        self.play(FadeOut(title_single), run_time=0.5)
        title_many = Text("Many Dice Rolls", font_size=36, color=WHITE).to_edge(UP)
        self.play(Write(title_many), run_time=0.5)

        num_dice = 75 # Max 100 for 2D performance
        dice_values = np.random.randint(1, 7, num_dice)
        dice_group = VGroup()
        dots_group = VGroup()
        
        # Create dice and dots off-screen initially
        for i, val in enumerate(dice_values):
            die = self.build_die(val, color=BLUE_C)
            die.scale(0.4)
            die.move_to(LEFT * 6 + UP * 3 + RIGHT * (i % 10) * 0.5 + DOWN * (i // 10) * 0.5)
            dice_group.add(die)
            
            dot = Dot(number_line.n2p(val) + UP * np.random.uniform(0, 0.5), color=BLUE_A, radius=0.08)
            dots_group.add(dot)

        self.play(FadeOut(single_die), FadeOut(label_single), run_time=0.5)
        self.play(LaggedStart(*[FadeIn(die, shift=RIGHT*0.5) for die in dice_group], lag_ratio=0.01, run_time=2))
        self.play(LaggedStart(*[Transform(dice_group[i], dots_group[i]) for i in range(num_dice)], lag_ratio=0.01, run_time=2))
        self.wait(0.5)

        # Create histogram bars from the dots
        counts = np.bincount(dice_values, minlength=7)[1:] # counts for 1-6
        max_count = max(counts) if counts.size > 0 else 1
        
        # Adjust y_range for histogram to fit counts
        hist_axes = Axes(x_range=[0.5, 6.5, 1], y_range=[0, max_count + 1, max(1, max_count // 3)],
                         x_length=8, y_length=4, axis_config={"include_numbers": True, "font_size": 20})
        hist_axes.to_edge(DOWN).shift(DOWN*0.5)
        
        bars = VGroup()
        for val, count in enumerate(counts):
            if count > 0:
                bar = Rectangle(width=0.7, height=hist_axes.get_y_axis().get_unit_size() * count, color=GREEN_C, fill_opacity=0.7)
                bar.move_to(hist_axes.c2p(val + 1, count / 2))
                bars.add(bar)
        
        self.play(ReplacementTransform(number_line, hist_axes), FadeOut(dots_group), run_time=1)
        self.play(Create(bars), run_time=1)
        self.wait(0.5)

        # --- Step 'higher-dimensions' (5s) ---
        self.play(FadeOut(title_many), FadeOut(bars), run_time=0.5)
        
        # Transform histogram dots to 2D scatter
        scatter_dots_2d = VGroup()
        for val in dice_values:
            x_pos = hist_axes.c2p(val, 0)[0]
            y_pos = np.random.uniform(-1, 1) # Add random Y component for 2D scatter
            dot_2d = Dot(np.array([x_pos, y_pos, 0]), color=YELLOW_A, radius=0.08)
            scatter_dots_2d.add(dot_2d)
        
        self.play(FadeOut(hist_axes), run_time=0.5)
        self.play(LaggedStart(*[Create(dot) for dot in scatter_dots_2d], lag_ratio=0.01, run_time=1.5))
        self.wait(0.5)

        # Transition to 3D
        self.play(FadeOut(scatter_dots_2d), run_time=0.5)
        self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)

        axes3d = ThreeDAxes(x_range=[-3, 3, 1], y_range=[-3, 3, 1], z_range=[-3, 3, 1], x_length=6, y_length=6, z_length=6)
        
        # Create 3D point cloud with structure (e.g., a sphere-like cluster)
        num_3d_points = 25 # Max 25 for performance budget
        points_3d = VGroup()
        for _ in range(num_3d_points):
            # Generate points in a somewhat spherical cluster
            phi_val = np.random.uniform(0, 2 * PI)
            theta_val = np.random.uniform(0, PI)
            radius = np.random.normal(1.5, 0.3) # Cluster around radius 1.5
            x = radius * np.sin(theta_val) * np.cos(phi_val)
            y = radius * np.sin(theta_val) * np.sin(phi_val)
            z = radius * np.cos(theta_val)
            points_3d.add(Dot3D(point=axes3d.c2p(x, y, z), color=PURPLE_A, radius=0.08))
        
        title_3d = Text("High-Dimensional Data", font_size=36, color=WHITE)
        title_3d.to_corner(UL)
        self.add_fixed_in_frame_mobjects(title_3d)

        self.play(Create(axes3d), run_time=1)
        self.play(LaggedStart(*[Create(dot) for dot in points_3d], lag_ratio=0.05, run_time=1.5))
        self.play(Write(title_3d), run_time=0.5)
        self.begin_ambient_camera_rotation(rate=0.15)
        self.wait(1)

        # --- Step 'question-posed' (5s) ---
        self.stop_ambient_camera_rotation()
        question_text = Text("What language describes this?", font_size=32, color=YELLOW)
        question_text.move_to(ORIGIN)
        self.add_fixed_in_frame_mobjects(question_text)

        # Pulse effect on cloud
        self.play(
            points_3d.animate.scale(1.1).set_color(BLUE_A),
            run_time=0.8,
            rate_func=there_and_back
        )
        self.play(
            points_3d.animate.scale(1/1.1).set_color(PURPLE_A),
            run_time=0.8,
            rate_func=there_and_back
        )
        self.play(Write(question_text), run_time=1.5)
        self.wait(1.5)

        # --- Step 'connection-tease' (5s) ---
        self.play(FadeOut(question_text), run_time=0.5)

        # Highlight a point from the cloud
        highlight_point = points_3d[np.random.randint(0, num_3d_points-1)].copy()
        highlight_point.set_color(RED).scale(1.5)
        
        # Placeholder for an image (e.g., a generated digit)
        # Using a simple square as a placeholder image
        generated_image_placeholder = Square(side_length=2, color=GREEN, fill_opacity=0.7)
        generated_image_placeholder_label = Text("Generated Image", font_size=20, color=WHITE)
        generated_image_placeholder_label.next_to(generated_image_placeholder, DOWN)
        image_group = VGroup(generated_image_placeholder, generated_image_placeholder_label)
        image_group.move_to(RIGHT * 3 + UP * 1.5)
        self.add_fixed_in_frame_mobjects(image_group)

        self.play(Create(highlight_point), run_time=1)
        self.play(FadeIn(image_group), run_time=1.5)
        
        connection_label = Text("Generative Models", font_size=28, color=YELLOW)
        connection_label.to_corner(DL)
        self.add_fixed_in_frame_mobjects(connection_label)
        self.play(Write(connection_label), run_time=1)
        self.wait(1)

        self.play(FadeOut(axes3d), FadeOut(points_3d), FadeOut(highlight_point), FadeOut(title_3d), FadeOut(image_group), FadeOut(connection_label), run_time=1)
        self.wait(0.5)