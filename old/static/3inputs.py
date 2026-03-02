import os
import System 
import time
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState

# --- CONFIGURATION ---
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
output_folder = os.path.join(desktop_path, "Ansys_Videos_3Inputs")

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Define Load Cases: (Pressure 1, Pressure 2, Pressure 3)
load_cases = [
    (10, 10, 50000),      # Case 1 (Changed 0 to 10 to ensure no zero-math errors)
    (10, 10, 100000),     # Case 2
    (50000, 10, 10),      # Case 3
    (100000, 10, 10),     # Case 4
    (10, 50000, 10),      # Case 5
    (50000, 50000, 50000) # Case 6
]

# --- HELPER FUNCTIONS ---
def find_object(parent, name):
    for child in parent.Children:
        if child.Name == name:
            return child
    return None

def blocking_solve(analysis_obj, solution_obj):
    """
    Forces a solve and BLOCKS execution until it is 100% finished.
    """
    # 1. Force Invalidation (Lightning Bolt)
    print("      -> Clearing old results...")
    solution_obj.ClearGeneratedData()
    
    # Wait for the status to actually change to 'Not Solved'
    # We loop until the Green Checkmark disappears
    start_time = time.time()
    while solution_obj.ObjectState == ObjectState.Solved:
        if time.time() - start_time > 10:
            print("      -> Warning: Could not verify clear. Attempting solve anyway.")
            break
        time.sleep(0.2)
        
    # 2. Trigger Solve
    print("      -> Sending Solve Command...")
    analysis_obj.Solve()
    
    # 3. Wait for Completion (Green Checkmark)
    print("      -> Waiting for Solver (this may take time)...")
    solve_start = time.time()
    while solution_obj.ObjectState != ObjectState.Solved:
        # Check for timeout (e.g., 5 minutes)
        if time.time() - solve_start > 300: 
            print("      -> Error: Solve timed out!")
            return False
        
        # Check if failed (Red X)
        if solution_obj.ObjectState == ObjectState.Failed:
            print("      -> Error: Solver Failed!")
            return False
            
        time.sleep(1) # Check every 1 second
        
    print("      -> Solver Finished Successfully.")
    return True

# --- MAIN SCRIPT ---
print("--- Starting Synchronized Simulation ---")
analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
solution = analysis.Solution

# Find Inputs
p1 = find_object(analysis, "Pressure")
p2 = find_object(analysis, "Pressure 2")
p3 = find_object(analysis, "Pressure 3")
total_deformation = find_object(solution, "Total Deformation")

if p1 and p2 and p3 and total_deformation:
    
    for i, case in enumerate(load_cases):
        case_num = i + 1
        val_p1, val_p2, val_p3 = case
        
        try:
            print("\nProcessing Case {}: {}, {}, {}".format(case_num, val_p1, val_p2, val_p3))
            
            # 1. Update Inputs
            # I used 10 Pa instead of 0 just to be safe, but 0 should work too.
            p1.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p1) + " [Pa]"))
            p2.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p2) + " [Pa]"))
            p3.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p3) + " [Pa]"))
            
            # 2. RUN THE BLOCKING SOLVE
            # The script CANNOT proceed past this line until Solver is done.
            success = blocking_solve(analysis, solution)
            
            if not success:
                print("Skipping export for Case {} due to solve failure.".format(case_num))
                continue

            # 3. EXPORT
            video_name = "Case{}_Deform.avi".format(case_num)
            file_path = os.path.join(output_folder, video_name)
            
            # Center Camera
            ExtAPI.Graphics.Camera.SetFit()
            
            # Export
            total_deformation.ExportAnimation(file_path, GraphicsAnimationExportFormat.AVI)
            print("   Saved Video.")
            
        except Exception as e:
            print("Error on Case {}: {}".format(case_num, str(e)))
else:
    print("Error: Could not find all objects.")

print("Done.")
