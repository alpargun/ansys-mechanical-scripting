import os
import System
import time # Added for a tiny safety pause between switching tabs
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat

# --- CONFIGURATION ---
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
output_folder = os.path.join(desktop_path, "Ansys_Multi_Sim")

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Define Load Combinations (P1, P2, P3)
load_cases = [
    (0, 0, 50000),      # Case 1
    (0, 0, 100000),     # Case 2
    (50000, 0, 0),      # Case 3
    (100000, 0, 0),     # Case 4
    (0, 50000, 0),      # Case 5
    (50000, 50000, 50000) # Case 6
]

# --- HELPER FUNCTION ---
def find_object_by_name(parent_object, name_to_find):
    for child in parent_object.Children:
        if child.Name == name_to_find:
            return child
    return None

def export_csv_data(result_obj, file_path, mesh_data, inputs):
    """Simple CSV writer for the results"""
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

# --- MAIN SCRIPT ---
print("--- Starting Simulation ---")

# 1. Get Analysis & Objects
analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
mesh_data = analysis.MeshData

# Inputs
p1 = find_object_by_name(analysis, "Pressure")
p2 = find_object_by_name(analysis, "Pressure 2")
p3 = find_object_by_name(analysis, "Pressure 3")

# Outputs
res_deform = find_object_by_name(analysis.Solution, "Total Deformation") # Or "Directional Deformation"
res_strain = find_object_by_name(analysis.Solution, "Equivalent Elastic Strain")

if p1 and p2 and p3 and res_deform and res_strain:
    
    for i, inputs in enumerate(load_cases):
        case_num = i + 1
        val_p1, val_p2, val_p3 = inputs
        
        try:
            print("\nProcessing Case {}: {}, {}, {}".format(case_num, val_p1, val_p2, val_p3))
            
            # A. Update All 3 Pressures
            p1.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p1) + " [Pa]"))
            p2.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p2) + " [Pa]"))
            p3.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p3) + " [Pa]"))
            
            # B. Solve
            print("Solving...")
            analysis.Solve()
            
            # --- C. EXPORT DEFORMATION ---
            # Fix: We must Click/Activate the result so ANSYS shows it on screen
            res_deform.Activate() 
            ExtAPI.Graphics.Camera.SetFit() # Center the view
            time.sleep(0.5) # Tiny pause to let graphics load
            
            vid_path = os.path.join(output_folder, "Case{}_Deform.avi".format(case_num))
            res_deform.ExportAnimation(vid_path, GraphicsAnimationExportFormat.AVI)
            
            csv_path = os.path.join(output_folder, "Case{}_Deform.csv".format(case_num))
            export_csv_data(res_deform, csv_path, mesh_data, inputs)
            print("Saved Deformation")

            # --- D. EXPORT STRAIN ---
            # Fix: Switch tabs to Strain
            res_strain.Activate() 
            ExtAPI.Graphics.Camera.SetFit()
            time.sleep(0.5) 
            
            vid_path = os.path.join(output_folder, "Case{}_Strain.avi".format(case_num))
            res_strain.ExportAnimation(vid_path, GraphicsAnimationExportFormat.AVI)
            
            csv_path = os.path.join(output_folder, "Case{}_Strain.csv".format(case_num))
            export_csv_data(res_strain, csv_path, mesh_data, inputs)
            print("Saved Strain")
            
        except Exception as e:
            print("Error on Case {}: {}".format(case_num, str(e)))
else:
    print("Error: Could not find all objects. Check names: Pressure, Pressure 2, Pressure 3, Total Deformation, Equivalent Elastic Strain")

print("Done.")
