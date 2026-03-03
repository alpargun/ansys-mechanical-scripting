import time
from Ansys.Mechanical.DataModel.Enums import AutomaticTimeStepping, LineSearchType, SolverType, ObjectState

# ==========================================
# --- BENCHMARK CONFIGURATION ---
# ==========================================
# Asymmetric extreme bending to stress-test the solver
TEST_P1 = 100000 # 100 kPa
TEST_P2 = 1      # Minimum pressure
TEST_P3 = 100000 # 100 kPa

def set_benchmark_loads(load_obj, peak_val):
    times = [Quantity("0 [s]"), Quantity("1 [s]"), Quantity("2 [s]")]
    pressures = [Quantity("1 [Pa]"), Quantity(str(peak_val) + " [Pa]"), Quantity("1 [Pa]")]
    load_obj.Magnitude.Inputs[0].DiscreteValues = times
    load_obj.Magnitude.Output.DiscreteValues = pressures

def run_benchmark():
    print("\n=== Starting Single-Case Speed & Stability Benchmark ===")
    analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
    solution = analysis.Solution

    # --- 1. Apply Faster Solver Settings ---
    settings = analysis.AnalysisSettings
    settings.NumberOfSteps = 2
    settings.SetStepEndTime(1, Quantity("1 [s]"))
    settings.SetStepEndTime(2, Quantity("2 [s]"))
    
    settings.LargeDeflection = True
    settings.LineSearch = LineSearchType.On
    
    # CRITICAL CHANGE: Using Direct Solver for hyperelastic stability
    settings.SolverType = SolverType.Direct 
    
    # CRITICAL CHANGE: More aggressive time stepping
    for step in [1, 2]:
        settings.SetAutomaticTimeStepping(step, AutomaticTimeStepping.On)
        settings.SetInitialSubsteps(step, 10)  # Reduced from 20
        settings.SetMinimumSubsteps(step, 5)   # Reduced from 10
        settings.SetMaximumSubsteps(step, 1000)

    print("Settings applied: Direct Solver, Initial Substeps=10, Min Substeps=5.")

    # --- 2. Find Load Objects ---
    def find_object(parent, name):
        for child in parent.Children:
            if child.Name == name: return child
        return None

    p1 = find_object(analysis, "Pressure")
    p2 = find_object(analysis, "Pressure 2")
    p3 = find_object(analysis, "Pressure 3")

    if not (p1 and p2 and p3):
        print("Error: Could not find all three Pressure objects.")
        return

    # --- 3. Set the Benchmark Load ---
    set_benchmark_loads(p1, TEST_P1)
    set_benchmark_loads(p2, TEST_P2)
    set_benchmark_loads(p3, TEST_P3)
    
    print("Loads applied: P1={}Pa, P2={}Pa, P3={}Pa".format(TEST_P1, TEST_P2, TEST_P3))

    # --- 4. Execute and Time the Solve ---
    solution.ClearGeneratedData()
    time.sleep(1)
    
    print("Solving... (Check Mechanical Solution Information for real-time progress)")
    start_time = time.time()
    analysis.Solve()
    
    TIMEOUT = 3600
    success = False
    
    while True:
        elapsed = time.time() - start_time
        if solution.ObjectState == ObjectState.Solved:
            success = True
            break
        if elapsed > TIMEOUT:
            print("\n!!! Benchmark Timeout after 60 minutes !!!")
            break
        if solution.ObjectState == ObjectState.SolveFailed:
            print("\n!!! Benchmark Diverged / Failed !!!")
            break
        time.sleep(2)

    end_time = time.time()
    total_time = end_time - start_time

    # --- 5. Report ---
    print("\n=== Benchmark Results ===")
    if success:
        print("Status: SUCCESS")
        print("Total Solve Time: {:.2f} seconds ({:.2f} minutes)".format(total_time, total_time/60.0))
        print("Conclusion: The faster settings are stable for extreme bending.")
    else:
        print("Status: FAILED")
        print("Time until failure: {:.2f} seconds".format(total_time))
        print("Conclusion: The direct solver/aggressive substeps caused divergence. Stick to your original conservative script.")

# Execute the benchmark
run_benchmark()
