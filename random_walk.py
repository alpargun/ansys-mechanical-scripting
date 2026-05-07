import os
import System
import time
import datetime
import random
from Ansys.Mechanical.DataModel.Enums import GraphicsAnimationExportFormat, ObjectState, AutomaticTimeStepping, ViewOrientationType, LineSearchType, SolverType
from Ansys.ACT.Math import Vector3D 

# ==========================================
# --- CONFIGURATION (RANDOM WALK PROFILE) ---
# ==========================================
# We enforce exactly 1 Pa as the absolute physical floor to prevent vacuum crashes [cite: 2026-02-17].
MIN_PRESSURE = 1       
MAX_PRESSURE = 100000  

# Random Walk Specifics
NUM_RANDOM_VIDEOS = 15     # 15 videos of 30 seconds is a massive continuous dataset
DURATION = 30.0            # 30-second long continuous wandering
WAYPOINT_INTERVAL = 3.0    # Changes pressure target every 3 seconds to ensure smooth, achievable ramps

FPS = 30
VIDEO_FRAMES = int(DURATION * FPS) # Yields exactly 900 frames per video

GROWTH_FACTOR = 2.0     # Keeps the camera bounds identical to the old 125-case dataset
CAMERA_WAIT_TIME = 0.5 

# Setup output directories on the Desktop
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
base_folder = os.path.join(desktop_path, "SoftRobot_Dataset_RandomWalk")
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
main_output_folder = os.path.join(base_folder, "Run_RandomWalk_" + timestamp)

if not os.path.exists(main_output_folder):
    os.makedirs(main_output_folder)

failure_log_path = os.path.join(main_output_folder, "failed_cases.txt")
print("Saving Data to: " + main_output_folder)

# ==========================================
# --- HELPER FUNCTIONS ---
# ==========================================
def setup_analysis_steps(analysis, times_list):
    """Configures the Newton-Raphson solver for dynamic multi-step waypoints."""
    print("--- Configuring Analysis Steps for Random Walk ---")
    settings = analysis.AnalysisSettings
    
    # Create a solver step for every single waypoint in the random walk
    num_steps = len(times_list) - 1
    settings.NumberOfSteps = num_steps
    
    for i in range(num_steps):
        step_num = i + 1
        settings.SetStepEndTime(step_num, Quantity(str(times_list[step_num]) + " [s]"))
        
    settings.LargeDeflection = True
    settings.LineSearch = LineSearchType.On
    settings.SolverType = SolverType.Iterative 
    
    for step in range(1, num_steps + 1):
        settings.SetAutomaticTimeStepping(step, AutomaticTimeStepping.On)
        # Gentler initial start (100 substeps) prevents shockwaves on extreme asymmetric bends
        settings.SetInitialSubsteps(step, 100)  
        settings.SetMinimumSubsteps(step, 20)   
        # Massive bisection headroom (5000) so the solver can survive element crushing
        settings.SetMaximumSubsteps(step, 5000) 
        
    print("    Steps configured. Iterative Solver & Line Search ON.")

def generate_random_trajectory():
    """Builds a continuous, random path for a single bellow that starts/ends at 1 Pa."""
    times = [0.0]
    pressures = [MIN_PRESSURE]
    
    current_time = WAYPOINT_INTERVAL
    while current_time < DURATION:
        times.append(current_time)
        # Pick a random pressure between 1 Pa and 100 kPa
        rand_p = random.uniform(MIN_PRESSURE, MAX_PRESSURE)
        pressures.append(rand_p)
        current_time += WAYPOINT_INTERVAL
        
    # Cap the end of the video safely at 1 Pa
    times.append(DURATION)
    pressures.append(MIN_PRESSURE)
    
    return times, pressures

def set_load_schedule(load_obj, times_list, pressures_list):
    """Injects the N-step dynamic pressure schedule into the Ansys Tabular Data array."""
    qty_times = [Quantity(str(t) + " [s]") for t in times_list]
    qty_pressures = [Quantity(str(p) + " [Pa]") for p in pressures_list]
    
    load_obj.Magnitude.Inputs[0].DiscreteValues = qty_times
    load_obj.Magnitude.Output.DiscreteValues = qty_pressures

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

def log_failure(case_num, error_msg):
    """Logs physically impossible configurations to a text file instead of crashing."""
    with open(failure_log_path, "a") as f:
        f.write("Random Case {} | Error: {}\n".format(case_num, error_msg))

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
    
    with open(file_path, "w") as f:
        f.write("Time(s), NodeID, X_und(m), Y_und(m), Z_und(m), DefX(m), DefY(m), DefZ(m), Strain\n")
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
                f.write("{:.4f}, {}, {:.6f}, {:.6f}, {:.6f}, {:.6e}, {:.6e}, {:.6e}, {:.6e}\n".format(
                    t, nid, nodes_cache[nid]['X'], nodes_cache[nid]['Y'], nodes_cache[nid]['Z'],
                    vals['dx'], vals['dy'], vals['dz'], vals['strain']
                ))

def blocking_solve(analysis_obj, solution_obj):
    """Triggers the solve and prevents Python from continuing until Ansys finishes the math."""
    print("      [Solver]: Clearing old results before starting...")
    solution_obj.ClearGeneratedData()
    time.sleep(0.5)
        
    print("      [Solver]: Starting Iterative Solve...")
    analysis_obj.Solve()
    
    solve_start = time.time()
    TIMEOUT = 7200 # Increased to 2 hours because 30s takes much longer than 8s
    
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
print("--- Starting Random Walk Continuous Dataset Recovery ---")

analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
solution = analysis.Solution
mesh_data = analysis.MeshData

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

    for case_num in range(1, NUM_RANDOM_VIDEOS + 1):
        try:
            print("\n=== Processing Random Walk {}/{} ===".format(case_num, NUM_RANDOM_VIDEOS))
            
            # Generate 3 independent random flight paths for the bellows
            times_1, pressures_1 = generate_random_trajectory()
            times_2, pressures_2 = generate_random_trajectory()
            times_3, pressures_3 = generate_random_trajectory()
            
            # The time steps are identical for all 3 arrays, so we just use times_1 to setup the solver
            setup_analysis_steps(analysis, times_1)
            
            # Apply the pressures
            set_load_schedule(p1, times_1, pressures_1)
            set_load_schedule(p2, times_2, pressures_2)
            set_load_schedule(p3, times_3, pressures_3)
            
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
                
                log_failure(case_num, msg)
                garbage_collect_solver_files(solution) 
                continue # Skip the exports and move to the next case safely
            
            # Formulate the folder names
            base_name = "RandomWalk_{}".format(case_num)
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
            log_failure(case_num, "Script Exception: " + str(e))
            garbage_collect_solver_files(solution) 

print("\nBatch Random Walk Run Finished.")
print("Videos and CSVs saved to: " + main_output_folder)