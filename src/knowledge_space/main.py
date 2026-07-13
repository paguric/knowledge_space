import logging
import os
import sys
import time

import knowledge_base.base
from knowledge_base.workspace import Workspace
from knowledge_base.domain import Domain
from knowledge_space.config import ConfigManager
from knowledge_space.constants import APP_NAME
from knowledge_space import ks_logging
from knowledge_space.settings import setup_folders, CONFIG_FILE, CHUNKS_DIR, DB_DIR, FILES_INDEX, LOG_FILE

from huggingface_hub import login
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# Setup cartelle
setup_folders()
knowledge_base.base.db_dir = DB_DIR
knowledge_base.base.files_index = FILES_INDEX
knowledge_base.base.chunks_dir = CHUNKS_DIR


# Setup logging
ks_logging.setup(LOG_FILE)


# Carica le preferenze dell'utente
cm = ConfigManager(CONFIG_FILE)

# Prova ad effettuare il login in HF con chiave API da configurazione
try:
    login(token=cm.get_hf_key())
except:
    pass


# Crea workspace via argomenti CLI
args = sys.argv[1:]
workspaces = [Workspace(os.path.join(os.getcwd(), arg)) for arg in args]
for ws in workspaces:
    ws.run()

while(1):
    time.sleep(10)
