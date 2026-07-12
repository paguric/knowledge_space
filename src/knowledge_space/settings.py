import os

from knowledge_space.constants import APP_NAME


XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
XDG_STATE  = os.environ.get("XDG_STATE_HOME")  or os.path.expanduser("~/.local/state")
XDG_DATA   = os.environ.get("XDG_DATA_HOME")   or os.path.expanduser("~/.local/share")


CONFIG_FILE   = os.path.join(XDG_CONFIG, APP_NAME, "config.json")
CHUNKS_DIR    = os.path.join(XDG_DATA, APP_NAME, "chunks")
DB_DIR        = os.path.join(XDG_STATE, APP_NAME, "chroma_langchain_db")
FILES_INDEX   = os.path.join(XDG_STATE, APP_NAME, "bases.json")
LOG_FILE      = os.path.join(XDG_STATE, APP_NAME, "log")


def setup_folders():
    """
    Crea cartelle di configurazione e salvataggio dati (chunk, DB, KB persistite).
    """
    os.makedirs(os.path.abspath(CHUNKS_DIR), exist_ok=True)
    os.makedirs(os.path.abspath(DB_DIR), exist_ok=True)
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(FILES_INDEX), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
