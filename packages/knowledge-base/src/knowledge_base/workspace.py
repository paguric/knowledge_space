import logging
import os

from knowledge_base.base import KnowledgeBase

from tinydb import TinyDB, Query
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# Variabili globali da impostare dall'esterno
domains_index = "nd"


class Workspace:
    def __init__(self, dir_path: str):
        self.name =  os.path.basename(os.path.normpath(dir_path))
        self.watch_dir = dir_path
        self.bases = []

        # Inizializza le basi già create
        logging.info("Inizializzo basi già presenti su disco")

        for (dirpath, dirnames, filenames) in os.walk(self.watch_dir):
            for dirname in dirnames:
                path = os.path.join(dirpath, dirname)
                logging.info(f"Creo nuova base \"{os.path.basename(path)}\"")
                base = KnowledgeBase(os.path.basename(path), path)

                self.bases.append(base)

        logging.info("Finito di inizializzare basi su disco")
        logging.info(f"Nuovo Workspace creato: \"{self.name}\", watch_dir={self.watch_dir}")
        logging.info(f"Contenuti di \"{self.name}\": {[base for base in self.bases]}")


    def run(self):
        for base in self.bases:
            base.run()

        event_handler = Handler(self)

        self.observer = Observer()
        self.observer.schedule(event_handler, self.watch_dir, recursive = True)
        self.observer.start()

    
    def stop(self):
        self.observer.stop()
        self.observer.join()


class Handler(FileSystemEventHandler):
    """
    Inizializza istanze di KnowledgeBase all'aggiunta di nuove KB/progetti nel workspace.
    """
    def __init__(self, ws: Workspace):
        self.ws = ws
        super().__init__()


    def on_any_event(self, event):
        if not event.is_directory or not event.event_type == 'created':
            return

        path = event.src_path
        
        logging.info(f"Creo nuova base \"{os.path.basename(path)}\"")
        base = KnowledgeBase(os.path.basename(path), path)
        self.ws.bases.append(base)
        base.run()
