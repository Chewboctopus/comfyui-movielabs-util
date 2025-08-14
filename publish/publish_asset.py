import os
from .shotgrid import shots, artist_logins, ShotGrid
from .config import shotgrid_config, task_names
from .fs import create_task_version


def sanitize_path(path):
    if path is None:
        return path
    path = path.strip()
    if (path.startswith('"') and path.endswith('"')) or (path.startswith("'") and path.endswith("'")):
        return path[1:-1]
    return path


class PublishAsset:
    RETURN_TYPES = ()
    FUNCTION = "publish_asset"
    OUTPUT_NODE = True
    CATEGORY = "MovieLabs > Util > Grant8&9"

    @classmethod
    def INPUT_TYPES(cls):
        artist_logins_with_blank = [""] + artist_logins
        return {
            "required": {
                "artist_login": (artist_logins_with_blank,),
                "shot_code": (list(shots.keys()),),
                "task_name": (task_names,),
                "original_asset_file_path": ("STRING", {"default": "", "label": "Original Asset File Path"}),
                "auto_create_proxy": ("BOOLEAN", {"default": True, "label": "Auto-create MP4 proxy for sequences"}),
            },
            "optional": {
                "proxy_asset_file_path": ("STRING", {"default": "", "label": "Proxy Asset File Path"}),
                "notes": ("STRING", {"default": "", "multiline": True, "label": "Notes"}),
            },
        }

    def publish_asset(
        self,
        artist_login,
        shot_code,
        task_name,
        original_asset_file_path,
        auto_create_proxy,
        proxy_asset_file_path=None,
        notes="",
    ):
        if not artist_login:
            raise Exception("Select your artist login")

        sg = ShotGrid(shotgrid_config, artist_login)

        if shot_code not in shots:
            raise Exception(f"Shot {shot_code} not found")

        sg_tasks = sg.get_tasks(shot_code, task_name)
        if not sg_tasks:
            raise Exception(f"Task {task_name} not found for shot {shot_code}")

        clean_original_path = sanitize_path(original_asset_file_path)
        clean_proxy_path = sanitize_path(proxy_asset_file_path)
        
        # --- THIS IS THE FIX ---
        # The faulty block that only searched for .exr files has been removed.
        # We now pass the original path directly to create_task_version,
        # which correctly handles all configured file types (EXR, PNG, JPG, etc.).
        
        shotgrid_data = create_task_version(
            shot_code,
            task_name,
            clean_original_path,
            clean_proxy_path,
            auto_create_proxy,
        )
        version_code = sg.get_version_code(
            shot_code, task_name, shotgrid_data["version_number"]
        )

        shotgrid_fields = {
            "sg_notes": notes,
            "sg_path_to_movie": shotgrid_data["sg_path_to_movie"],
            "sg_path_to_frames": shotgrid_data["sg_path_to_frames"],
        }

        shot_id = shots[shot_code]["id"]
        task_id = sg_tasks[0]["id"]

        sg_version = sg.add_version(version_code, shot_id, task_id, shotgrid_fields)
        file_upload_data = sg.request_file_upload(
            sg_version["id"], "sg_uploaded_movie", shotgrid_fields["sg_path_to_movie"]
        )
        sg.upload_file(
            file_upload_data["links"]["upload"],
            shotgrid_fields["sg_path_to_movie"],
            shotgrid_data["mime_type"],
        )
        sg.complete_file_upload(file_upload_data)

        return ()


NODE_CLASS_MAPPINGS = {
    "PublishAsset": PublishAsset,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PublishAsset": "Publish Asset (MovieLabs)",
}