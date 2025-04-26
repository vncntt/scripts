from manim import (
    Scene,
    VGroup,
    Tex,
    MathTex,
    FadeIn,
    FadeOut,
    MoveToTarget,
    config
)

# ----------------------------------------------------------------------------
# Configuration overrides (you can also supply these on the CLI if you prefer)
# ----------------------------------------------------------------------------
config.pixel_width = 1920
config.pixel_height = 1080
config.frame_rate = 30
config.background_color = "#FFFFFF"  # White background

class EquationsScene(Scene):
    def construct(self):
        # --------------------------------------------------------------------
        # 1. Define parameters
        # --------------------------------------------------------------------
        equations_file = "equations.txt"  # Input file with one LaTeX equation per line
        display_time   = 1.0             # Seconds to hold each equation set
        fade_duration  = 1.0             # Seconds for fade/slide animations
        max_visible    = 5               # Max number of equations displayed at once
        vertical_gap   = 1.0             # Spacing between equations

        # --------------------------------------------------------------------
        # 2. Read equations from file
        # --------------------------------------------------------------------
        with open(equations_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        # --------------------------------------------------------------------
        # 3. Setup data structures
        # --------------------------------------------------------------------
        displayed_equations = VGroup()  # will hold the currently visible equations

        # --------------------------------------------------------------------
        # 4. Helper: position visible equations
        #    We'll call this after we modify the displayed_equations group
        #    so they stack nicely in the vertical center
        # --------------------------------------------------------------------
        def position_equations(equations_group):
            """
            Positions equations to evenly divide the vertical space.
            As more equations are added, they spread out until reaching max_visible.
            """
            num_equations = len(equations_group)
            # Height of the visible area (slightly less than full height to leave margins)
            screen_height = 6.0
            
            if num_equations == 1:
                # First equation goes in the middle
                equations_group[0].move_to([0, 0, 0])
            else:
                # Multiple equations divide the screen evenly
                spacing = screen_height / (num_equations + 1)
                top_position = screen_height/2 - spacing
                
                for i, eq in enumerate(equations_group):
                    y_pos = top_position - (i * spacing)
                    eq.move_to([0, y_pos, 0])

        # --------------------------------------------------------------------
        # 5. Main loop: add each equation in turn, animate
        # --------------------------------------------------------------------
        for eq_text in lines:
            # Create the equation mobject
            eq_mobj = MathTex(eq_text, color="#000000")  # black text
            eq_mobj.scale(1.0)  # adjust scale as needed

            if len(displayed_equations) < max_visible:
                # First add the equation to our group
                displayed_equations.add(eq_mobj)
                
                # Calculate final positions for ALL equations
                final_positions = []
                temp_group = displayed_equations.copy()
                position_equations(temp_group)
                for eq in temp_group:
                    final_positions.append(eq.get_center())
                
                # Position new equation below the screen
                eq_mobj.move_to([0, -vertical_gap * (max_visible), 0])
                
                # Create animations for ALL equations to move to their correct positions
                animations = []
                for i, eq in enumerate(displayed_equations):
                    # Only animate the previous equations if they're not at their final positions
                    if i < len(displayed_equations) - 1:
                        animations.append(eq.animate.move_to(final_positions[i]))
                    else:
                        # This is the new equation, always animate it
                        animations.append(eq.animate.move_to(final_positions[i]))
                
                # Play all animations together
                self.play(*animations, run_time=fade_duration)
                self.wait(display_time)
            else:
                # Case B: We already have 'max_visible' equations visible.
                # The oldest (topmost) one slides out; 
                # new one slides in from the bottom.

                # 1) Create a "target" position for everything to shift up
                # so the top equation slides off-screen, and the new one
                # appears below. We'll shift the group up by 'vertical_gap'.
                # Then we'll remove the top eq once the animation finishes.

                top_eq = displayed_equations[0]  # the top equation
                displayed_equations.remove(top_eq)
                displayed_equations.add(eq_mobj)
                
                # Save the position where we want equations to end up
                final_positions = []
                temp_group = displayed_equations.copy()
                position_equations(temp_group)
                for eq in temp_group:
                    final_positions.append(eq.get_center())
                
                # Animate the top equation going out
                self.play(
                    top_eq.animate.shift([0, vertical_gap, 0]).set_opacity(0),
                    run_time=fade_duration
                )
                self.remove(top_eq)
                
                # Position the new equation off-screen at the bottom
                eq_mobj.move_to([0, -vertical_gap * (max_visible), 0])
                self.add(eq_mobj)
                
                # Animate all equations moving to their final positions
                animations = []
                for i, eq in enumerate(displayed_equations):
                    animations.append(eq.animate.move_to(final_positions[i]))
                
                self.play(*animations, run_time=fade_duration)
                
                # Wait for display time
                self.wait(display_time)

        # Finally, fade out any remaining equations (optional)
        self.play(*[FadeOut(eq, run_time=fade_duration) for eq in displayed_equations])