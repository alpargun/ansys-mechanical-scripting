import os
import System
import time
import datetime
import csv
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState, AutomaticTimeStepping, ViewOrientationType, LineSearchType, SolverType
from Ansys.ACT.Math import Vector3D 

# ==========================================
# --- CONFIGURATION (60s at 30 FPS) ---
# ==========================================
MIN_PRESSURE = 1       
DURATION = 60.0        
FPS = 30
VIDEO_FRAMES = DURATION * FPS # 60s * 30 FPS = 1800 Frames
GROWTH_FACTOR = 2.0    
CAMERA_WAIT_TIME = 0.5 

desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
base_folder = os.path.join(desktop_path, "SoftRobot_Dataset_Hysteresis")
csv_input_path = os.path.join(desktop_path, "Staircase_Creep_Test.csv")

timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
main_output_folder = os.path.join(base_folder, "Run_Staircase_30FPS_" + timestamp)

if not os.path.exists(main_output_folder):
    os.makedirs(main_output_folder)

print("Reading Data from: " + csv_input_path)
print("Saving 30 FPS Visual Data to: " + main_output_folder)

# ==========================================
# --- HELPER FUNCTIONS ---
# ==========================================
def find_object(parent, name):
    for child in parent.Children:
        if child.Name == name: return child
    return None

def setup_analysis_steps(analysis):
    print("--- Configuring Analysis for 60-Second Dynamic Solve ---")
    settings = analysis.AnalysisSettings
    settings.NumberOfSteps = 1
    settings.SetStepEndTime(1, Quantity(str(DURATION) + " [s]"))
    
    settings.LargeDeflection = True
    settings.LineSearch = LineSearchType.On
    settings.SolverType = SolverType.Iterative 
    
    settings.SetAutomaticTimeStepping(1, AutomaticTimeStepping.On)
    settings.SetInitialSubsteps(1, 600)   
    settings.SetMinimumSubsteps(1, 60)    
    settings.SetMaximumSubsteps(1, 12000)  
        
    print("    Dynamic Auto-Stepping configured.")

def load_csv_to_tabular_data(csv_path, load_p1, load_p2, load_p3):
    print("    Parsing CSV directly into Ansys Tabular Data...")
    times, p1_vals, p2_vals, p3_vals = [], [], [], []
    
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader) 
        for row in reader:
            t_val = float(row[0])
            v1 = max(float(row[1]) * 1000.0, float(MIN_PRESSURE))
            v2 = max(float(row[2]) * 1000.0, float(MIN_PRESSURE))
            v3 = max(float(row[3]) * 1000.0, float(MIN_PRESSURE))
            
            times.append(Quantity(str(t_val) + " [s]"))
            p1_vals.append(Quantity(str(v1) + " [Pa]"))
            p2_vals.append(Quantity(str(v2) + " [Pa]"))
            p3_vals.append(Quantity(str(v3) + " [Pa]"))
            
    load_p1.Magnitude.Inputs[0].DiscreteValues = times
    load_p1.Magnitude.Output.DiscreteValues = p1_vals
    
    load_p2.Magnitude.Inputs[0].DiscreteValues = times
    load_p2.Magnitude.Output.DiscreteValues = p2_vals
    
    load_p3.Magnitude.Inputs[0].DiscreteValues = times
    load_p3.Magnitude.Output.DiscreteValues = p3_vals

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

def blocking_solve(analysis_obj, solution_obj):
    print("      [Solver]: Clearing old results before starting...")
    solution_obj.ClearGeneratedData()
    time.sleep(0.5)
        
    print("      [Solver]: Starting Massive 60-Second Iterative Solve...")
    analysis_obj.Solve()
    
    solve_start = time.time()
    TIMEOUT = 86400 
    
    while solution_obj.ObjectState != ObjectState.Solved:
        if time.time() - solve_start > TIMEOUT: return False, "Timeout"
        if solution_obj.ObjectState == ObjectState.SolveFailed: return False, "Divergence/Failure"
        time.sleep(5)
        
    return True, "Success"

def get_interpolated_pressure(t_target, times_qty, pressures_qty):
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

def export_30fps_pressure_profile(output_folder, base_name, load_p1, load_p2, load_p3):
    file_path = os.path.join(output_folder, base_name + "_PressureProfile.csv")
    time_steps = [round((i + 1) * (DURATION / VIDEO_FRAMES), 5) for i in range(VIDEO_FRAMES)]
    
    with open(file_path, "w") as f:
        f.write("Time(s), P1(kPa), P2(kPa), P3(kPa)\n")
        for t in time_steps:
            inst_p1 = get_interpolated_pressure(t, load_p1.Magnitude.Inputs[0].DiscreteValues, load_p1.Magnitude.Output.DiscreteValues) / 1000.0
            inst_p2 = get_interpolated_pressure(t, load_p2.Magnitude.Inputs[0].DiscreteValues, load_p2.Magnitude.Output.DiscreteValues) / 1000.0
            inst_p3 = get_interpolated_pressure(t, load_p3.Magnitude.Inputs[0].DiscreteValues, load_p3.Magnitude.Output.DiscreteValues) / 1000.0
            f.write("{:.5f}, {:.3f}, {:.3f}, {:.3f}\n".format(t, inst_p1, inst_p2, inst_p3))

def export_safe_tip_data(output_folder, base_name, total_def, solution_obj):
    file_path = os.path.join(output_folder, base_name + "_TipDisplacement.csv")
    time_steps = [round((i + 1) * (DURATION / VIDEO_FRAMES), 5) for i in range(VIDEO_FRAMES)]
    
    with open(file_path, "w") as f:
        f.write("Time(s), Max_Deformation(m)\n")
        for t in time_steps:
            total_def.DisplayTime = Quantity(str(t) + " [s]")
            solution_obj.EvaluateAllResults()
            max_val = total_def.Maximum.Value 
            f.write("{:.5f}, {:.6f}\n".format(t, max_val))

# ==========================================
# --- MAIN EXECUTION ---
# ==========================================
print("--- Starting Staircase System ID (30 FPS) ---")

if not os.path.exists(csv_input_path):
    print("ERROR: Could not find {} on the Desktop!".format(csv_input_path))
else:
    analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
    solution = analysis.Solution
    mesh_data = analysis.MeshData

    setup_analysis_steps(analysis)
    master_zoom = calculate_geometry_zoom(mesh_data)

    p1 = find_object(analysis, "Pressure")
    p2 = find_object(analysis, "Pressure 2")
    p3 = find_object(analysis, "Pressure 3")
    total_def = find_object(solution, "Total Deformation")

    if not (p1 and p2 and p3 and total_def):
        print("Error: Missing required loads or Deformation results.")
    else:
        try: total_def.DeformationScaling = 1 
        except: pass

        load_csv_to_tabular_data(csv_input_path, p1, p2, p3)
        
        success, msg = blocking_solve(analysis, solution)
        if not success:
            print("      !!! SOLVE FAILED: {} !!!".format(msg))
        else:
            base_name = "Staircase_30FPS_60s"
            
            print("      Exporting 30 FPS Pressure Profile...")
            export_30fps_pressure_profile(main_output_folder, base_name, p1, p2, p3)

            print("      Exporting Tip Displacement CSV (1800 Frames)...")
            export_safe_tip_data(main_output_folder, base_name, total_def, solution)

            print("      Exporting Videos ({} Frames)...".format(VIDEO_FRAMES))
            total_def.Activate()
            total_def.DisplayTime = Quantity(str(DURATION) + " [s]") 
            total_def.EvaluateAllResults()
            time.sleep(CAMERA_WAIT_TIME)
            
            ExtAPI.Graphics.ResultAnimationOptions.NumberOfFrames = VIDEO_FRAMES
            ExtAPI.Graphics.ResultAnimationOptions.Duration = Quantity(DURATION, "s")
            
            set_camera_custom(1, 0, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(main_output_folder, base_name + "_ViewSide1.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_custom(0, 1, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(main_output_folder, base_name + "_ViewSide2.avi"), GraphicsAnimationExportFormat.AVI)

            set_camera_custom(-1, 0, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(main_output_folder, base_name + "_ViewSide3.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_custom(0, 0, 1, 1, 0, 0, master_zoom)
            total_def.ExportAnimation(os.path.join(main_output_folder, base_name + "_ViewTop.avi"), GraphicsAnimationExportFormat.AVI)

            print("\nStaircase Run Finished. 30 FPS Files Generated.")