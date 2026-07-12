import json
import os


class ConfigManager:
    def __init__(self, config_file: str):
        """
        config_file = path al file di configurazione sulla macchina dell'utente.
        """
        self.config_file = config_file

        if not os.path.isfile(self.config_file):
            self.create_default_config_file()

        with open(self.config_file, "r") as f:
            preferences = json.load(f)
            self.hf_key = preferences["hf_key"]

    
    def create_default_config_file(self):
        """
        Crea file di configurazione default.
        """
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)

        data = {"hf_key":"NONE"}
        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=4)


    def get_hf_key(self):
        return self.hf_key
