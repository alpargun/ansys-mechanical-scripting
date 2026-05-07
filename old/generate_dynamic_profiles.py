import os
import numpy as np
import pandas as pd
from scipy.signal import chirp

def generate_ansys_profiles():
    # ==========================================
    # --- 1. CONFIGURATION ---
    # ==========================================
    OUTPUT_DIR = "Ansys_Dynamic_Profiles"
    FRAMES = 60
    MIN_P = 1.0
    MAX_P = 100.0 # Adjust based on your physical limits
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Generating profiles in: {OUTPUT_DIR}/")

    # Time vector (assuming 30 FPS, so 2 seconds total)
    t = np.linspace(0, 2, FRAMES)

    def save_csv(filename, p1, p2, p3):
        # Clip everything to ensure strict bounds
        p1 = np.clip(p1, MIN_P, MAX_P)
        p2 = np.clip(p2, MIN_P, MAX_P)
        p3 = np.clip(p3, MIN_P, MAX_P)
        
        df = pd.DataFrame({
            'Frame': np.arange(FRAMES),
            'Chamber_1': p1,
            'Chamber_2': p2,
            'Chamber_3': p3
        })
        filepath = os.path.join(OUTPUT_DIR, filename)
        df.to_csv(filepath, index=False)
        print(f"Saved: {filename}")

    # ==========================================
    # --- 2. PRBS (PSEUDO-RANDOM BINARY STEPS) ---
    # ==========================================
    # Generates sudden, random jumps to shock the system.
    # FIXED: Evenly distributes the signals across all 3 chambers!
    for i in range(6):
        target_chamber = i % 3  # Cycles through 0, 1, 2
        
        # Generate the random step signal
        p_active = np.ones(FRAMES) * MIN_P
        for step in range(0, FRAMES, 10): 
            p_active[step:step+10] = np.random.uniform(MIN_P, MAX_P)
            
        # Apply the active signal to the correct chamber
        p1, p2, p3 = np.ones(FRAMES) * MIN_P, np.ones(FRAMES) * MIN_P, np.ones(FRAMES) * MIN_P
        if target_chamber == 0:
            p1 = p_active
        elif target_chamber == 1:
            p2 = p_active
        else:
            p3 = p_active
            
        save_csv(f"PRBS_SingleChamber_C{target_chamber+1}_run{i//3 + 1}.csv", p1, p2, p3)

    # ==========================================
    # --- 3. CHIRP SIGNALS (FREQUENCY SWEEP) ---
    # ==========================================
    # Sine wave that gets progressively faster (tests resonance/damping)
    for i in range(3):
        # Sweeps from 0.5 Hz to 5 Hz over the 2 seconds
        c_signal = chirp(t, f0=0.5, f1=5.0, t1=2, method='linear')
        # Normalize to pressure range
        c_signal = ((c_signal + 1) / 2) * (MAX_P - MIN_P) + MIN_P
        
        p1, p2, p3 = np.ones(FRAMES) * MIN_P, np.ones(FRAMES) * MIN_P, np.ones(FRAMES) * MIN_P
        if i == 0: p1 = c_signal
        elif i == 1: p2 = c_signal
        else: p3 = c_signal
            
        save_csv(f"Chirp_Sweep_C{i+1}.csv", p1, p2, p3)

    # ==========================================
    # --- 4. MULTI-CHAMBER CHAOS ---
    # ==========================================
    # Rapidly alternating chambers to test extreme internal stress
    p1 = np.ones(FRAMES) * MIN_P
    p2 = np.ones(FRAMES) * MIN_P
    p3 = np.ones(FRAMES) * MIN_P
    
    # Pulse C1, then C2, then C3 in a rapid sequence
    for step in range(0, FRAMES, 15):
        p1[step:step+5] = MAX_P
        p2[step+5:step+10] = MAX_P
        p3[step+10:step+15] = MAX_P
        
    save_csv("Multi_Chamber_Alternating.csv", p1, p2, p3)

    print("\nDone! Import these CSVs into Ansys to generate the dynamic dataset.")

if __name__ == "__main__":
    generate_ansys_profiles()