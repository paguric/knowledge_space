import os
from constants import APP_NAME


XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
XDG_STATE  = os.environ.get("XDG_STATE_HOME")  or os.path.expanduser("~/.local/state")
XDG_DATA   = os.environ.get("XDG_DATA_HOME")   or os.path.expanduser("~/.local/share")


CONFIG_FILE   = os.path.join(XDG_CONFIG, APP_NAME, "config.json")
CHUNKS_DIR    = os.path.join(XDG_DATA, APP_NAME, "chunks")
DB_DIR        = os.path.join(XDG_STATE, APP_NAME, "chroma_langchain_db")
KB_INDEX_FILE = os.path.join(XDG_STATE, APP_NAME, "kb.json")
LOG_FILE      = os.path.join(XDG_STATE, APP_NAME, "log")
