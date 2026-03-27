import os
import System
import time
import datetime
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState, AutomaticTimeStepping, ViewOrientationType, LineSearchType, SolverType
from Ansys.ACT.Math import Vector3D 

# ==========================================
# --- CONFIGURATION (10s 4-2-4 PROFILE) ---
# ==========================================
# We enforce exactly 1 Pa as the absolute physical floor to prevent vacuum crashes [cite: 2026-02-17].
MIN_PRESSURE = 1       
MAX_PRESSURE = 100001  
STEP_SIZE = 20000      

# The Viscoelastic "Golden Zone" Profile: 4s Ramp Up, 2s Static Hold (for creep), 4s Ramp Down
DURATION = 10.0         
GROWTH_FACTOR = 2.0     # Keeps the camera bounds identical to the old 125-case dataset
CAMERA_WAIT_TIME = 0.5 
FPS = 30
VIDEO_FRAMES = int(DURATION * FPS) # Yields exactly 300 frames per video

# Setup output directories on the Desktop
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
base_folder = os.path.join(desktop_path, "SoftRobot_Dataset_Hysteresis")
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
main_output_folder = os.path.join(base_folder, "Run_424_Profile_" + timestamp)

if not os.path.exists(main_output_folder):
    os.makedirs(main_output_folder)

failure_log_path = os.path.join(main_output_folder, "failed_cases.txt")
print("Saving Data to: " + main_output_folder)

# ==========================================
# --- HELPER FUNCTIONS ---
# ==========================================
def setup_analysis_steps(analysis):
    """Configures the Newton-Raphson solver for the 3 distinct phases of the 4-2-4 profile."""
    print("--- Configuring Analysis Steps for 4-2-4 Hysteresis Profile ---")
    settings = analysis.AnalysisSettings
    
    # 3 distinct steps match the inflation, the hold, and the deflation
    settings.NumberOfSteps = 3
    settings.SetStepEndTime(1, Quantity("4 [s]"))  # Phase 1: Ramp Up
    settings.SetStepEndTime(2, Quantity("6 [s]"))  # Phase 2: Static Hold
    settings.SetStepEndTime(3, Quantity("10 [s]")) # Phase 3: Ramp Down
    
    settings.LargeDeflection = True
    settings.LineSearch = LineSearchType.On
    settings.SolverType = SolverType.Iterative 
    
    for step in [1, 2, 3]:
        settings.SetAutomaticTimeStepping(step, AutomaticTimeStepping.On)
        # Gentler initial start (100 substeps) prevents shockwaves on extreme asymmetric bends
        settings.SetInitialSubsteps(step, 100)  
        settings.SetMinimumSubsteps(step, 20)   
        # Massive bisection headroom (5000) so the solver can survive element crushing
        settings.SetMaximumSubsteps(step, 5000) 
        
    print("    Steps configured. Iterative Solver & Line Search ON.")

def set_load_schedule(load_obj, peak_val):
    """Injects the 4-2-4 pressure schedule into the Ansys Tabular Data array."""
    times = [Quantity("0 [s]"), Quantity("4 [s]"), Quantity("6 [s]"), Quantity("10 [s]")]
    pressures = [
        Quantity(str(MIN_PRESSURE) + " [Pa]"), 
        Quantity(str(peak_val) + " [Pa]"), 
        Quantity(str(peak_val) + " [Pa]"), 
        Quantity(str(MIN_PRESSURE) + " [Pa]")
    ]
    load_obj.Magnitude.Inputs[0].DiscreteValues = times
    load_obj.Magnitude.Output.DiscreteValues = pressures

def get_interpolated_pressure(t_target, times_qty, pressures_qty):
    """Linearly interpolates pressure at any specific video frame timestamp."""
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
    """Logs physically impossible configurations to a text file instead of crashing."""
    with open(failure_log_path, "a") as f:
        f.write("Case {}: P1={}, P2={}, P3={} | Error: {}\n".format(case_num, p1, p2, p3, error_msg))

def find_object(parent, name):
    """Utility to grab an object from the Ansys Mechanical Project Tree by name."""
    for child in parent.Children:
        if child.Name == name: return child
    return None

def calculate_geometry_zoom(mesh_data):
    """Calculates the max dimension of the un-deformed mesh to set a consistent camera scale."""
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
    """Orients the camera and locks the focal distance for perfect pixel-to-pixel consistency."""
    cam = ExtAPI.Graphics.Camera
    try:
        cam.ViewVector = Vector3D(1, 1, 1)
        cam.UpVector = Vector3D(-1, 1, 0)
    except: pass 
    cam.ViewVector = Vector3D(view_x, view_y, view_z)
    cam.UpVector = Vector3D(up_x, up_y, up_z)
    cam.SetFit() 
    cam.SceneHeight = Quantity(master_zoom, "m") # Locks the zoom scale permanently
    time.sleep(CAMERA_WAIT_TIME)

def export_pressure_profile(case_folder, base_name, load_p1, load_p2, load_p3):
    """Saves the exact pressure applied at every single video frame for neural network training."""
    file_path = os.path.join(case_folder, base_name + "_PressureProfile.csv")
    time_steps = [0.0] + [round((i + 1) * (DURATION / VIDEO_FRAMES), 4) for i in range(VIDEO_FRAMES)]
    
    with open(file_path, "w") as f:
        f.write("Time(s), P1(kPa), P2(kPa), P3(kPa)\n")
        for t in time_steps:
            inst_p1 = get_interpolated_pressure(t, load_p1.Magnitude.Inputs[0].DiscreteValues, load_p1.Magnitude.Output.DiscreteValues) / 1000.0
            inst_p2 = get_interpolated_pressure(t, load_p2.Magnitude.Inputs[0].DiscreteValues, load_p2.Magnitude.Output.DiscreteValues) / 1000.0
            inst_p3 = get_interpolated_pressure(t, load_p3.Magnitude.Inputs[0].DiscreteValues, load_p3.Magnitude.Output.DiscreteValues) / 1000.0
            f.write("{:.4f}, {:.3f}, {:.3f}, {:.3f}\n".format(t, inst_p1, inst_p2, inst_p3))

def export_consolidated_data(case_folder, base_name, mesh_data, load_p1, load_p2, load_p3, def_x, def_y, def_z, strain, solution_obj):
    """Iterates through every time step, evaluates the mesh, and saves the nodal positions/strains."""
    file_path = os.path.join(case_folder, base_name + "_NodeData.csv")
    nodes_cache = {node.Id: {'X': node.X, 'Y': node.Y, 'Z': node.Z} for node in mesh_data.Nodes}
    time_steps = [round((i + 1) * (DURATION / VIDEO_FRAMES), 4) for i in range(VIDEO_FRAMES)]
    
    peak_p1 = float(load_p1.Magnitude.Output.DiscreteValues[1].Value)
    peak_p2 = float(load_p2.Magnitude.Output.DiscreteValues[1].Value)
    peak_p3 = float(load_p3.Magnitude.Output.DiscreteValues[1].Value)
    
    with open(file_path, "w") as f:
        f.write("Time(s), NodeID, X_und(m), Y_und(m), Z_und(m), DefX(m), DefY(m), DefZ(m), Strain, Peak_P1(Pa), Peak_P2(Pa), Peak_P3(Pa)\n")
        for t in time_steps:
            def_x.DisplayTime = Quantity(str(t) + " [s]")
            def_y.DisplayTime = Quantity(str(t) + " [s]")
            def_z.DisplayTime = Quantity(str(t) + " [s]")
            strain.DisplayTime = Quantity(str(t) + " [s]")
            
            solution_obj.EvaluateAllResults() # Forces Ansys to calculate the requested timestep
            
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
                    peak_p1, peak_p2, peak_p3
                ))

def blocking_solve(analysis_obj, solution_obj):
    """Triggers the solve and prevents Python from continuing until Ansys finishes the math."""
    print("      [Solver]: Clearing old results before starting...")
    solution_obj.ClearGeneratedData()
    time.sleep(0.5)
        
    print("      [Solver]: Starting Iterative Solve...")
    analysis_obj.Solve()
    
    solve_start = time.time()
    TIMEOUT = 7200 # Increased to 2 hours because 10s takes much longer than 2s
    
    while solution_obj.ObjectState != ObjectState.Solved:
        if time.time() - solve_start > TIMEOUT: return False, "Timeout"
        if solution_obj.ObjectState == ObjectState.SolveFailed: return False, "Divergence/Failure"
        time.sleep(1)
        
    return True, "Success"

def garbage_collect_solver_files(solution_obj):
    """Hard-flushes the RAM and Disk after every case to prevent memory fragmentation."""
    print("      [Cleanup]: Purging massive solver result files...")
    try:
        solution_obj.ClearGeneratedData()
        System.GC.Collect() # Forces the .NET environment to dump the nodal data from RAM
        time.sleep(1) 
        print("      [Cleanup]: Disk space recovered.")
    except Exception as e:
        print("      [Cleanup Warning]: Could not clear data. " + str(e))

# ==========================================
# --- MAIN EXECUTION ---
# ==========================================
print("--- Starting Video-Focused Hysteresis Dataset Recovery (216 Cases) ---")

analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
solution = analysis.Solution
mesh_data = analysis.MeshData

setup_analysis_steps(analysis)

# Compute the zoom once to guarantee every video has the exact same spatial dimensions
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

    # Generate the grid array (0k, 20k, 40k, 60k, 80k, 100k)
    raw_levels = range(0, MAX_PRESSURE + 1, STEP_SIZE)
    # Replaces 0 with MIN_PRESSURE to prevent negative volumes
    pressure_levels = [p if p >= MIN_PRESSURE else MIN_PRESSURE for p in raw_levels]
    
    load_cases = []
    # Generates exactly 216 combinations (6 * 6 * 6)
    for v1 in pressure_levels:
        for v2 in pressure_levels:
            for v3 in pressure_levels:
                load_cases.append((v1, v2, v3))

    for i, case in enumerate(load_cases):
        case_num = i + 1
        
        # --- RESUME LOGIC ---
        # Modify this number to skip previously successful solves
        if case_num < 168:
            continue
        # --------------------
        
        val_p1, val_p2, val_p3 = case
        
        try:
            print("\n=== Processing Case {}/216 [Peak: P1={}, P2={}, P3={}] ===".format(case_num, val_p1, val_p2, val_p3))
            
            # Apply the pressures to the 3 bellows
            set_load_schedule(p1, val_p1)
            set_load_schedule(p2, val_p2)
            set_load_schedule(p3, val_p3)
            
            success, msg = blocking_solve(analysis, solution)
            
            if not success:
                print("      !!! SOLVE FAILED: {} !!!".format(msg))
                print("      [Hard Reset]: Flushing corrupted MAPDL matrix...")
                
                # --- MAPDL FLUSH TRICK ---
                # When extreme asymmetric cases fail, the matrix gets trapped in a deformed state.
                # Toggling 'Suppressed' tricks Ansys into permanently wiping the old matrix 
                # and snapping the robot back to its un-deformed state, saving the 16GB RAM.
                p1.Suppressed = True
                p1.Suppressed = False
                
                log_failure(case_num, val_p1, val_p2, val_p3, msg)
                garbage_collect_solver_files(solution) 
                continue # Skip the exports and move to the next case safely
            
            # Formulate the folder names
            base_name = "3bellows_{}_{}_{}".format(val_p1, val_p2, val_p3)
            folder_name = "Case_{}_{}".format(case_num, base_name)
            case_folder = os.path.join(main_output_folder, folder_name)
            if not os.path.exists(case_folder): os.makedirs(case_folder)

            # Execute the massive exports
            print("      Exporting Time/Pressure Profile (kPa)...")
            export_pressure_profile(case_folder, base_name, p1, p2, p3)

            print("      Exporting Multi-Frame Data (Static Target Pressures)...")
            export_consolidated_data(case_folder, base_name, mesh_data, p1, p2, p3, def_x, def_y, def_z, eqv_strain, solution)

            print("      Exporting Videos...")
            total_def.Activate()
            total_def.DisplayTime = Quantity(str(DURATION) + " [s]") 
            total_def.EvaluateAllResults()
            time.sleep(CAMERA_WAIT_TIME)
            
            ExtAPI.Graphics.ResultAnimationOptions.NumberOfFrames = VIDEO_FRAMES
            ExtAPI.Graphics.ResultAnimationOptions.Duration = Quantity(DURATION, "s")
            
            # Export all 4 camera views precisely
            set_camera_custom(1, 0, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide1.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_custom(0, 1, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide2.avi"), GraphicsAnimationExportFormat.AVI)

            set_camera_custom(-1, 0, 0, 0, 0, 1, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewSide3.avi"), GraphicsAnimationExportFormat.AVI)
            
            set_camera_custom(0, 0, 1, 1, 0, 0, master_zoom)
            total_def.ExportAnimation(os.path.join(case_folder, base_name + "_ViewTop.avi"), GraphicsAnimationExportFormat.AVI)

            print("      Case {} Complete.".format(case_num))
            
            # Final RAM dump before moving to the next case
            garbage_collect_solver_files(solution)
            
        except Exception as e:
            # Catch-all for unexpected Python errors (like network drive disconnects)
            print("Error on Case {}: {}".format(case_num, str(e)))
            log_failure(case_num, val_p1, val_p2, val_p3, "Script Exception: " + str(e))
            garbage_collect_solver_files(solution) 

print("\nBatch Recovery Run Finished.")
print("Videos and CSVs saved to: " + main_output_folder)