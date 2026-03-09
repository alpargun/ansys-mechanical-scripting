import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def generate_ramped_staircase(time, num_steps, min_p, max_p, ramp_time=0.5):
    """Generates a hold-and-release pattern with mathematically smooth ramps."""
    signal = np.zeros_like(time)
    dt = time[1] - time[0]
    points_per_step = len(time) // num_steps
    ramp_points = int(ramp_time / dt)
    
    target_pressures = np.random.uniform(min_p, max_p, num_steps)
    current_p = min_p 
    
    for i in range(num_steps):
        start_idx = i * points_per_step
        end_idx = (i + 1) * points_per_step if i < num_steps - 1 else len(time)
        target_p = target_pressures[i]
        
        ramp_end_idx = min(start_idx + ramp_points, end_idx)
        
        # 1. The Smooth Ramp 
        if start_idx < ramp_end_idx:
            signal[start_idx:ramp_end_idx] = np.linspace(current_p, target_p, ramp_end_idx - start_idx)
            
        # 2. The Flat Hold 
        if ramp_end_idx < end_idx:
            signal[ramp_end_idx:end_idx] = target_p
            
        current_p = target_p
        
    return signal

def main():
    DURATION = 60.0       
    DT = 0.01             
    MIN_PRESSURE = 0.001 # 1 Pa strictly enforced to prevent solver vacuums    
    
    # --- THE PHYSICAL FIX ---
    # Dropped from 100.0 to 40.0 to prevent 60-second creep ballooning
    MAX_PRESSURE = 90.0 
    
    NUM_STEPS = 10 
    
    time = np.arange(0, DURATION, DT)
    
    print(f"Generating Safe Ramped Staircase dataset...")
    pressures = {}
    for i in range(1, 4):
        pressures[f'P{i}'] = generate_ramped_staircase(time, NUM_STEPS, MIN_PRESSURE, MAX_PRESSURE, ramp_time=0.5)

    df = pd.DataFrame({
        'Time [s]': time,
        'P1 [kPa]': pressures['P1'],
        'P2 [kPa]': pressures['P2'],
        'P3 [kPa]': pressures['P3']
    })
    
    desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
    csv_filename = os.path.join(desktop_path, 'Staircase_Creep_Test_Safe.csv')
    df.to_csv(csv_filename, index=False)
    print(f"Saved solver-safe Ansys input file: {csv_filename}")

    # Visualization
    plt.figure(figsize=(12, 6))
    plt.plot(time, pressures['P1'], label='Bellow 1', alpha=0.8, linewidth=2)
    plt.plot(time, pressures['P2'], label='Bellow 2', alpha=0.8, linewidth=2)
    plt.plot(time, pressures['P3'], label='Bellow 3', alpha=0.8, linewidth=2)
    plt.title('Physically Capped Ramped Staircase (Max 40 kPa)')
    plt.xlabel('Time (s)')
    plt.ylabel('Pressure (kPa)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()