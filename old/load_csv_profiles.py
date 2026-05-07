import os

# ==========================================
# --- 1. WINDOWS CONFIGURATION ---
# ==========================================
# Use the raw string (r"") format for Windows file paths!
# Update these to the actual folders on your Windows C: drive
DATA_FOLDERS = [
    r"C:\SoftRobot_Sim\Ansys_Dynamic_Profiles",
    r"C:\SoftRobot_Sim\Ansys_LHS_Profiles"
]

# Where you want the 4-view masks saved
EXPORT_BASE_DIR = r"C:\SoftRobot_Sim\Exported_Masks"

# These must match your Mechanical Tree EXACTLY
P_LOADS = ["Pressure_1", "Pressure_2", "Pressure_3"]

# ==========================================
# --- 2. SETUP HOOKS ---
# ==========================================
# Ensure export directory exists
if not os.path.exists(EXPORT_BASE_DIR):
    os.makedirs(EXPORT_BASE_DIR)

analysis = ExtAPI.DataModel.Project.Model.Analyses[0]

# Find the pressure objects once to save time
load_objs = []
for name in P_LOADS:
    try:
        load = [c for c in analysis.Children if c.Name == name][0]
        load_objs.append(load)
    except:
        raise Exception("ERROR: Could not find load named '" + name + "'. Check your tree!")

# ==========================================
# --- 3. THE AUTOMATION LOOP ---
# ==========================================
for folder in DATA_FOLDERS:
    if not os.path.exists(folder):
        print("Skipping folder - not found: " + folder)
        continue

    for filename in os.listdir(folder):
        if not filename.endswith(".csv"):
            continue
            
        print("--- Processing: " + filename + " ---")
        filepath = os.path.join(folder, filename)
        run_name = filename.replace(".csv", "")

        times = []
        p_data = [[], [], []]

        # Read the CSV (Native file IO for IronPython compatibility)
        with open(filepath, 'r') as f:
            lines = f.readlines()[1:] # Skip header
            for line in lines:
                cols = line.strip().split(',')
                # Map frames to 30 FPS real-world time (0.033s per frame)
                # We start at 0.033 so the first frame isn't at T=0
                t_val = (float(cols[0]) * 0.033) + 0.033
                times.append(Quantity(str(t_val) + " [s]"))
                
                # Assign pressures for all 3 chambers
                p_data[0].append(Quantity(str(float(cols[1])) + " [kPa]"))
                p_data[1].append(Quantity(str(float(cols[2])) + " [kPa]"))
                p_data[2].append(Quantity(str(float(cols[3])) + " [kPa]"))

        # Inject Data into Ansys Tabular Loads
        for i in range(3):
            load_objs[i].Magnitude.Inputs[0].DiscreteValues = times
            load_objs[i].Magnitude.Output.DiscreteValues = p_data[i]

        # Solve the FEA
        print("Solving " + run_name + "...")
        analysis.Solve()
        
        # ==========================================
        # --- 4. EXPORT 4-VIEW MASK SEQUENCES ---
        # ==========================================
        # This assumes you have your 4 Viewports or Views named 
        # in the Graphics window. If not, it exports the current active view.
        
        # Create subfolder for this specific run
        run_export_dir = os.path.join(EXPORT_BASE_DIR, run_name)
        if not os.path.exists(run_export_dir):
            os.makedirs(run_export_dir)

        # We export the final state (Step 60). 
        # To export the whole video sequence, you would need to loop through time steps.
        # For our 3D TriPlane training, we just need the final deformed state per run.
        views = ["Side1", "Side2", "Side3", "Side4"]
        
        for view in views:
            # Tip: You'll need to manually set the camera once in the UI 
            # before running this to ensure 'Side1' etc. look correct.
            image_name = run_name + "_" + view + ".png"
            image_full_path = os.path.join(run_export_dir, image_name)
            
            # Export command
            Graphics.ExportImage(image_full_path, GraphicsImageExportFormat.PNG)
            
        print("Finished: " + run_name + "\n")

print("All simulations and exports complete!")