import os
import System 
import time
# REMOVED 'ViewOrientation' and 'DeformationScaling' to prevent import errors
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState

# --- CONFIGURATION ---
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
main_output_folder = os.path.join(desktop_path, "SoftRobot_WorldModel_Data")

if not os.path.exists(main_output_folder):
    os.makedirs(main_output_folder)

# Load Cases (P1, P2, P3)
load_cases = [
    (10, 10, 50000),      
    (10, 10, 100000),     
    (50000, 10, 10),      
    (100000, 10, 10),     
    (10, 50000, 10),      
    (50000, 50000, 50000) 
]

# --- HELPER FUNCTIONS ---
def find_object(parent, name):
    for child in parent.Children:
        if child.Name == name:
            return child
    return None

def export_csv(result_obj, file_path, mesh_data, inputs):
    with open(file_path, "w") as f:
        f.write("NodeID, X(m), Y(m), Z(m), Value, P1, P2, P3\n")
        if result_obj.PlotData:
            nodes = result_obj.PlotData["Node"]
            values = result_obj.PlotData["Values"]
            for i in range(len(nodes)):
                node = mesh_data.NodeById(int(nodes[i]))
                f.write("{}, {}, {}, {}, {}, {}, {}, {}\n".format(
                    nodes[i], node.X, node.Y, node.Z, values[i],
                    inputs[0], inputs[1], inputs[2]
                ))

def blocking_solve(analysis_obj, solution_obj):
    """ Forces a solve and BLOCKS until finished """
    print("      [Solver]: Clearing old results...")
    solution_obj.ClearGeneratedData()
    
    # Wait for invalidation
    start_time = time.time()
    while solution_obj.ObjectState == ObjectState.Solved:
        if time.time() - start_time > 10: break
        time.sleep(0.2)
        
    print("      [Solver]: Starting...")
    analysis_obj.Solve()
    
    # Wait for completion
    solve_start = time.time()
    while solution_obj.ObjectState != ObjectState.Solved:
        if time.time() - solve_start > 600: # 10 min timeout
            print("      [Error]: Solve Timed Out!")
            return False
        if solution_obj.ObjectState == ObjectState.Failed:
            print("      [Error]: Solve Failed!")
            return False
        time.sleep(1)
        
    print("      [Solver]: Finished.")
    return True

# --- MAIN SCRIPT ---
print("--- Starting World Model Dataset Generation ---")
analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
solution = analysis.Solution
mesh_data = analysis.MeshData

# 1. Find Objects
p1 = find_object(analysis, "Pressure")
p2 = find_object(analysis, "Pressure 2")
p3 = find_object(analysis, "Pressure 3")
total_def = find_object(solution, "Total Deformation")
def_x = find_object(solution, "Deformation X")
def_y = find_object(solution, "Deformation Y")
def_z = find_object(solution, "Deformation Z")
eqv_strain = find_object(solution, "Equivalent Elastic Strain")

if not (p1 and p2 and p3 and total_def and def_x and def_y and def_z and eqv_strain):
    print("Error: Ensure you have 'Total Deformation' and all other results in the Tree.")
else:
    # Set True Scale via Integer (1 = True Scale, 0 = Auto)
    # If this fails, we catch it so the script doesn't crash
    try:
        total_def.DeformationScaling = 1 
    except:
        print("Warning: Could not set True Scale via script. Please check GUI.")

    for i, case in enumerate(load_cases):
        case_num = i + 1
        val_p1, val_p2, val_p3 = case
        
        try:
            print("\n=== Processing Case {}/{} ===".format(case_num, len(load_cases)))
            
            # A. Create Folder
            folder_name = "Case_{}_3bellows_{}_{}_{}".format(case_num, val_p1, val_p2, val_p3)
            case_folder = os.path.join(main_output_folder, folder_name)
            if not os.path.exists(case_folder):
                os.makedirs(case_folder)
            
            # B. Update Inputs
            p1.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p1) + " [Pa]"))
            p2.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p2) + " [Pa]"))
            p3.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p3) + " [Pa]"))
            
            # C. Blocking Solve (Prevents Skipping)
            success = blocking_solve(analysis, solution)
            if not success: continue

            base_name = "3bellows_{}_{}_{}".format(val_p1, val_p2, val_p3)

            # --- VISUAL DATA: Total Deformation (Multi-View) ---
            print("   Exporting Multi-View Videos...")
            total_def.Activate()
            
            # View 1: Isometric (0)
            ExtAPI.Graphics.Camera.SetSpecificView(0) 
            ExtAPI.Graphics.Camera.SetFit()
            ExtAPI.Graphics.Camera.Zoom(0.7) # Zoom OUT 30% for safety
            time.sleep(1)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewIso.avi"), GraphicsAnimationExportFormat.AVI)
            
            # View 2: Front (1)
            ExtAPI.Graphics.Camera.SetSpecificView(1)
            ExtAPI.Graphics.Camera.SetFit()
            ExtAPI.Graphics.Camera.Zoom(0.7)
            time.sleep(1)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewFront.avi"), GraphicsAnimationExportFormat.AVI)
            
            # View 3: Right (6) - Note: standard is usually 6 for Right, 5 for Left
            ExtAPI.Graphics.Camera.SetSpecificView(6)
            ExtAPI.Graphics.Camera.SetFit()
            ExtAPI.Graphics.Camera.Zoom(0.7)
            time.sleep(1)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewRight.avi"), GraphicsAnimationExportFormat.AVI)

            # --- MATH DATA: CSV Ground Truth ---
            print("   Exporting CSV Data...")
            export_csv(def_x, os.path.join(case_folder, base_name + "_DefX.csv"), mesh_data, case)
            export_csv(def_y, os.path.join(case_folder, base_name + "_DefY.csv"), mesh_data, case)
            export_csv(def_z, os.path.join(case_folder, base_name + "_DefZ.csv"), mesh_data, case)
            export_csv(eqv_strain, os.path.join(case_folder, base_name + "_Strain.csv"), mesh_data, case)

            print("   Case {} Complete!".format(case_num))
            
        except Exception as e:
            print("Error on Case {}: {}".format(case_num, str(e)))

print("Batch Run Finished.")
