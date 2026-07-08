import os
from constants import APP_NAME


XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
XDG_STATE  = os.environ.get("XDG_STATE_HOME")  or os.path.expanduser("~/.local/state")
XDG_DATA   = os.environ.get("XDG_DATA_HOME")   or os.path.expanduser("~/.local/share")

"""
config_dir  = os.path.join(XDG_CONFIG, f"{APP_NAME}")
index_dir   = os.path.join(XDG_STATE, f"{APP_NAME}")
chunks_dir  = os.path.join(XDG_DATA, f"{APP_NAME}")

internal_index_path = os.path.join(index_dir, "internal_index.json")
config_path =  os.path.join(config_dir, "config.json")

# Crea cartelle di configurazione e salvataggio dati (index & chunk)
os.makedirs(KnowledgeBase.config_dir, exist_ok=True)
os.makedirs(KnowledgeBase.index_dir, exist_ok=True)
os.makedirs(KnowledgeBase.chunks_dir, exist_ok=True)
"""

LOG_FILE = os.path.join(XDG_STATE, APP_NAME, "log")
