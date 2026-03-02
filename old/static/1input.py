import os
import System 

# --- CONFIGURATION ---
desktop_path = System.Environment.GetFolderPath(System.Environment.SpecialFolder.Desktop)
output_folder = os.path.join(desktop_path, "Ansys_Videos")

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

print("Saving videos to: " + output_folder)

# Define pressures (Pa)
pressure_values = [10000, 50000, 100000] 

# --- HELPER ---
def find_object_by_name(parent_object, name_to_find):
    for child in parent_object.Children:
        if child.Name == name_to_find:
            return child
    return None

# --- MAIN ---
analysis = ExtAPI.DataModel.Project.Model.Analyses[0]
pressure_load = find_object_by_name(analysis, "Pressure")
dir_deformation = find_object_by_name(analysis.Solution, "Directional Deformation")

if pressure_load and dir_deformation:
    for p_val in pressure_values:
        try:
            print("Setting Pressure to {} Pa".format(p_val))
            q = Quantity(str(p_val) + " [Pa]")
            pressure_load.Magnitude.Output.SetDiscreteValue(0, q)
            
            print("Solving...")
            analysis.Solve()
            
            # --- VIDEO EXPORT ---
            # NOTE: We force .avi extension in the filename
            video_name = "Deform_{}Pa.avi".format(p_val)
            file_path = os.path.join(output_folder, video_name)
            
            # Use the explicit Enum for AVI
            # This should bypass the MP4 restriction
            dir_deformation.ExportAnimation(file_path, GraphicsAnimationExportFormat.AVI)
            
            print("Saved: " + file_path)
            
        except Exception as e:
            print("Error processing {}: {}".format(p_val, str(e)))
else:
    print("Error: Could not find 'Pressure' or 'Directional Deformation'.")

print("Done.")
