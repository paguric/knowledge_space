import logging
import os
import json
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class KnowledgeBase:
    def __init__(self, name: str, watch_dir: str):
        self.name = name
        self.watch_dir = watch_dir
        self.files = {}
        self.index = None # TODO: indice vettoriale (connessione al database)
        self.observer = Observer()


    def add(self, file_path: str):
        """
        Aggiunge o aggiorna file. L'aggiornamento non è incrementale; ripete da zero l'intero processo di aggiunta.
        """
        mtime = os.path.getmtime(file_path)

        if file_path in [file_paths for file_paths in self.files]:
            if mtime == self.files[file_path]:
                return # file già nella base
            
            logging.info(f"\"{self.name}\": aggiorno il file {file_path}")
            self.remove(file_path)

        logging.info(f"\"{self.name}\": aggiungo il file {file_path}")
        
        self.files[file_path] = mtime
        # TODO: calcolo chunk e aggiunta a index vettoriale


    def remove(self, file_path: str):
        logging.info(f"\"{self.name}\": rimuovo il file {file_path}")

        del self.files[file_path]
        # TODO: rimozione chunk ed embedding nell'index vettoriale


    def run(self):
        event_handler = Handler(self)
        self.observer.schedule(event_handler, self.watch_dir, recursive = True)
        self.observer.start()
    

    def stop(self):
        self.observer.stop()
        self.observer.join()

    
    def get_files(self):
        return self.files


class Handler(FileSystemEventHandler):
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        super().__init__()

    
    def on_any_event(self, event):
        if event.is_directory:
            return None

        elif event.event_type == 'created':
            self.kb.add(event.src_path)

        elif event.event_type == 'modified':
            if os.path.getmtime(event.src_path) == self.kb.files[event.src_path]:
                return

            self.kb.add(event.src_path)

        elif event.event_type == 'deleted':
            self.kb.remove(event.src_path)

        elif event.event_type == 'moved':
            self.kb.remove(event.src_path)
            self.kb.add(event.dest_path)
