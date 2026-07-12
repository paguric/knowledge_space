import logging
import os
import sys
import time

from knowledge_base.base import KnowledgeBase
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
knowledge_base.base.files_index = CHUNKS_DIR


# Setup logging
ks_logging.setup(LOG_FILE)


# Carica le preferenze dell'utente
cm = ConfigManager(CONFIG_FILE)

# Prova ad effettuare il login in HF con chiave API da configurazione
try:
    login(token=cm.get_hf_key())
except:
    pass


# Imposta il path del workspace principale via CLI
args = sys.argv[1:]
workspace_dir = os.path.join(os.getcwd(), args[0]) # ???

bases = []


# Inizializza le basi già create
logging.info("Inizializzo basi già presenti su disco")

for (dirpath, dirnames, filenames) in os.walk(workspace_dir):
    for dirname in dirnames:
        path = os.path.join(dirpath, dirname)
        logging.info(f"Creo nuova base \"{os.path.basename(path)}\"")
        base = KnowledgeBase(os.path.basename(path), path)

        bases.append(base)
        base.run()

logging.info("Finito di inizializzare basi su disco")


class Handler(FileSystemEventHandler):
    """
    Inizializza istanze di KnowledgeBase all'aggiunta di nuove KB/progetti nel workspace.
    """
    def on_any_event(self, event):
        if not event.is_directory or not event.event_type == 'created':
            return

        path = event.src_path
        logging.info(f"Creo nuova base \"{os.path.basename(path)}\"")
        base = KnowledgeBase(os.path.basename(path), path)

        # Se l'utente fra drag-&-drop di una cartella non vuota, bisogna riempire la base
        # Se la cartella contiene sotto cartelle, diventa un processo ricorsivo (crea nuova base, riempila, ripeti)

        bases.append(base)
        base.run()


event_handler = Handler()

observer = Observer()
observer.schedule(event_handler, workspace_dir, recursive = True)
observer.start()
try:
    while True:
        time.sleep(5)
except:
    observer.stop()
    for b in bases:
        b.stop()
    logging.info("Fermato main observer")

observer.join()
