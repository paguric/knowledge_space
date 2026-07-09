import logging
import os
import sys
import time

from knowledge_space.settings import CONFIG_FILE, CHUNKS_DIR, DB_DIR, KB_INDEX_FILE, LOG_FILE
from knowledge_base.base import KnowledgeBase

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# Crea cartelle di configurazione e salvataggio dati (chunk, DB, KB persistite)
os.makedirs(os.path.abspath(CHUNKS_DIR), exist_ok=True)
os.makedirs(os.path.abspath(DB_DIR), exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(KB_INDEX_FILE), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode="w",
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Disabilita logging di Langchain
# https://github.com/langchain-ai/langchain/issues/14065
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)


# Imposta il path del workspace via CLI
args = sys.argv[1:]
workspace_dir = os.path.join(os.getcwd(), args[0])

bases = []


# Inizializza le basi già create
logging.info("Inizializzo basi già presenti su disco")
for (dirpath, dirnames, filenames) in os.walk(workspace_dir):
    for dirname in dirnames:
        path = os.path.join(dirpath, dirname)
        base = KnowledgeBase(os.path.basename(path), path)
        logging.info(f"Nuova base creata: \"{base.name}\", watch_dir={base.watch_dir}")

        """
        Per ogni file della cartella dell'utente:
            se il file della cartella non è nella base serializzata OR è stato modificato::
                base.add(file)

        Per ogni file della base serializzata:
            se il file non è più nella cartella dell'utente:
                base.remove(file)

        O ancora più sintetico:

        per ogni file nella differenza simmetrica tra (cartella_utente ⇔ base):
            se il file è nella cartella_utente:
                base.add(file)
            altrimenti:
                base.remove(file)
        """

        bases.append(base)

        base.run()
        logging.info(f"Base \"{base.name}\" avviata con successo")
        logging.info(f"Contenuti di \"{base.name}\": {base.get_files()}")
logging.info("Finito di inizializzare basi su disco")


class Handler(FileSystemEventHandler):
    """
    Inizializza istanze di KnowledgeBase all'aggiunta di nuove KB/progetti nel workspace.
    """
    def on_any_event(self, event):
        if not event.is_directory or not event.event_type == 'created':
            return

        path = event.src_path
        base = KnowledgeBase(os.path.basename(path), path)
        logging.info(f"Nuova base creata: \"{base.name}\", watch_dir={base.watch_dir}")

        # Se l'utente fra drag-&-drop di una cartella non vuota, bisogna riempire la base
        # Se la cartella contiene sotto cartelle, diventa un processo ricorsivo (crea nuova base, riempila, ripeti)

        bases.append(base)

        base.run()
        logging.info(f"Base \"{base.name}\" avviata con successo")


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
