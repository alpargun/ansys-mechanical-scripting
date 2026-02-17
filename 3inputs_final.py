import os
import System 
import time
import datetime 
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState, ViewOrientationType

# --- CONFIGURATION ---
# 1. Dataset Generation Settings
MIN_PRESSURE = 1 # Starting pressure (Pa) (ANSYS doesn't allow zero for pressure BCs)
MAX_PRESSURE = 150000 # Maximum pressure (Pa)
STEP_SIZE = 30000 # Step size (Pa)

# 2. Camera Settings
GROWTH_FACTOR = 1.5      # Safety margin for zoom
CAMERA_WAIT_TIME = 0.3   # Wait time for graphics to update (seconds)

# 3. Output Paths
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
base_folder = os.path.join(desktop_path, "SoftRobot_Dataset")

timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
main_output_folder = os.path.join(base_folder, "Run_" + timestamp)

if not os.path.exists(main_output_folder):
    os.makedirs(main_output_folder)

print("Saving Data to: " + main_output_folder)

# --- AUTOMATIC LOAD CASE GENERATOR ---
# Generates all combinations: [0,0,0], [0,0,50k] ... [150k, 150k, 150k]
load_cases = []
pressure_levels = range(MIN_PRESSURE, MAX_PRESSURE + 1, STEP_SIZE)

# Replace 0 with 1 Pa as ANSYS does not allow 0 pressure.
pressure_levels = [p if p > 0 else 1 for p in pressure_levels]

# Permute through all combinations of pressures for the 3 bellows
print("--- Generating Load Cases ---")
for p1 in pressure_levels:
    for p2 in pressure_levels:
        for p3 in pressure_levels:
            load_cases.append((p1, p2, p3))

print("   Pressure Levels: {}".format(list(pressure_levels)))
print("   Total Cases Generated: {}".format(len(load_cases)))


# --- HELPER FUNCTIONS ---
def find_object(parent, name):
    for child in parent.Children:
        if child.Name == name: return child
    return None

def calculate_geometry_zoom(mesh_data):
    """ Scans mesh to find max dimension and calculates a fixed zoom level """
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
            
    len_x = max_x - min_x
    len_y = max_y - min_y
    len_z = max_z - min_z
    max_dim = max(len_x, len_y, len_z)
    master_zoom = max_dim * GROWTH_FACTOR
    print("   Master Zoom: {:.3f} m".format(master_zoom))
    return master_zoom

def set_camera_safe(view_type, master_zoom):
    """ Sets view, centers robot, locks zoom, and waits for redraw """
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
    print("      [Solver]: Clearing old results...")
    solution_obj.ClearGeneratedData()
    start_time = time.time()
    while solution_obj.ObjectState == ObjectState.Solved:
        if time.time() - start_time > 10: break
        time.sleep(0.5)
    print("      [Solver]: Starting...")
    analysis_obj.Solve()
    solve_start = time.time()
    while solution_obj.ObjectState != ObjectState.Solved:
        if time.time() - solve_start > 600: return False
        if solution_obj.ObjectState == ObjectState.Failed: return False
        time.sleep(1)
    print("      [Solver]: Finished.")
    return True

# --- MAIN SCRIPT ---
print("--- Starting Automated Soft Robot Dataset ---")
analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
solution = analysis.Solution
mesh_data = analysis.MeshData

# 1. Calculate Zoom ONCE
master_zoom = calculate_geometry_zoom(mesh_data)

# 2. Find Tree Items
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
    try: total_def.DeformationScaling = 1 
    except: pass

    # Loop through the automatically generated cases
    for i, case in enumerate(load_cases):
        case_num = i + 1
        val_p1, val_p2, val_p3 = case
        
        try:
            print("\n=== Processing Case {}/{} [P1={}, P2={}, P3={}] ===".format(
                case_num, len(load_cases), val_p1, val_p2, val_p3))
            
            folder_name = "Case_{}_3bellows_{}_{}_{}".format(case_num, val_p1, val_p2, val_p3)
            case_folder = os.path.join(main_output_folder, folder_name)
            if not os.path.exists(case_folder): os.makedirs(case_folder)
            
            base_name = "3bellows_{}_{}_{}".format(val_p1, val_p2, val_p3)

            p1.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p1) + " [Pa]"))
            p2.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p2) + " [Pa]"))
            p3.Magnitude.Output.SetDiscreteValue(0, Quantity(str(val_p3) + " [Pa]"))
            
            if not blocking_solve(analysis, solution): continue

            # Export CSVs
            export_csv(def_x, os.path.join(case_folder, base_name + "_DefX.csv"), mesh_data, case)
            export_csv(def_y, os.path.join(case_folder, base_name + "_DefY.csv"), mesh_data, case)
            export_csv(def_z, os.path.join(case_folder, base_name + "_DefZ.csv"), mesh_data, case)
            export_csv(eqv_strain, os.path.join(case_folder, base_name + "_Strain.csv"), mesh_data, case)

            # Export Videos (Z-Up Mapped)
            print("   Exporting Videos...")
            total_def.Activate()
            time.sleep(CAMERA_WAIT_TIME) 
            
            # Front (Robot Standing Up) -> ANSYS Bottom
            set_camera_safe(ViewOrientationType.Bottom, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewFront.avi"), GraphicsAnimationExportFormat.AVI)
            
            # Top (Gripper Face) -> ANSYS Front
            set_camera_safe(ViewOrientationType.Front, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewTop.avi"), GraphicsAnimationExportFormat.AVI)

            # Side (Profile) -> ANSYS Right
            set_camera_safe(ViewOrientationType.Right, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide.avi"), GraphicsAnimationExportFormat.AVI)
            
            # Iso View
            set_camera_safe(ViewOrientationType.Iso, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewIso.avi"), GraphicsAnimationExportFormat.AVI)

            print("   Case {} Complete!".format(case_num))
            
        except Exception as e:
            print("Error on Case {}: {}".format(case_num, str(e)))

print("Batch Run Finished. Data saved to: " + main_output_folder)