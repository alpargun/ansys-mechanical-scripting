import numpy as np
import pandas as pd

# ==========================================
# --- CONFIGURATION ---
# ==========================================
DURATION = 10.0         # 10 seconds is mathematically sufficient for steady-state vibration
DT = 0.01               # 100 Hz generation
MAX_PRESSURE = 90.0     # kPa
MIN_PRESSURE = 0.001    # kPa (Exactly 1 Pa safety floor)
FADE_IN_TIME = 1.0      # 1-second envelope

# The specific missing frequencies to target
FREQUENCIES = [4.0, 8.0, 12.0, 15.0]

t = np.arange(0, DURATION + DT, DT)
envelope = np.clip(t / FADE_IN_TIME, 0.0, 1.0)

def scale_to_pressure(signal, min_p, max_p):
    """Scales a [-1, 1] sine wave perfectly to our safe pressure bounds."""
    # Since sine waves are exactly -1 to 1, we can hardcode the normalization
    normalized = (signal + 1.0) / 2.0 
    return min_p + normalized * (max_p - min_p)

def apply_safe_fade(signal_scaled):
    """Applies the envelope while maintaining the 1 Pa minimum floor."""
    return MIN_PRESSURE + (signal_scaled - MIN_PRESSURE) * envelope

# ==========================================
# GENERATE THE 4 FILES
# ==========================================
print("Generating Targeted Frequency Bursts...")

for freq in FREQUENCIES:
    # Base angular velocity
    omega = 2.0 * np.pi * freq
    
    # Generate 120-degree phase-shifted sine waves for maximum 3D swirl
    # Phase shifts: 0, 2pi/3, 4pi/3
    s1 = np.sin(omega * t)
    s2 = np.sin(omega * t - (2.0 * np.pi / 3.0))
    s3 = np.sin(omega * t - (4.0 * np.pi / 3.0))
    
    # Scale and apply the 1-second safety envelope
    p1 = apply_safe_fade(scale_to_pressure(s1, MIN_PRESSURE, MAX_PRESSURE))
    p2 = apply_safe_fade(scale_to_pressure(s2, MIN_PRESSURE, MAX_PRESSURE))
    p3 = apply_safe_fade(scale_to_pressure(s3, MIN_PRESSURE, MAX_PRESSURE))
    
    # Save to CSV
    filename = f"Burst_Excitation_{int(freq)}Hz.csv"
    df = pd.DataFrame({'Time [s]': t, 'P1 [kPa]': p1, 'P2 [kPa]': p2, 'P3 [kPa]': p3})
    df.to_csv(filename, index=False)
    print(f" -> Saved: {filename} ({int(freq)} Hz, 10s duration)")

print("\nDone! Ready for Ansys.")