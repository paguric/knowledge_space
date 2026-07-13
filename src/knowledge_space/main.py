import logging
import os
import sys
import time

import knowledge_base.base
import knowledge_base.domain
import knowledge_base.workspace
from knowledge_base.base import db_dir, files_index, chunks_dir
from knowledge_base.domain import Domain
from knowledge_base.workspace import Workspace, domains_index
from knowledge_space.config import ConfigManager
from knowledge_space.constants import APP_NAME
from knowledge_space import ks_logging
from knowledge_space.settings import setup_folders, CONFIG_FILE, CHUNKS_DIR, DB_DIR, FILES_INDEX, BASES_INDEX, DOMAINS_INDEX, WORKSPACES_INDEX, LOG_FILE

from huggingface_hub import login
from tinydb import TinyDB, Query
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


workspaces_db = None

def setup():
    # Setup cartelle, logging e preferenze
    setup_folders()
    knowledge_base.workspace.domains_index = DOMAINS_INDEX
    knowledge_base.domain.bases_index = BASES_INDEX
    knowledge_base.base.db_dir = DB_DIR
    knowledge_base.base.files_index = FILES_INDEX
    knowledge_base.base.chunks_dir = CHUNKS_DIR

    global workspaces_db
    workspaces_db = TinyDB(WORKSPACES_INDEX)

    ks_logging.setup(LOG_FILE)

    cm = ConfigManager(CONFIG_FILE)
    try: # Prova ad effettuare il login in HF con chiave API da configurazione
        login(token=cm.get_hf_key())
    except:
        pass


def main():
    setup()    
    
    # Carica e avvia Workspace
    workspaces = [Workspace(entry["path"]) for entry in TinyDB(WORKSPACES_INDEX).all()]
    for ws in workspaces:
        ws.run()

    while(1):
        time.sleep(10)


def add_workspace(abs_path: str):
    """
    Crea un nuovo workspace e lo aggiunge a KnowledgeSpace.
    Intesa per uso esterno (per ora CLI), ad es. python -c "import knowledge_space.main as km; km.add_workspace('/percorso/workspace')"
    """
    setup()
    global workspaces_db
    Workspaces = Query()
    
    if not workspaces_db.search(Workspaces.path == abs_path):
        ws = Workspace(abs_path)
        workspaces_db.insert({"workspace": ws.name, "path": abs_path})


if __name__ == "__main__":
    main()
