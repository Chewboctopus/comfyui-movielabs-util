import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import shotgrid_config, task_names

def authenticate_with_client_credentials(client, config, user_login):
    response = client.post(
        f"{config['server_url']}/api/v1.1/auth/access_token",
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "grant_type": "client_credentials",
            "scope": f"sudo_as_login:{user_login}" if user_login else None
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
    )
    return response.json()

def refresh_tokens(client, config, tokens):
    response = client.post(
        f"{config['server_url']}/api/v1.1/auth/access_token",
        data={"refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"},
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    )
    return response.json()

def create_client():
    client = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    client.mount('http://', adapter)
    client.mount('https://', adapter)
    return client

class ShotGrid:
    def __init__(self, config, user_login):
        self.config = config
        self.user_login = user_login
        self.client = create_client()
        self._refresh_timer = None
        self._initial_auth()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def _initial_auth(self):
        resp_json = authenticate_with_client_credentials(self.client, self.config, self.user_login)
        if "access_token" in resp_json:
            self.tokens = resp_json
            # Set up refresh timer
            self.cleanup()
            
            self._refresh_timer = threading.Timer(
                self.tokens["expires_in"] - 30,
                self._refresh_tokens
            )
            self._refresh_timer.daemon = True
            self._refresh_timer.start()
        else:
            raise Exception("Could not authenticate with ShotGrid")

    def _refresh_tokens(self):
        # Refresh using refresh_token
        resp_json = refresh_tokens(self.client, self.config, self.tokens)
        self.tokens = resp_json
        
        # Set up next refresh
        self.cleanup()
        
        self._refresh_timer = threading.Timer(
            self.tokens["expires_in"] - 30,
            self._refresh_tokens
        )
        self._refresh_timer.daemon = True
        self._refresh_timer.start()

    def cleanup(self):
        if self._refresh_timer:
            self._refresh_timer.cancel()
            self._refresh_timer = None

    def get_shots(self):
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        params = {"filter[project.Project.id]": self.config["project_id"], "filter[tasks.Task.content]": ",".join(task_names), "fields": "id,code,project,content"}
        response = self.client.get(f"{self.config['server_url']}/api/v1.1/entity/Shot", headers=headers, params=params)
        sg_shots = response.json()
        if "errors" in sg_shots:
            if response.status_code == 401:
                self.cleanup()
                self._initial_auth()
                return self.get_shots()
            else:
                raise Exception("Error getting shots from ShotGrid")
        if "data" in sg_shots and len(sg_shots["data"]) > 0:
            return [shot for shot in sg_shots["data"] if "attributes" in shot and "code" in shot["attributes"]]
        else:
            return []
    
    def get_shot(self, shot_code):
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        params = {"filter[project.Project.id]": self.config["project_id"], "filter[code]": shot_code, "fields": "id,code,project,content"}
        response = self.client.get(f"{self.config['server_url']}/api/v1.1/entity/Shot", headers=headers, params=params)
        sg_shot = response.json()
        if "errors" in sg_shot:
            if response.status_code == 401:
                self.cleanup()
                self._initial_auth()
                return self.get_shot(shot_code)
            else:
                raise Exception("Error getting shot from ShotGrid")
        if "data" in sg_shot and len(sg_shot["data"]) > 0:
            return [shot for shot in sg_shot["data"] if "attributes" in shot and "code" in shot["attributes"]]
        else:
            return []
    
    def get_tasks(self, shot_code, task_name):
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        params = {"filter[project.Project.id]": self.config["project_id"], "filter[entity.Shot.code]": shot_code, "fields": "id,name,content,step"}
        if task_name:
            params["filter[content]"] = task_name
        response = self.client.get(f"{self.config['server_url']}/api/v1.1/entity/Task", headers=headers, params=params)
        sg_tasks = response.json()
        if "errors" in sg_tasks:
            if response.status_code == 401:
                self.cleanup()
                self._initial_auth()
                return self.get_tasks(shot_code, task_name)
            else:
                raise Exception("Error getting tasks from ShotGrid")
        if "data" in sg_tasks and len(sg_tasks["data"]) > 0:
            return sg_tasks["data"]
        else:
            return []
    
    # def get_versions(self, shot_code):
    #     headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
    #     params = {"filter[project.Project.id]": self.config["project_id"], "filter[entity.Shot.code]": shot_code, "fields": "id,code,entity.Shot.id"}
    #     params["sort"] = "-code"
    #     response = self.client.get(f"{self.config['server_url']}/api/v1.1/entity/Version", headers=headers, params=params)
    #     sg_versions = response.json()
    #     if "errors" in sg_versions:
    #         if response.status_code == 401:
    #             self.cleanup()
    #             self._initial_auth()
    #             return self.get_versions(shot_code)
    #         else:
    #             raise Exception("Error getting versions from ShotGrid")
    #     if "data" in sg_versions and len(sg_versions["data"]) > 0:
    #         sg_versions = sg_versions["data"]
    #         versions = [version for version in sg_versions if self.version_convention_regex.match(version["attributes"]["code"])]
    #         return versions
    #     else:
    #         return []
    
    def get_version_code(self, shot_code, task_name, version_number):
        return self.config["version_convention"][task_name].format(SHOT_CODE=shot_code, VERSION_NUMBER=version_number)
    
    def get_artists(self):
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        params = {
            "fields": "firstname,lastname,login",
            "filter[projects.Project.id]": self.config["project_id"],
            "sort": "login"
        }
        response = self.client.get(f"{self.config['server_url']}/api/v1.1/entity/HumanUser", headers=headers, params=params)
        data = response.json()
        return data.get("data", [])
    
    def add_version(self, version_code, shot_id, task_id, fields):
        params = {
            "project":  { "type": "Project", "id": self.config["project_id"] },
            "entity":   { "type": "Shot",    "id": shot_id },
            "sg_task":  { "type": "Task",    "id": task_id },
        }
        fields["code"] = version_code
        params.update(fields)
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        response = self.client.post(f"{self.config['server_url']}/api/v1/entity/versions", headers=headers, json=params)
        sg_version = response.json()
        if "errors" in sg_version:
            if response.status_code == 401:
                self.cleanup()
                self._initial_auth()
                return self.add_version(version_code, shot_id, task_id, fields)
            else:
                raise Exception("Error adding version to ShotGrid")
        return sg_version["data"]
    
    def request_file_upload(self, version_id, field_name, filename):
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        response = self.client.get(f"{self.config['server_url']}/api/v1/entity/versions/{version_id}/{field_name}/_upload?filename={filename}", headers=headers)
        if "errors" in response.json():
            if response.status_code == 401:
                self.cleanup()
                self._initial_auth()
                return self.request_file_upload(version_id, field_name, filename)
            else:
                raise Exception("Error requesting file upload to ShotGrid")
        return response.json()
    
    def upload_file(self, upload_link, file_path, mime_type):
        headers = {"Accept": "application/json", "Content-Type": mime_type}
        with open(file_path, "rb") as f:
            response = self.client.put(upload_link, headers=headers, data=f)
        if response.status_code != 200:
            raise Exception("Error uploading file to ShotGrid")

    def complete_file_upload(self, file_upload_data):
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}", "Accept": "application/json"}
        data = {
            "upload_info": file_upload_data["data"],
            "upload_data": {}
        }
        response = self.client.post(f"{self.config['server_url']}{file_upload_data['links']['complete_upload']}", headers=headers, json=data)
        if response.status_code != 201:
            if response.status_code == 401:
                self.cleanup()
                self._initial_auth()
                return self.complete_file_upload(file_upload_data)
            else:
                raise Exception("Error completing file upload to ShotGrid")

sg = ShotGrid(shotgrid_config, None)
sg_shots = sg.get_shots()
shots = {shot["attributes"]["code"]: shot for shot in sg_shots if "attributes" in shot and "code" in shot["attributes"]}
# tasks = {}
# for shot_code in shots.keys():
#     tasks[shot_code] = {}
#     for task_name in task_names:
#         sg_tasks = sg.get_tasks(shot_code, task_name)
#         if len(sg_tasks) > 0:
#             tasks[shot_code][task_name] = sg_tasks[0]
artist_logins = [artist["attributes"]["login"] for artist in sg.get_artists()]