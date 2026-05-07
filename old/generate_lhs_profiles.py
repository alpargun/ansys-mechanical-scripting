import os
import numpy as np
import pandas as pd
from scipy.stats import qmc

def generate_lhs_ansys_profiles():
    # ==========================================
    # --- 1. CONFIGURATION ---
    # ==========================================
    OUTPUT_DIR = "Ansys_LHS_Profiles"
    NUM_SAMPLES = 15  # The number of highly efficient random cases
    FRAMES = 60
    MIN_P = 1.0       # Strict baseline constraint
    MAX_P = 100.0     # Maximum physical limit
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Generating {NUM_SAMPLES} Latin Hypercube profiles in: {OUTPUT_DIR}/\n")

    # ==========================================
    # --- 2. LATIN HYPERCUBE SAMPLING ---
    # ==========================================
    # We have 3 dimensions (Chamber 1, Chamber 2, Chamber 3)
    sampler = qmc.LatinHypercube(d=3)
    
    # Generate 15 samples in the [0, 1] range
    lhs_samples = sampler.random(n=NUM_SAMPLES)
    
    # Scale the samples to our physical pressure bounds [MIN_P, MAX_P]
    scaled_targets = qmc.scale(lhs_samples, [MIN_P, MIN_P, MIN_P], [MAX_P, MAX_P, MAX_P])

    # ==========================================
    # --- 3. GENERATE 60-FRAME RAMP SEQUENCES ---
    # ==========================================
    for i, target in enumerate(scaled_targets):
        target_p1, target_p2, target_p3 = target
        
        # Initialize empty arrays
        p1 = np.zeros(FRAMES)
        p2 = np.zeros(FRAMES)
        p3 = np.zeros(FRAMES)
        
        # Frame 0 to 30: Ramp UP from MIN_P to the LHS Target
        p1[:30] = np.linspace(MIN_P, target_p1, 30)
        p2[:30] = np.linspace(MIN_P, target_p2, 30)
        p3[:30] = np.linspace(MIN_P, target_p3, 30)
        
        # Frame 30 to 60: Ramp DOWN from the LHS Target back to MIN_P
        p1[30:] = np.linspace(target_p1, MIN_P, 30)
        p2[30:] = np.linspace(target_p2, MIN_P, 30)
        p3[30:] = np.linspace(target_p3, MIN_P, 30)
        
        # Save to CSV for Ansys
        df = pd.DataFrame({
            'Frame': np.arange(FRAMES),
            'Chamber_1': p1,
            'Chamber_2': p2,
            'Chamber_3': p3
        })
        
        filename = f"LHS_Asymmetric_Case_{i+1:02d}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)
        df.to_csv(filepath, index=False)
        
        print(f"Saved: {filename} | Peak Targets -> C1: {target_p1:.1f}, C2: {target_p2:.1f}, C3: {target_p3:.1f}")

    print("\nDone! Import these 15 CSVs into Ansys for the sparse interior sampling.")

if __name__ == "__main__":
    generate_lhs_ansys_profiles()