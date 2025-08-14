import os
from pathlib import Path
import json

# Get the parent directory of the current file's parent (the project root)
config_dir = Path(__file__).parent.parent

# Construct the path to config.json
config_path = os.path.join(config_dir, "config.json")
if not os.path.exists(config_path):
    raise Exception("config.json not found")

with open(config_path, "r") as f:
    config = json.load(f)

# Get the secret file path from the config
secret_file_path = config["shotgrid"].get("secret_file_path", "shotgrid_secret.txt")

# If the path is not absolute, resolve it relative to the project root
if not os.path.isabs(secret_file_path):
    secret_file_path = os.path.join(config_dir, secret_file_path)

if not os.path.exists(secret_file_path):
    raise Exception(f"Secret file not found at {secret_file_path}. Please check the 'secret_file_path' in your config.json.")

with open(secret_file_path, "r") as f:
    client_secret = f.read().strip()

filesystem_config = config["filesystem"]
shotgrid_config = config["shotgrid"]
shotgrid_config["client_secret"] = client_secret  # Add the secret to the config
task_names = config["task_names"]
