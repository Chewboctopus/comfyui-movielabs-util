import os
import re
import shutil
import subprocess
import tempfile

from .config import filesystem_config

def sanitize_path(path):
    if path is None:
        return path
    path = path.strip()
    if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
        return path[1:-1]
    return path

# --- NEW: Generic function to find the first file of a sequence ---
def find_sequence_in_folder(dir_path, allowed_extensions):
    for f in sorted(os.listdir(dir_path)):
        ext = os.path.splitext(f)[1].lower().strip('.')
        if ext in allowed_extensions:
            return os.path.join(dir_path, f)
    return None

# --- NEW: Generic function to list all files in a sequence ---
def list_sequence_files(dir_path, extension):
    ext_lower = extension.lower()
    return sorted([f for f in os.listdir(dir_path) if f.lower().endswith(f".{ext_lower}")])

def get_frame_number_from_filename(file_path):
    base, _ = os.path.splitext(os.path.basename(file_path))
    # --- MODIFIED REGEX ---
    # This regex is more robust. It finds numbers at the end of the filename,
    # even if they are followed by an optional underscore or period.
    match = re.search(r'(\d+)[._]?$', base)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract frame number from {file_path}")

# --- MODIFIED: Renamed and generalized from ensure_exr_sequence ---
def ensure_image_sequence(dir_path, extension):
    sequence_files = list_sequence_files(dir_path, extension)
    if not sequence_files:
        raise ValueError(f"No .{extension} files found in {dir_path}")

    frame_numbers_str = [get_frame_number_from_filename(f) for f in sequence_files]
    
    if len(set(len(f) for f in frame_numbers_str)) > 1:
        raise ValueError(f"Frame numbers in {dir_path} have inconsistent padding.")
    
    frame_padding = len(frame_numbers_str[0])
    frame_numbers_int = [int(f) for f in frame_numbers_str]
    original_start_frame = frame_numbers_int[0]

    for i, num in enumerate(frame_numbers_int):
        if num != original_start_frame + i:
            raise ValueError(f"Frame numbers in {dir_path} are not consecutive.")
            
    frame_offset = 0
    if not (100 < original_start_frame < 1000):
        frame_offset = 1001 - original_start_frame
        
    output_frames = {}
    for i, original_frame in enumerate(frame_numbers_int):
        new_frame = original_frame + frame_offset
        output_frames[str(new_frame).zfill(frame_padding)] = os.path.join(dir_path, sequence_files[i])
        
    return output_frames, original_start_frame, frame_padding, f".{extension}"

# (Keep all other functions like get_output_dir, get_task_dir, etc. the same)
def get_output_dir(shot_code):
    output_dir = filesystem_config["output_dir"]
    seq_code = shot_code[:-4]
    output_dir = [dir.format(SEQ_CODE=seq_code, SHOT_CODE=shot_code) for dir in output_dir]
    output_dir_path = os.path.join(*output_dir)
    os.makedirs(output_dir_path, exist_ok=True)
    return output_dir_path

def get_task_dir(output_dir, task_name):
    task_dir = filesystem_config["version_convention"][task_name]["parent_dir"]
    task_dir_path = os.path.join(output_dir, *task_dir)
    os.makedirs(task_dir_path, exist_ok=True)
    return task_dir_path

def format_string_to_version_regex(format_string):
    regex = re.escape(format_string)
    regex = regex.replace(r'\{VERSION_NUMBER\}', r'(\d{3})')
    regex = f'^{regex}$'
    return re.compile(regex)

def get_next_version(task_name, task_dir):
    version_numbers = []
    version_dir_format = filesystem_config["version_convention"][task_name]["version_dir"]
    if version_dir_format:
        version_regex = format_string_to_version_regex(version_dir_format)
        for f in os.listdir(task_dir):
            if os.path.isdir(os.path.join(task_dir, f)):
                match = version_regex.match(f)
                if match:
                    version_numbers.append(int(match.group(1)))
    else:
        version_pattern = re.compile(r"_v(\d{3})$")
        for f in os.listdir(task_dir):
            if os.path.isfile(os.path.join(task_dir, f)):
                base, _ = os.path.splitext(f)
                match = version_pattern.search(base)
                if match:
                    version_numbers.append(int(match.group(1)))
    if not version_numbers:
        return "001"
    else:
        return str(max(version_numbers) + 1).zfill(3)

def get_version_dir(task_name, task_dir, version_number):
    version_dir_format = filesystem_config["version_convention"][task_name]["version_dir"]
    if version_dir_format is None:
        return task_dir
    else:
        version_dir = version_dir_format.format(VERSION_NUMBER=version_number)
        version_dir_path = os.path.join(task_dir, version_dir)
        os.makedirs(version_dir_path, exist_ok=True)
        return version_dir_path

def get_file_name(kind, shot_code, task_name, version_number, frame_number=None):
    file_name_format = filesystem_config["version_convention"][task_name][kind]
    return file_name_format.format(SHOT_CODE=shot_code, VERSION_NUMBER=version_number, FRAME_NUMBER=frame_number)

def match_extension(task_name, is_original, file_path):
    kind = "original" if is_original else "proxy"
    file_type = filesystem_config["version_convention"][task_name][kind]
    
    if file_type == "image":
        supported_extensions = filesystem_config["version_convention"][task_name].get("image_ext", [])
    elif file_type == "file":
        supported_extensions = filesystem_config["version_convention"][task_name].get("file_ext", [])
    else:
        supported_extensions = filesystem_config["version_convention"][task_name].get("movie_ext", [])
    
    _, ext = os.path.splitext(file_path)
    ext = ext[1:].lower()
    if ext not in supported_extensions:
        raise ValueError(f"Unsupported {kind} file extension: {ext} for {task_name} task. Must be {', '.join(supported_extensions)}")
    return True

def mime_type_from_file_path(file_path):
    if not file_path: return "application/octet-stream"
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".tiff": "image/tiff", ".exr": "image/x-exr", ".dpx": "image/x-dpx"
    }.get(ext, "application/octet-stream")

def create_task_version(shot_code, task_name, original_file_path, proxy_file_path=None, auto_create_proxy=True):
    if not original_file_path or not (os.path.exists(original_file_path) or os.path.isdir(os.path.dirname(original_file_path))):
        raise FileNotFoundError(f"Original file or folder not found: {original_file_path}")

    # --- START OF FIX ---
    # Check the task's configuration to see if it's meant to be a sequence.
    task_config = filesystem_config["version_convention"][task_name]
    original_type = task_config.get("original") # e.g., "image" or "movie"
    
    # A task is sequential only if its filename format includes a frame number placeholder.
    is_sequence_task = False
    if original_type and f"{original_type}" in task_config:
        if "{FRAME_NUMBER}" in task_config[f"{original_type}"]:
            is_sequence_task = True

    # A submission is a sequence if the task is a sequence task AND
    # the path is a directory OR it's a file with frame numbers.
    is_sequence_submission = is_sequence_task and \
        (os.path.isdir(original_file_path) or \
         re.search(r'\d+', os.path.splitext(os.path.basename(original_file_path))[0]))
    # --- END OF FIX ---
    
    if not is_sequence_submission:
        match_extension(task_name, True, original_file_path)

    output_dir = get_output_dir(shot_code)
    task_dir = get_task_dir(output_dir, task_name)
    new_version_number = get_next_version(task_name, task_dir)
    version_dir = get_version_dir(task_name, task_dir, new_version_number)
    
    sequence_data = None
    output_file = None
    sequence_dir_for_shotgrid = None

    if is_sequence_submission:
        # If a folder was passed, find the first file to determine the extension
        if os.path.isdir(original_file_path):
            allowed_exts = filesystem_config["version_convention"][task_name].get("image_ext", [])
            first_file = find_sequence_in_folder(original_file_path, allowed_exts)
            if not first_file:
                raise FileNotFoundError(f"No valid image sequence found in {original_file_path}")
            original_file_path = first_file

        ext = os.path.splitext(original_file_path)[1].lower().strip('.')
        sequence_data = ensure_image_sequence(os.path.dirname(original_file_path), ext)
        
        if not proxy_file_path and auto_create_proxy:
            print("Proxy not found. Auto-creating proxy with FFmpeg...")
            frames, start_frame, padding, extension = sequence_data
            
            first_frame_name = os.path.basename(list(frames.values())[0])
            # Replace the number sequence with the ffmpeg pattern
            input_pattern = re.sub(r'(\d+)(?=\.\w+$)', f'%0{padding}d', first_frame_name)
            input_path_pattern = os.path.join(os.path.dirname(original_file_path), input_pattern)
            
            proxy_name = get_file_name("movie", shot_code, task_name, new_version_number) + ".mp4"
            proxy_output_path = os.path.join(version_dir, proxy_name)
            
            # This updated command correctly converts linear EXR files to Rec. 709
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "24",
                "-start_number", str(start_frame),
                "-i", input_path_pattern,
                "-vf", "zscale=t=linear,tonemap=hable,zscale=p=bt709,zscale=t=bt709,zscale=m=bt709,format=yuv420p,scale=1920:1080",
                "-c:v", "libx264",
                proxy_output_path
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"Successfully created proxy: {proxy_output_path}")
                proxy_file_path = proxy_output_path
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"FFmpeg failed to create proxy:\n{e.stderr}")

    if proxy_file_path:
        match_extension(task_name, False, proxy_file_path)

    if sequence_data:
        sequence_dir_for_shotgrid = version_dir
        frames, _, _, extension = sequence_data
        for frame_number, file_path in frames.items():
            file_name = get_file_name("image", shot_code, task_name, new_version_number, frame_number) + extension
            shutil.copy(file_path, os.path.join(version_dir, file_name))
    else: # It's a single file
        file_type = filesystem_config["version_convention"][task_name]["original"]
        file_name = get_file_name(file_type, shot_code, task_name, new_version_number) + os.path.splitext(original_file_path)[1].lower()
        output_file = os.path.join(version_dir, file_name)
        shutil.copy(original_file_path, output_file)
    
    if proxy_file_path:
        # This will become the main `output_file` for ShotGrid if it exists
        file_type = filesystem_config["version_convention"][task_name]["proxy"]
        file_name = get_file_name(file_type, shot_code, task_name, new_version_number) + os.path.splitext(proxy_file_path)[1].lower()
        output_file = os.path.join(version_dir, file_name)
        if proxy_file_path != output_file:
            shutil.copy(proxy_file_path, output_file)
    
    shotgrid_data = {
        "version_number": new_version_number,
        "shot_code": shot_code,
        "task_name": task_name,
        "sg_path_to_movie": output_file,
        "sg_path_to_frames": sequence_dir_for_shotgrid,
        "mime_type": mime_type_from_file_path(output_file),
    }

    return shotgrid_data
