from manim import *
import numpy as np
from scipy.special import fresnel

class CornuSpiral(Scene):
    def construct(self):
        # === CUSTOMIZABLE PARAMETERS ===
        # Adjust these values to tweak the visualization
        SPIRAL_SCALE = 3.8        # Size of the spiral (higher = bigger)
        SPIRAL_Y_POSITION = 0.8   # Vertical position of spiral (higher = more up)
        PATH_Y_POSITION = -3.0    # Vertical position of A-B points (lower = more down)
        PATH_HEIGHT_MAX = 1.5     # Maximum height of the V-shaped paths
        PATH_SAMPLING = 5         # Show one path for every N arrows (higher = fewer paths)
        # ==============================
        
        # Set transparent background
        self.camera.background_color = None
        
        # Parametric definition of the Cornu spiral
        def param_spiral(t):
            x, y = fresnel(t)
            return SPIRAL_SCALE * np.array([x, y, 0])
        
        # Number of discrete segments
        N = 150 # I WANT THIS NUMBER OF DISCRETE SEGMENTS.
        
        # Parameter samples from t = -4 to t = 4
        t_values = np.linspace(-5, 5, N)
        
        # Create a vibrant color gradient with more color stops
        segment_colors = color_gradient([
            "#FF0000",  
            "#FF7700",  
            "#FFDD00",  
            "#00FF00",  
            "#00CCCC"   
        ], N - 1)
        
        # Build all the arrows
        arrows = VGroup()
        for i in range(N - 1):
            start_point = param_spiral(t_values[i])
            end_point   = param_spiral(t_values[i + 1])
            arrow = Arrow(
                start_point,
                end_point,
                buff=0
            ).set_color(segment_colors[i])
            arrows.add(arrow)
        
        # Move the spiral up to leave space for the paths, but ensure it stays on screen
        arrows.center()
        arrows.shift(UP * SPIRAL_Y_POSITION)
        
        # Set fixed points A and B for the paths
        point_A = np.array([-4, PATH_Y_POSITION, 0])
        point_B = np.array([4, PATH_Y_POSITION, 0])
        
        # Create dots for points A and B
        dot_A = Dot(point_A, color=WHITE)
        dot_B = Dot(point_B, color=WHITE)
        
        # Create labels for points A and B
        label_A = Text("A", font_size=24).next_to(dot_A, DOWN)
        label_B = Text("B", font_size=24).next_to(dot_B, DOWN)
        
        # Add fixed elements to the scene
        self.add(dot_A, dot_B, label_A, label_B)
        
        # Create paths from A to B that change shape
        # We'll create fewer paths to avoid overcrowding
        step = PATH_SAMPLING  # Create a path for every N arrows
        paths = VGroup()
        
        for i in range(0, N - 1, step):
            # Calculate progress (0 to 1) for determining path shape
            progress = i / (N - 1)
            
            # Calculate vertical displacement for the middle control point
            # Start with wide V, transition to straight line, end with upside-down V
            middle_y_offset = PATH_HEIGHT_MAX * (progress - 0.5)  # Ranges from PATH_HEIGHT_MAX/2 to -PATH_HEIGHT_MAX/2
            
            # Middle control point
            control_point = np.array([0, PATH_Y_POSITION + middle_y_offset, 0])
            
            # Create a V-shaped path (two straight lines joined at the control point)
            path = VMobject()
            path.set_points_as_corners([point_A, control_point, point_B])
            
            # Use the same color as the corresponding arrow
            path.set_color(segment_colors[i])
            
            paths.add(path)
        
        # Animate them appearing one by one in sequence
        self.play(
            LaggedStart(
                *[Create(arrow) for arrow in arrows],
                lag_ratio=0.9, ## DO NOT CHANGE THIS. I WANT THIS LAG RATIO
                run_time=6
            ),
            LaggedStart(
                *[Create(path) for path in paths],
                lag_ratio=0.9 * step,  # Adjust to match arrow timing
                run_time=6
            )
        )
        
        # Pause to see the final spiral
        self.wait(1)

if __name__ == "__main__":
    scene = CornuSpiral()
    scene.render()