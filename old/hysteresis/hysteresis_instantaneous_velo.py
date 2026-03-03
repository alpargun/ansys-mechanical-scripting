import os
import System
import time
import datetime
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState, AutomaticTimeStepping, ViewOrientationType, LineSearchType
from Ansys.ACT.Math import Vector3D 

# ==========================================
# --- CONFIGURATION ---
# ==========================================
MIN_PRESSURE = 1       
MAX_PRESSURE = 100000  
STEP_SIZE = 25000      

GROWTH_FACTOR = 2.0    
CAMERA_WAIT_TIME = 0.5 
VIDEO_FRAMES = 60      

desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
base_folder = os.path.join(desktop_path, "SoftRobot_Dataset_Hysteresis")

timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
main_output_folder = os.path.join(base_folder, "Run_" + timestamp)

if not os.path.exists(main_output_folder):
    os.makedirs(main_output_folder)

failure_log_path = os.path.join(main_output_folder, "failed_cases.txt")

print("Saving Data to: " + main_output_folder)

# ==========================================
# --- HELPER FUNCTIONS ---
# ==========================================

def setup_analysis_steps(analysis):
    print("--- Configuring Analysis Steps for Extreme Bending (100k Pa) ---")
    settings = analysis.AnalysisSettings
    settings.NumberOfSteps = 2
    settings.SetStepEndTime(1, Quantity("1 [s]"))
    settings.SetStepEndTime(2, Quantity("2 [s]"))
    
    settings.LargeDeflection = True
    settings.LineSearch = LineSearchType.On
    
    for step in [1, 2]:
        settings.SetAutomaticTimeStepping(step, AutomaticTimeStepping.On)
        settings.SetInitialSubsteps(step, 25)  
        settings.SetMinimumSubsteps(step, 10)   
        settings.SetMaximumSubsteps(step, 400) # Fast-fail ceiling
        
    print("   Steps configured. Line Search ON.")

def set_load_schedule(load_obj, peak_val):
    times = [Quantity("0 [s]"), Quantity("1 [s]"), Quantity("2 [s]")]
    pressures = [Quantity("1 [Pa]"), Quantity(str(peak_val) + " [Pa]"), Quantity("1 [Pa]")]
    load_obj.Magnitude.Inputs[0].DiscreteValues = times
    load_obj.Magnitude.Output.DiscreteValues = pressures

def get_interpolated_pressure(t_target, times_qty, pressures_qty):
    """ 
    Future-Proof: Calculates the exact instantaneous pressure at any given time 't_target' 
    """
    times = [float(qty.Value) for qty in times_qty]
    pressures = [float(qty.Value) for qty in pressures_qty]
    
    if t_target <= times[0]: return pressures[0]
    if t_target >= times[-1]: return pressures[-1]
    
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i+1]
        p0, p1 = pressures[i], pressures[i+1]
        if t0 <= t_target <= t1:
            return p0 + (p1 - p0) * (t_target - t0) / (t1 - t0)
    return pressures[-1]

def log_failure(case_num, p1, p2, p3, error_msg):
    with open(failure_log_path, "a") as f:
        f.write("Case {}: P1={}, P2={}, P3={} | Error: {}\n".format(case_num, p1, p2, p3, error_msg))

def find_object(parent, name):
    for child in parent.Children:
        if child.Name == name: return child
    return None

def calculate_geometry_zoom(mesh_data):
    min_x, min_y, min_z = 1e9, 1e9, 1e9
    max_x, max_y, max_z = -1e9, -1e9, -1e9
    nodes = mesh_data.Nodes
    for i in range(nodes.Count):
        try:
            node = nodes[i]
            if node.X < min_x: min_x = node.X
            if node.X > max_x: max_x = node.X
            if node.Y < min_y: min_y = node.Y
            if node.Y > max_y: max_y = node.Y
            if node.Z < min_z: min_z = node.Z
            if node.Z > max_z: max_z = node.Z
        except: pass
    max_dim = max(max_x - min_x, max_y - min_y, max_z - min_z)
    return max_dim * GROWTH_FACTOR

def set_camera_custom(view_x, view_y, view_z, up_x, up_y, up_z, master_zoom):
    cam = ExtAPI.Graphics.Camera
    try:
        cam.ViewVector = Vector3D(1, 1, 1)
        cam.UpVector = Vector3D(-1, 1, 0)
    except: pass 
    
    cam.ViewVector = Vector3D(view_x, view_y, view_z)
    cam.UpVector = Vector3D(up_x, up_y, up_z)
    cam.SetFit() 
    cam.SceneHeight = Quantity(master_zoom, "m")
    time.sleep(CAMERA_WAIT_TIME)

def export_consolidated_data(case_folder, base_name, mesh_data, load_p1, load_p2, load_p3, def_x, def_y, def_z, strain):
    file_path = os.path.join(case_folder, base_name + "_Data.csv")
    
    # SPEED HACK: Pre-cache node geometry into a Python dictionary. 
    nodes_cache = {}
    for node in mesh_data.Nodes:
        nodes_cache[node.Id] = {'X': node.X, 'Y': node.Y, 'Z': node.Z}
        
    time_steps = [round((i + 1) * (2.0 / VIDEO_FRAMES), 4) for i in range(VIDEO_FRAMES)]
    
    with open(file_path, "w") as f:
        f.write("Time(s), NodeID, X_und(m), Y_und(m), Z_und(m), DefX(m), DefY(m), DefZ(m), Strain, Inst_P1(Pa), Inst_P2(Pa), Inst_P3(Pa)\n")
        
        for t in time_steps:
            inst_p1 = get_interpolated_pressure(t, load_p1.Magnitude.Inputs[0].DiscreteValues, load_p1.Magnitude.Output.DiscreteValues)
            inst_p2 = get_interpolated_pressure(t, load_p2.Magnitude.Inputs[0].DiscreteValues, load_p2.Magnitude.Output.DiscreteValues)
            inst_p3 = get_interpolated_pressure(t, load_p3.Magnitude.Inputs[0].DiscreteValues, load_p3.Magnitude.Output.DiscreteValues)
            
            def_x.DisplayTime = Quantity(str(t) + " [s]")
            def_y.DisplayTime = Quantity(str(t) + " [s]")
            def_z.DisplayTime = Quantity(str(t) + " [s]")
            strain.DisplayTime = Quantity(str(t) + " [s]")
            
            def_x.EvaluateAllResults()
            def_y.EvaluateAllResults()
            def_z.EvaluateAllResults()
            strain.EvaluateAllResults()
            
            frame_data = {}
            def extract_fast(res_obj, key):
                if res_obj.PlotData:
                    nodes = res_obj.PlotData["Node"]
                    vals = res_obj.PlotData["Values"]
                    for i in range(len(nodes)):
                        nid = int(nodes[i])
                        if nid not in frame_data:
                            if nid in nodes_cache:
                                frame_data[nid] = {'dx': 0, 'dy': 0, 'dz': 0, 'strain': 0}
                            else: continue 
                        frame_data[nid][key] = vals[i]
                        
            extract_fast(def_x, 'dx')
            extract_fast(def_y, 'dy')
            extract_fast(def_z, 'dz')
            extract_fast(strain, 'strain')
            
            for nid, vals in frame_data.items():
                f.write("{:.4f}, {}, {:.6f}, {:.6f}, {:.6f}, {:.6e}, {:.6e}, {:.6e}, {:.6e}, {:.2f}, {:.2f}, {:.2f}\n".format(
                    t, nid, nodes_cache[nid]['X'], nodes_cache[nid]['Y'], nodes_cache[nid]['Z'],
                    vals['dx'], vals['dy'], vals['dz'], vals['strain'],
                    inst_p1, inst_p2, inst_p3
                ))

def blocking_solve(analysis_obj, solution_obj):
    print("      [Solver]: Clearing old results...")
    solution_obj.ClearGeneratedData()
    time.sleep(0.5)
        
    print("      [Solver]: Starting...")
    analysis_obj.Solve()
    
    solve_start = time.time()
    TIMEOUT = 300 # Lowered to 5 minutes to fast-fail impossible edge cases
    
    while solution_obj.ObjectState != ObjectState.Solved:
        if time.time() - solve_start > TIMEOUT: return False, "Timeout"
        if solution_obj.ObjectState == ObjectState.SolveFailed: return False, "Divergence/Failure"
        time.sleep(1)
        
    return True, "Success"

# ==========================================
# --- MAIN EXECUTION ---
# ==========================================
print("--- Starting Video-Focused Hysteresis Dataset ---")

analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
solution = analysis.Solution
mesh_data = analysis.MeshData

setup_analysis_steps(analysis)
master_zoom = calculate_geometry_zoom(mesh_data)

p1 = find_object(analysis, "Pressure")
p2 = find_object(analysis, "Pressure 2")
p3 = find_object(analysis, "Pressure 3")
total_def = find_object(solution, "Total Deformation")
def_x = find_object(solution, "Deformation X")
def_y = find_object(solution, "Deformation Y")
def_z = find_object(solution, "Deformation Z")
eqv_strain = find_object(solution, "Equivalent Elastic Strain")

if not (p1 and p2 and p3 and total_def):
    print("Error: Missing 'Pressure' loads or 'Total Deformation' result.")
else:
    try: total_def.DeformationScaling = 1 
    except: pass

    load_cases = []
    pressure_levels = range(MIN_PRESSURE, MAX_PRESSURE + 1, STEP_SIZE)
    pressure_levels = [p if p > 0 else 1 for p in pressure_levels]
    
    for v1 in pressure_levels:
        for v2 in pressure_levels:
            for v3 in pressure_levels:
                load_cases.append((v1, v2, v3))

    for i, case in enumerate(load_cases):
        case_num = i + 1
        val_p1, val_p2, val_p3 = case
        
        try:
            print("\n=== Processing Case {}/{} [Peak: P1={}, P2={}, P3={}] ===".format(case_num, len(load_cases), val_p1, val_p2, val_p3))
            
            set_load_schedule(p1, val_p1)
            set_load_schedule(p2, val_p2)
            set_load_schedule(p3, val_p3)
            
            success, msg = blocking_solve(analysis, solution)
            if not success:
                print("      !!! SOLVE FAILED: {} !!!".format(msg))
                log_failure(case_num, val_p1, val_p2, val_p3, msg)
                continue 

            base_name = "3bellows_{}_{}_{}".format(val_p1, val_p2, val_p3)
            folder_name = "Case_{}_{}".format(case_num, base_name)
            case_folder = os.path.join(main_output_folder, folder_name)
            if not os.path.exists(case_folder): os.makedirs(case_folder)

            print("      Exporting Multi-Frame Data (Node Cached)...")
            export_consolidated_data(case_folder, base_name, mesh_data, p1, p2, p3, def_x, def_y, def_z, eqv_strain)

            print("      Exporting Videos...")
            total_def.Activate()
            total_def.DisplayTime = Quantity("2 [s]") 
            total_def.EvaluateAllResults()
            time.sleep(CAMERA_WAIT_TIME)
            
            ExtAPI.Graphics.ResultAnimationOptions.NumberOfFrames = VIDEO_FRAMES
            ExtAPI.Graphics.ResultAnimationOptions.Duration = Quantity(2, "s")
            
            set_camera_custom(1, 0, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide1.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_custom(0, 1, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide2.avi"), GraphicsAnimationExportFormat.AVI)

            set_camera_custom(-1, 0, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide3.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_custom(0, 0, 1, 1, 0, 0, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewTop.avi"), GraphicsAnimationExportFormat.AVI)

            print("      Case {} Complete.".format(case_num))
            
        except Exception as e:
            print("Error on Case {}: {}".format(case_num, str(e)))
            log_failure(case_num, val_p1, val_p2, val_p3, "Script Exception: " + str(e))

print("\nBatch Run Finished.")
print("Videos and CSVs saved to: " + main_output_folder)
