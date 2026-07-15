import datetime
import logging
import os
import threading
import time
from uuid import uuid4

from knowledge_base.chunking import fixed_size_chunking
from knowledge_base.ingestion import convert

import chromadb
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from tinydb import TinyDB, Query
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# Variabili globali da impostare dall'esterno
db_dir = "nd"
files_index = "nd"
chunks_dir = "nd"


class KnowledgeBase:
    def __init__(self, watch_dir: str):
        self.name = os.path.basename(os.path.normpath(watch_dir))
        self.watch_dir = watch_dir
        self.ready = threading.Event() # semaforo per attendere fine aggiunta file

        # Setup database vettoriale
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
        client = chromadb.PersistentClient(path=db_dir)
        self.vector_store = Chroma(
            client=client,
            collection_name=self.name,
            embedding_function=embeddings,
        )

        # Carica i file dall'indice JSON e lo aggiorna
        self.files = TinyDB(files_index)
        watch_dir_files = list(os.scandir(self.watch_dir))
        
        logging.info(f"\"{self.name}\": aggiungo {watch_dir_files}")
        for f in watch_dir_files:
            self.add(f.path)

        for f in self.get_files():
            if not f in [f.path for f in watch_dir_files]:
                self.remove(f)
        
        self.observer = Observer()
        # self.base_ready.set() # sblocca semaforo

        logging.info(f"Nuova base creata: \"{self.name}\", watch_dir={self.watch_dir}")
        logging.info(f"Contenuti di \"{self.name}\": {self.get_files()}")


    def add(self, file_path: str):
        """
        Aggiunge o aggiorna file. L'aggiornamento non è incrementale; ripete da zero l'intero processo di aggiunta.
        """
        self.ready.clear()
        try:
            self.busy = True
            mtime = os.path.getmtime(file_path)

            if file_path in self.get_files():
                if mtime == self.get_mtime(file_path):
                    logging.info(f"\"{self.name}\": {file_path} già nella base")
                    return
                
                logging.info(f"\"{self.name}\": aggiorno il file {file_path}")
                self.remove(file_path)

            logging.info(f"\"{self.name}\": aggiungo il file {file_path}")
            
            # Ingestione (conversione in Markdown)
            logging.info(f"\"{self.name}\": converto in Markdown {file_path}")
            md_text = convert(file_path)

            # Generazione chunk
            logging.info(f"\"{self.name}\": divido in chunk {file_path}")
            chunks = fixed_size_chunking(md_text)

            # Setup cartella dei chunk
            self.chunks_dir = os.path.join(chunks_dir, self.name)
            file_name = os.path.basename(file_path).rsplit('.', 1)[0]
            file_chunks_dir = os.path.join(self.chunks_dir, f"{file_name}")
            os.makedirs(file_chunks_dir, exist_ok=True)
            
            # Salvataggio chunk su disco
            for i, chunk in enumerate(chunks):
                with open(os.path.join(file_chunks_dir, f"{file_name}_chunk_{i}.md"), "w") as f:
                    f.write(chunk)

            # Aggiunta all'index vettoriale
            documents = [Document(page_content=chunk, metadata={"source": file_path},) for chunk in chunks]
            uuids = [str(uuid4()) for _ in range(len(documents))]
            logging.info(f"\"{self.name}\": aggiungo all'indice vettoriale (calcolo embedding) {file_path}")
            self.vector_store.add_documents(documents=documents, ids=uuids)

            # Aggiunta a grafo del workspace
            # TODO

            self.files.insert({"knowledge_base": self.name, "path": file_path, "mtime": mtime, "added": str(datetime.datetime.now())})
        finally:
            self.ready.set()
            logging.info(f"\"{self.name}\": {file_path} aggiunto correttamente")


    def remove(self, file_path: str):
        logging.info(f"\"{self.name}\": rimuovo il file {file_path}")

        self.files.remove(Query().path == file_path)
        # TODO: rimozione chunk ed embedding nell'index vettoriale


    def run(self):
        event_handler = Handler(self)
        self.observer.schedule(event_handler, self.watch_dir, recursive = True)
        self.observer.start()

        logging.info(f"Base \"{self.name}\" avviata con successo")
    

    def stop(self):
        self.observer.stop()
        self.observer.join()

    
    def get_file_entries(self):
        return self.files.search(Query().knowledge_base == self.name)


    def get_files(self):
        return [entry["path"] for entry in self.get_file_entries()]

    
    def get_mtime(self, file_path: str):
        return next(iter([entry["mtime"] for entry in self.get_file_entries() if entry["path"] == file_path]), None)


    def get_vector_store_content(self):
        """
        Restituisce contenuti della collezione nel vector store con chunk, metadati ed embedding.
        """
        return self.vector_store.get(include=["embeddings", "metadatas", "documents"])

        
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
            if not event.src_path in [mtime for mtime in self.kb.files]:
                return
            if os.path.getmtime(event.src_path) == self.kb.files[event.src_path]:
                return

            self.kb.add(event.src_path)

        elif event.event_type == 'deleted':
            self.kb.remove(event.src_path)

        elif event.event_type == 'moved':
            self.kb.remove(event.src_path)
            self.kb.add(event.dest_path)
