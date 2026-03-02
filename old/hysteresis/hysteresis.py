import os
import System
import time
import datetime
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState, ViewOrientationType

# ==========================================
# --- CONFIGURATION (UPDATED FOR HYSTERESIS) ---
# ==========================================
# 1. Dataset Generation Settings
MIN_PRESSURE = 1       # Starting pressure (Pa)
MAX_PRESSURE = 60000   # UPDATED: Max pressure is now 60kPa
STEP_SIZE = 15000      # Step size (Pa) - Adjusted for 60k limit (gives ~4-5 steps)

# 2. Camera Settings
GROWTH_FACTOR = 2.0    # Zoom safety margin
CAMERA_WAIT_TIME = 0.5 # Increased slightly for heavier graphical updates

# 3. Output Paths
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
base_folder = os.path.join(desktop_path, "SoftRobot_Dataset_Hysteresis")

timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
main_output_folder = os.path.join(base_folder, "Run_" + timestamp)

if not os.path.exists(main_output_folder):
    os.makedirs(main_output_folder)

# Log file for skipped cases (Crucial for non-linear materials)
failure_log_path = os.path.join(main_output_folder, "failed_cases.txt")

print("Saving Data to: " + main_output_folder)

# ==========================================
# --- HELPER FUNCTIONS ---
# ==========================================

def log_failure(case_num, p1, p2, p3, error_msg):
    """ Writes failed cases to a text file so you don't lose track """
    with open(failure_log_path, "a") as f:
        f.write("Case {}: P1={}, P2={}, P3={} | Error: {}\n".format(case_num, p1, p2, p3, error_msg))

def find_object(parent, name):
    for child in parent.Children:
        if child.Name == name: return child
    return None

def calculate_geometry_zoom(mesh_data):
    """ Calculates fixed zoom level based on undeformed mesh max dimension """
    print("--- Calculating Master Zoom ---")
    min_x, min_y, min_z = 1e9, 1e9, 1e9
    max_x, max_y, max_z = -1e9, -1e9, -1e9
    
    nodes = mesh_data.Nodes
    count = nodes.Count
    
    for i in range(count):
        try:
            node = nodes[i]
            if node.X < min_x: min_x = node.X
            if node.X > max_x: max_x = node.X
            if node.Y < min_y: min_y = node.Y
            if node.Y > max_y: max_y = node.Y
            if node.Z < min_z: min_z = node.Z
            if node.Z > max_z: max_z = node.Z
        except:
            pass
            
    max_dim = max(max_x - min_x, max_y - min_y, max_z - min_z)
    master_zoom = max_dim * GROWTH_FACTOR
    print("   Master Zoom: {:.4f} m".format(master_zoom))
    return master_zoom

def set_camera_safe(view_type, master_zoom):
    """ Locks camera zoom using SceneHeight """
    cam = ExtAPI.Graphics.Camera
    cam.SetSpecificViewOrientation(view_type)
    cam.SetFit() 
    cam.SceneHeight = Quantity(master_zoom, "m")
    time.sleep(CAMERA_WAIT_TIME)

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
    """ Robust solver wait loop """
    print("      [Solver]: Clearing old results...")
    solution_obj.ClearGeneratedData()
    time.sleep(0.5)
        
    print("      [Solver]: Starting...")
    analysis_obj.Solve()
    
    solve_start = time.time()
    # Hysteresis can take longer, increased timeout to 15 mins (900s)
    TIMEOUT = 900 
    
    while solution_obj.ObjectState != ObjectState.Solved:
        if time.time() - solve_start > TIMEOUT: 
            return False, "Timeout"
        if solution_obj.ObjectState == ObjectState.Failed: 
            return False, "Divergence/Failure"
        time.sleep(1)
        
    return True, "Success"

# ==========================================
# --- MAIN EXECUTION ---
# ==========================================
print("--- Starting Hysteresis Dataset Gen (Max 60kPa) ---")

analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
solution = analysis.Solution
mesh_data = analysis.MeshData

# 1. Calc Zoom
master_zoom = calculate_geometry_zoom(mesh_data)

# 2. Objects
p1 = find_object(analysis, "Pressure")
p2 = find_object(analysis, "Pressure 2")
p3 = find_object(analysis, "Pressure 3")
total_def = find_object(solution, "Total Deformation")
def_x = find_object(solution, "Deformation X")
def_y = find_object(solution, "Deformation Y")
def_z = find_object(solution, "Deformation Z")
eqv_strain = find_object(solution, "Equivalent Elastic Strain")

# 3. Validation
if not (p1 and p2 and p3 and total_def and def_x and def_y and def_z and eqv_strain):
    print("Error: Missing objects in the Tree. Check naming.")
else:
    try: total_def.DeformationScaling = 1 
    except: pass

    # Generate Cases [1...60000]
    load_cases = []
    pressure_levels = range(MIN_PRESSURE, MAX_PRESSURE + 1, STEP_SIZE)
    pressure_levels = [p if p > 0 else 1 for p in pressure_levels]
    
    for v1 in pressure_levels:
        for v2 in pressure_levels:
            for v3 in pressure_levels:
                load_cases.append((v1, v2, v3))

    print("   Total Cases: {}".format(len(load_cases)))

    for i, case in enumerate(load_cases):
        case_num = i + 1
        val_p1, val_p2, val_p3 = case
        
        try:
            print("\n=== Processing Case {}/{} [P1={}, P2={}, P3={}] ===".format(
                case_num, len(load_cases), val_p1, val_p2, val_p3))
            
            base_name = "3bellows_{}_{}_{}".format(val_p1, val_p2, val_p3)
            folder_name = "Case_{}_{}".format(case_num, base_name)
            case_folder = os.path.join(main_output_folder, folder_name)

            # Set Loads
            p1.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p1) + " [Pa]"))
            p2.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p2) + " [Pa]"))
            p3.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p3) + " [Pa]"))
            
            # Solve
            success, msg = blocking_solve(analysis, solution)
            if not success:
                print("      !!! SOLVE FAILED: {} !!!".format(msg))
                log_failure(case_num, val_p1, val_p2, val_p3, msg)
                continue # Skip to next case, do not crash script

            # Create folder only if solve succeeded
            if not os.path.exists(case_folder): os.makedirs(case_folder)

            # Export Data
            export_csv(def_x, os.path.join(case_folder, base_name + "_DefX.csv"), mesh_data, case)
            export_csv(def_y, os.path.join(case_folder, base_name + "_DefY.csv"), mesh_data, case)
            export_csv(def_z, os.path.join(case_folder, base_name + "_DefZ.csv"), mesh_data, case)
            export_csv(eqv_strain, os.path.join(case_folder, base_name + "_Strain.csv"), mesh_data, case)

            # Export Videos
            print("      Exporting Videos...")
            total_def.Activate()
            time.sleep(CAMERA_WAIT_TIME)
            
            set_camera_safe(ViewOrientationType.Bottom, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewFront.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_safe(ViewOrientationType.Front, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewTop.avi"), GraphicsAnimationExportFormat.AVI)

            set_camera_safe(ViewOrientationType.Right, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_safe(ViewOrientationType.Iso, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewIso.avi"), GraphicsAnimationExportFormat.AVI)

            print("      Case {} Complete.".format(case_num))
            
        except Exception as e:
            print("Error on Case {}: {}".format(case_num, str(e)))
            log_failure(case_num, val_p1, val_p2, val_p3, "Script Exception: " + str(e))

print("\nBatch Run Finished.")
print("Check 'failed_cases.txt' in output folder for any skipped runs.")
