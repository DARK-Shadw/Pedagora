from manim import *
import numpy as np

class AnimationScene(Scene):
    def construct(self):
        # Setup
        np.random.seed(42)
        data = np.random.normal(1.2, 0.8, 12)
        
        # Title/Formula
        formula = MathTex(r"L(\mu, \sigma) = \sum \log \left( \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{(x_i-\mu)^2}{2\sigma^2}} \right)", font_size=28)
        formula.to_edge(UP)
        self.add(formula)

        # Trackers
        mu = ValueTracker(0)
        sigma = ValueTracker(2)
        
        # Left Panel: Data points
        dots = VGroup(*[Dot(point=RIGHT * x + DOWN * 2, color=BLUE) for x in data])
        labels = Text("Data points", font_size=24).next_to(dots, UP)
        self.add(dots, labels)

        # Right Panel: Gaussian
        axes = Axes(x_range=[-4, 4], y_range=[0, 0.6], axis_config={"include_numbers": False}).scale(0.7).shift(DOWN * 0.5)
        
        def get_gaussian():
            m, s = mu.get_value(), sigma.get_value()
            return axes.plot(lambda x: (1/(s*np.sqrt(2*np.pi))) * np.exp(-(x-m)**2/(2*s**2)), color=RED)

        curve = always_redraw(get_gaussian)
        self.add(axes, curve)

        # Likelihood tracker
        def get_log_likelihood():
            m, s = mu.get_value(), sigma.get_value()
            ll = np.sum(-0.5 * np.log(2 * np.pi * s**2) - ((data - m)**2 / (2 * s**2)))
            return ll

        ll_text = always_redraw(lambda: Text(f"L = {get_log_likelihood():.2f}", font_size=30).next_to(formula, DOWN))
        self.add(ll_text)

        # Animation
        self.play(mu.animate.set_value(1.2), sigma.animate.set_value(0.8), run_time=4)
        curve.set_color(GREEN)
        self.wait(1)

        # Vertical lines
        lines = always_redraw(lambda: VGroup(*[
            DashedLine(
                axes.c2p(x, 0), 
                axes.c2p(x, (1/(sigma.get_value()*np.sqrt(2*np.pi))) * np.exp(-(x-mu.get_value())**2/(2*sigma.get_value()**2))),
                color=YELLOW
            ) for x in data
        ]))
        
        self.play(Create(lines), run_time=2)
        self.wait(3)