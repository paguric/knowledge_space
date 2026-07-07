import os
import json
import time
from knowledge_space.constants import APP_NAME
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class InternalFileRecord:
    """
    Indice (registro/record) interno.
    """

    def __init__(self, record_path):
        """
        Crea il file JSON formattato per salvare i path dei file.
        """
        self.record_path = record_path
        if not os.path.exists(self.record_path):
            data = {"files": []}
            json_str = json.dumps(data, indent=4)
            with open(self.record_path, "w") as f:
                f.write(json_str)


    def get_files(self):
        with open(self.record_path, "r") as f:
            data = json.load(f)
        
        return data["files"]


    def add_file(self, path: str):
        entry = {path:os.path.getmtime(path)}
        with open(self.record_path, "r+") as f:
            data = json.load(f)
            data["files"].append(entry)
            f.seek(0)
            json.dump(data, f, indent=4)

    
    def remove_file(self, path: str):
        files = self.get_files()
        files = [entry for entry in files if path not in entry]

        with open(self.record_path, "w") as f:
            json.dump({"files": files}, f, indent=4)


    def update_file(self, path:str):
        files = self.get_files()
        for entry in files:
            if path in entry:
                entry[path] = os.path.getmtime(path)
                break

        with open(self.record_path, "w") as f:
            json.dump({"files": files}, f, indent=4)


class KnowledgeBase:
    """
    Gestisce l'indicizzazione nel database vettoriale. Avvia il processo ad ogni modifica dell'indice interno.
    """
    
    xdg_config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    xdg_state  = os.environ.get("XDG_STATE_HOME")  or os.path.expanduser("~/.local/state")
    xdg_data   = os.environ.get("XDG_DATA_HOME")   or os.path.expanduser("~/.local/share")

    config_path = os.path.join(xdg_config, "", "config.json")
    record_path = os.path.join(xdg_state, f"{APP_NAME}", "internal_index.json")
    chunks_dir  = os.path.join(xdg_data, f"{APP_NAME}", "chunks")

    def __init__(self, watchDirectory: str):
        self.watchDirectory = watchDirectory
        self.observer = Observer()

        # Crea cartella di configurazione
        os.makedirs(KnowledgeBase.config_path, exist_ok=True)

        self.internalFileRecord = InternalFileRecord(KnowledgeBase.record_path)


    def add(self, filePath: str):
        print(f"Adding file {filePath}...")        

    def remove(self, filePath: str):
        print(f"Removing file {filePath}...")

    def refresh(self):
        """
        Controlla che la cartella creata dall'utente e l'indice in record_path siano in sync. Da utilizzare all'avvio della base di conoscenza e per refresh manuali.
        """

        files = self.internalFileRecord.get_files()

        # Controllo file nuovi/modificati/spostati
        for e in os.scandir(self.watchDirectory):
            if not e.is_file():
                continue

            path = e.path
            mtime = os.path.getmtime(path)
            entry = {path:mtime}

            # Confronto stringa/chiave dei dizionari
            if not any(path in f for f in files):
                # print(f"{e.name} viene inserito nella base e nel registro\n")
                self.add(path)
                self.internalFileRecord.add_file(path)

            elif entry not in files:
                # print(f"{path} sarà rimosso dalla base, verrà aggiunto di nuovo e viene aggiornata la entry\n")
                self.remove(path)
                self.add(path)
                self.internalFileRecord.update_file(path)
                
        # Controllo file eliminati
        for entry in files:
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
    """
    Gestisce i cambiamenti nella base di conoscenza esterna gestita dall'utente.
    - Ogni nuovo file aggiunto dall'utente viene convertito in chunk markdown e aggiunto direttamente al database vettoriale.
    - I file eliminati vengono rimossi dal database vettoriale e dalla cache interna di chunk in markdown.
    - I file modificati vengono prima eliminati, poi sono aggiunti come se fossero mai stati presenti (non è un approccio incrementale: per ogni modifica si ricalcolano da zero chunk ed embedding vettoriali).
    """

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        super().__init__()

    
    def on_any_event(self, event):
        if event.is_directory:
            return None

        path = event.src_path
            
        if event.event_type == 'created':
            self.kb.add(path)
            self.kb.internalFileRecord.add_file(path)

        elif event.event_type == 'modified':
            # Watchdog genera questo evento anche quando un file viene creato (in alcuni casi)
            # Per colpa della libreria quindi si controlla che il file che genera l'evento non sia appena stato aggiunto

            if {path:os.path.getmtime(path)} in self.kb.internalFileRecord.get_files():
                return
            
            self.kb.remove(path)
            self.kb.add(path)
            self.kb.internalFileRecord.update_file(path)
            
        elif event.event_type == 'deleted':
            self.kb.remove(path)
            self.kb.internalFileRecord.remove_file(path)

        elif event.event_type == 'moved':
            self.kb.remove(path)
            self.kb.internalFileRecord.remove_file(path)
            self.kb.add(event.dest_path)
            self.kb.internalFileRecord.add_file(event.dest_path)
