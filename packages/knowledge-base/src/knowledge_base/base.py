import logging
import os
import time
from uuid import uuid4

from knowledge_base.chunking import fixed_size_chunking
from knowledge_base.ingestion import convert
from knowledge_space.settings import DB_DIR

import chromadb
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class KnowledgeBase:
    def __init__(self, name: str, watch_dir: str):
        self.name = name
        self.watch_dir = watch_dir
        self.files = {}
        
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-mpnet-base-v2")
        client = chromadb.PersistentClient(path=DB_DIR)
        # self.collection = chroma_client.get_or_create_collection(name=self.name) # collezione all'interno del database vettoriale
        self.vector_store = Chroma(
            client=client,
            collection_name=self.name,
            embedding_function=embeddings,
        )
        
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
        
        # Calcola chunk e salva gli embedding nell'index vettoriale
        logging.info(f"\"{self.name}\": converto in Markdown {file_path}")
        md_text = convert(file_path)

        logging.info(f"\"{self.name}\": divido in chunk {file_path}")
        documents = [Document(page_content=chunk) for chunk in fixed_size_chunking(md_text)]

        logging.info(f"\"{self.name}\": calcolo embedding {file_path}")
        uuids = [str(uuid4()) for _ in range(len(documents))]
        self.vector_store.add_documents(documents=documents, ids=uuids)

        self.files[file_path] = mtime
        logging.info(f"\"{self.name}\": {file_path} aggiunto correttamente")


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
