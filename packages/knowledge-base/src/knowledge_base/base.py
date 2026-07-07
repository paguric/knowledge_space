import os
import json
import time
from knowledge_space.constants import APP_NAME
from tinydb import TinyDB, Query
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class InternalFileRecord:
    def __init__(self, record_path):
        self.db = TinyDB(record_path)  # crea/apre il DB

    def get_files(self):
        return self.db.all()

    def add_file(self, path: str):
        self.db.insert({"path": path, "mtime": os.path.getmtime(path)})

    def remove_file(self, path: str):
        File = Query()
        self.db.remove(File.path == path)

    def update_file(self, path: str):
        File = Query()
        self.db.update({"mtime": os.path.getmtime(path)}, File.path == path)


class KnowledgeBase:
    """
    Gestisce l'indicizzazione nel database vettoriale. Avvia il processo ad ogni modifica dell'indice interno.
    """

    xdg_config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    xdg_state  = os.environ.get("XDG_STATE_HOME")  or os.path.expanduser("~/.local/state")
    xdg_data   = os.environ.get("XDG_DATA_HOME")   or os.path.expanduser("~/.local/share")

    config_dir  = os.path.join(xdg_config, f"{APP_NAME}")
    index_dir   = os.path.join(xdg_state, f"{APP_NAME}")
    chunks_dir  = os.path.join(xdg_data, f"{APP_NAME}")

    internal_index_path = os.path.join(index_dir, "internal_index.json")
    config_path =  os.path.join(config_dir, "config.json")


    def __init__(self, watchDirectory: str):
        self.watchDirectory = watchDirectory
        self.observer = Observer()

        # Crea cartelle di configurazione e salvataggio dati (index & chunk)
        os.makedirs(KnowledgeBase.config_dir, exist_ok=True)
        os.makedirs(KnowledgeBase.index_dir, exist_ok=True)
        os.makedirs(KnowledgeBase.chunks_dir, exist_ok=True)

        self.internalFileRecord = InternalFileRecord(KnowledgeBase.internal_index_path)


    def add(self, filePath: str):
        print(f"Adding file {filePath}...")     


    def remove(self, filePath: str):
        print(f"Removing file {filePath}...")


    def refresh(self):
        """
        Aggiorna l'indice interno e la base di conoscenza (chunk + database vettoriale).
        """

        internal_files = self.internalFileRecord.get_files()

        # Controllo file nuovi/modificati/spostati
        for (dirpath, dirnames, filenames) in os.walk(self.watchDirectory):
            for filename in filenames:
                path = os.path.join(dirpath, filename)
                if not os.path.isfile(path):
                    continue

                mtime = os.path.getmtime(path)
                entry = {path:mtime}

                # Confronto stringa/chiave dei dizionari
                if not any(path in in_f for in_f in internal_files):
                    # print(f"{f.name} viene inserito nella base e nel registro\n")
                    self.add(path)
                    self.internalFileRecord.add_file(path)

                elif entry not in internal_files:
                    # print(f"{path} sarà rimosso dalla base, verrà aggiunto di nuovo e viene aggiornata la entry\n")
                    self.remove(path)
                    self.add(path)
                    self.internalFileRecord.update_file(path)
                
        # Controllo file eliminati
        for entry in internal_files:
            for path in entry:
                if not os.path.exists(path):
                    # print(f"{path} viene rimosso dalla base e dal registro")
                    self.remove(path)
                    self.internalFileRecord.remove_file(path)


    def run(self):
        event_handler = Handler(self)
        self.observer.schedule(event_handler, self.watchDirectory, recursive = True)
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except:
            self.observer.stop()
            print("KnowledgeBase Stopped")

        self.observer.join()


class Handler(FileSystemEventHandler):
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        super().__init__()

    
    def on_any_event(self, event):
        # if event.is_directory:
        #     return

        self.kb.refresh()
