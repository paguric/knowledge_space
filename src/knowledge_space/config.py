import json
import os

from knowledge_space.settings import CONFIG_FILE



class ConfigManager:
    def __init__(self):
        with open(CONFIG_FILE, "r") as f:
            preferences = json.load(f)
            self.hf_key = preferences["hf_key"]
    

    @staticmethod
    def create_default_config_file():
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

        data = {"hf_key":"NONE"}
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)


    def get_hf_key(self):
        return self.hf_key
