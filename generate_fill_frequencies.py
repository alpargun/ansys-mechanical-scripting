import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt
import os

# ==========================================
# --- CONFIGURATION ---
# ==========================================
DT = 0.01 
DURATION = 10.0         # 10s runs
MIN_PRESSURE = 0.001    # kPa (Exactly 1 Pa safety floor)
MAX_PRESSURE = 90.0     # kPa upper limit
MAX_AMPLITUDE = 25.0    # Capped +/- 25 kPa swings to prevent Ansys from diverging
BASE_PRESSURE = 40.0    # Centered around 40 kPa
NUM_FILES = 5

t_array = np.arange(0, DURATION + DT, DT)
envelope = np.clip(t_array / 1.0, 0.0, 1.0) # 1-second fade-in

# Butterworth filter to strictly cut off at 15 Hz
b, a = butter(4, 15.0 / (0.5 * (1.0 / DT)), btype='low')

def generate_safe_random_action():
    """Generates a bounded, 15Hz-limited random signal with a 1-sec fade-in."""
    noise = np.random.normal(0, 1, len(t_array))
    smooth_noise = filtfilt(b, a, noise)
    
    # Normalize to [-1, 1]
    smooth_noise = smooth_noise / np.max(np.abs(smooth_noise))
    
    # Scale to safe amplitude around base pressure
    signal = BASE_PRESSURE + (smooth_noise * MAX_AMPLITUDE)
    
    # Apply 1-second fade-in to prevent initial shockwave
    signal = MIN_PRESSURE + (signal - MIN_PRESSURE) * envelope
    
    # Clip to absolute physical bounds just in case
    return np.clip(signal, MIN_PRESSURE, MAX_PRESSURE)

# ==========================================
# --- EXECUTION & EXPORT ---
# ==========================================
# Get the Desktop path for whatever OS you are on
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")

print(f"Generating {NUM_FILES} Safe Random Action CSVs...")

for i in range(1, NUM_FILES + 1):
    # Generate 3 independent bellows signals
    p1 = generate_safe_random_action()
    p2 = generate_safe_random_action()
    p3 = generate_safe_random_action()
    
    df = pd.DataFrame({'Time [s]': t_array, 'P1 [kPa]': p1, 'P2 [kPa]': p2, 'P3 [kPa]': p3})
    
    filename = f"Safe_Random_Actions_{i}.csv"
    filepath = os.path.join(desktop_path, filename)
    df.to_csv(filepath, index=False)
    print(f" -> Saved: {filepath}")

print("\nGeneration complete! Ready for Ansys.")