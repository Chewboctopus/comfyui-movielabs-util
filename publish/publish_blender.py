from .shotgrid import shots, artist_logins, ShotGrid
from .config import shotgrid_config, task_names
from .fs import create_task_version


class PublishBlender:
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "shot_code": (list(shots.keys()),),
                "blender_file_path": ("STRING", {"default": "", "label": "Blender File Path", "tooltip": "Path to the blender file to publish"}),
            },
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    RETURN_TYPES = ()
    FUNCTION = "publish_blender"
    OUTPUT_NODE = True
    CATEGORY = "MovieLabs > Util > Grant8&9"

    def publish_blender(self, **kwargs):
        shot_code = kwargs["shot_code"]
        task_name = "Blender Files"
        blender_file_path = kwargs["blender_file_path"]

        if shot_code not in shots:
            raise Exception(f"Shot {shot_code} not found")
        create_task_version(shot_code, task_name, blender_file_path)
        return ()

NODE_CLASS_MAPPINGS = {
    "PublishBlender": PublishBlender
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PublishBlender": "Publish Blender"
}