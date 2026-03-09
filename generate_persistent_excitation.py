import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, chirp

# ==========================================
# --- CONFIGURATION ---
# ==========================================
DURATION = 60.0         # 60 seconds
DT = 0.01               # 100 Hz generation (gives Ansys smooth substeps)
MAX_PRESSURE = 90.0     # kPa
MIN_PRESSURE = 1.0      # kPa (Safety floor to prevent vacuum crashing)
CUTOFF_HZ = 12.0        # Stay safely under 15 Hz Nyquist limit for 30 FPS camera

t = np.arange(0, DURATION + DT, DT)

def scale_to_pressure(signal, min_p, max_p):
    """Scales any signal to perfectly fit within our safe pressure bounds."""
    sig_min, sig_max = np.min(signal), np.max(signal)
    normalized = (signal - sig_min) / (sig_max - sig_min)
    return min_p + normalized * (max_p - min_p)

# ==========================================
# 1. BAND-LIMITED RANDOM SPLINE (Filtered Noise)
# ==========================================
print("Generating Band-Limited Random Excitation...")
# Generate raw white noise
noise_p1 = np.random.normal(0, 1, len(t))
noise_p2 = np.random.normal(0, 1, len(t))
noise_p3 = np.random.normal(0, 1, len(t))

# Create a 4th-order Butterworth Low-Pass Filter
nyquist = 0.5 * (1.0 / DT)
normal_cutoff = CUTOFF_HZ / nyquist
b, a = butter(4, normal_cutoff, btype='low', analog=False)

# Apply filter to create smooth, chaotic splines
smooth_p1 = filtfilt(b, a, noise_p1)
smooth_p2 = filtfilt(b, a, noise_p2)
smooth_p3 = filtfilt(b, a, noise_p3)

# Scale to safe limits
p1_random = scale_to_pressure(smooth_p1, MIN_PRESSURE, MAX_PRESSURE)
p2_random = scale_to_pressure(smooth_p2, MIN_PRESSURE, MAX_PRESSURE)
p3_random = scale_to_pressure(smooth_p3, MIN_PRESSURE, MAX_PRESSURE)

df_random = pd.DataFrame({'Time [s]': t, 'P1 [kPa]': p1_random, 'P2 [kPa]': p2_random, 'P3 [kPa]': p3_random})
df_random.to_csv("Persistent_Excitation_Random.csv", index=False)

# ==========================================
# 2. CHIRP SIGNAL (0.5 Hz to 15 Hz Sweep)
# ==========================================
print("Generating 15 Hz Chirp Sweep...")
# We phase-shift the bellows so the robot spirals as it vibrates
# P1: Base chirp
# P2: Phase shifted by 120 degrees
# P3: Phase shifted by 240 degrees

phase_rad = 2.0 * np.pi / 3.0 
f_start = 0.5
f_end = 15.0

# Generate Chirps
chirp_p1 = chirp(t, f0=f_start, f1=f_end, t1=DURATION, method='linear')
chirp_p2 = chirp(t, f0=f_start, f1=f_end, t1=DURATION, method='linear', phi=-phase_rad * 180 / np.pi)
chirp_p3 = chirp(t, f0=f_start, f1=f_end, t1=DURATION, method='linear', phi=-2 * phase_rad * 180 / np.pi)

p1_chirp = scale_to_pressure(chirp_p1, MIN_PRESSURE, MAX_PRESSURE)
p2_chirp = scale_to_pressure(chirp_p2, MIN_PRESSURE, MAX_PRESSURE)
p3_chirp = scale_to_pressure(chirp_p3, MIN_PRESSURE, MAX_PRESSURE)

df_chirp = pd.DataFrame({'Time [s]': t, 'P1 [kPa]': p1_chirp, 'P2 [kPa]': p2_chirp, 'P3 [kPa]': p3_chirp})
df_chirp.to_csv("Persistent_Excitation_Chirp.csv", index=False)

print("Done! Files saved: 'Persistent_Excitation_Random.csv' and 'Persistent_Excitation_Chirp.csv'")