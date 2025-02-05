import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider


# AFTER YOU SLIDE THE CURVE, YOU CAN SAVE THE CURVE TO CSV FILES BY HOLDING DOWN THE 's' KEY

# VARIABLES YOU CAN CHANGE
points_count = 1000  # Adjust this for lower/higher resolution
wavelengths = np.linspace(0,6e-6,points_count)  # Using points_count instead of hardcoded 1000
temperatures = [3000,4000,5000]# list of temperatures to plot

# axis limits
y_max = 1.4e7  # Change based on your observation. this is what works for temperatures 3000, 4000, 5000

set_x_limits = False # set to be true if you want to set the x-axis limits. usually not necessary 
x_min = 0  # minimum wavelength in μm
x_max = 6  # maximum wavelength in μm

# limits for the slider
h_min = 0.1
h_max = 2.0




c = 299792458 # speed of light (m/s)
k_B = 1.380649e-23 # Boltzmann constant (J/K)
h_actual = 6.62607015e-34 # Actual Planck constant (J*s)

def I(lambdaa, temperature, h):
    # temperature in Kelvin
    # Returns spectral radiance in W⋅sr⁻¹⋅m⁻²⋅m⁻¹
    return (2*h*c**2)/(lambdaa**5) * 1/(np.exp((h*c)/(lambdaa*k_B*temperature)) - 1)

def I_classical(lambdaa, temperature):
    return (2*c*k_B*temperature)/(lambdaa**4)


# Create the figure and axis
fig, ax = plt.subplots(figsize=(10, 8))
plt.subplots_adjust(bottom=0.25)  # Make room for the slider

# Create the initial plot
lines = []

ax.set_ylim(0, y_max)
if set_x_limits:
    ax.set_xlim(x_min, x_max)

# Add classical curve for 5000K
classical_intensities = I_classical(wavelengths, 5000)
ax.plot(wavelengths*1e6, classical_intensities*1e-6, '--', label='Classical 5000K', color='red')

# Save classical curve data
classical_data = np.column_stack((wavelengths*1e6, classical_intensities*1e-6))
np.savetxt('classical_5000K.csv', classical_data, delimiter=',', 
           header='wavelength_um,intensity_MW_sr-1_m-2_nm-1', comments='')

for temp in temperatures:
    intensities = []
    for wavelength in wavelengths:
        intensity = I(wavelength, temp, h_actual)
        intensities.append(intensity)
    intensities = np.array(intensities)
    line, = ax.plot(wavelengths*1e6, intensities*1e-6, label=f"{temp} K")
    lines.append(line)
    
    # Save data for each temperature
    data = np.column_stack((wavelengths*1e6, intensities*1e-6))
    np.savetxt(f'blackbody_{temp}K.csv', data, delimiter=',',
               header='wavelength_um,intensity_MW_sr-1_m-2_nm-1', comments='')

# Add "experimental data points" (using actual Planck's constant)
# Let's add fewer points to make it look like actual measurements
experimental_wavelengths = np.linspace(0.1e-6, 5e-6, 50)  # 20 "measurement" points
experimental_intensities = I(experimental_wavelengths, 5000, h_actual)  # Using 5000K as our "experiment"

# Save experimental data points
exp_data = np.column_stack((experimental_wavelengths*1e6, experimental_intensities*1e-6))
np.savetxt('experimental_data.csv', exp_data, delimiter=',',
           header='wavelength_um,intensity_MW_sr-1_m-2_nm-1', comments='')

# Add experimental data points plot
ax.scatter(experimental_wavelengths*1e6, experimental_intensities*1e-6, 
          color='black', marker='o', label='5000K Experimental Data', 
          zorder=3, s=50)  # zorder=3 to ensure points are on top

ax.set_xlabel('Wavelength (μm)')
ax.set_ylabel('Spectral Radiance (MW⋅sr⁻¹⋅m⁻²⋅nm⁻¹)')
ax.set_title(f'Blackbody Radiation (h = {h_actual:.2e} J⋅s)')
ax.legend()
ax.grid(True)

# Create the slider axis and slider
ax_slider = plt.axes([0.2, 0.1, 0.6, 0.03])  # [left, bottom, width, height]
h_slider = Slider(
    ax=ax_slider,
    label='h multiplier',
    valmin=h_min,
    valmax=h_max,
    valinit=1.0
)

# Update function for the slider
def update(val):
    h = h_actual * val
    for temp, line in zip(temperatures, lines):
        intensities = []
        for wavelength in wavelengths:
            intensity = I(wavelength, temp, h)
            intensities.append(intensity)
        intensities = np.array(intensities)
        line.set_ydata(intensities*1e-6)
    
    ax.set_title(f'Blackbody Radiation (h = {h:.2e} J⋅s)\nFit quality: {abs(1-val):.3f} error')
    fig.canvas.draw_idle()

# Save function for keyboard shortcut
def save_current_state(event):
    if event.key == 's':
        h = h_actual * h_slider.val
        for temp, line in zip(temperatures, lines):
            intensities = []
            for wavelength in wavelengths:
                intensity = I(wavelength, temp, h)
                intensities.append(intensity)
            intensities = np.array(intensities)
            
            # Save data for each temperature at current h value
            data = np.column_stack((wavelengths*1e6, intensities*1e-6))
            np.savetxt(f'{h_slider.val:.3f}_blackbody_{temp}K.csv', data, delimiter=',',
                       header='wavelength_um,intensity_MW_sr-1_m-2_nm-1', comments='')
        print(f"Saved curves for h multiplier = {h_slider.val:.3f}")

h_slider.on_changed(update)
fig.canvas.mpl_connect('key_press_event', save_current_state)
plt.show()



