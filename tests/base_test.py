import logging
import os
import pytest
import requests
import shutil
import threading

import knowledge_base.base
from knowledge_base.base import KnowledgeBase
from knowledge_space.config import ConfigManager
from knowledge_space import ks_logging

import chromadb
from tinydb import TinyDB, Query


# Setup: crea i file e le cartelle dove salvare chunk, indice dei file, indice vettoriale, log e chunk.

tests_dir = os.path.dirname(os.path.realpath(__file__))
data_dir = os.path.join(tests_dir, "data")

# Pulisce (elimina e ricrea) cartella test/data/ dall'ultimo test
shutil.rmtree(data_dir, ignore_errors=True)
os.makedirs(data_dir, exist_ok=True)

# Chunk
chunks_dir = os.path.join(data_dir, "chunks")
os.makedirs(chunks_dir, exist_ok=True)
knowledge_base.base.chunks_dir = chunks_dir

# Configurazione utente
config_file = os.path.join(data_dir, "config.json")
cm = ConfigManager(config_file)
cm.create_default_config_file()

# Connessione chroma
db_dir = os.path.join(data_dir, "chroma_langchain_db")
os.makedirs(db_dir, exist_ok=True)
knowledge_base.base.db_dir = db_dir

# Connessione tinydb
files_index = os.path.join(data_dir, "bases.json")
knowledge_base.base.files_index = files_index

# Log
log_file = os.path.join(data_dir, "log")
ks_logging.setup(log_file)

# kb/progetto/watch_dir
kb1_dir = os.path.join(data_dir, "kb1")
os.makedirs(kb1_dir, exist_ok=True)


@pytest.fixture
def test_kb():
    # NOTE: We could use pytest's built-in tmp_path fixture to create temp directories. Configure knowledge_base.settings to point to those temp paths inside the fixture, then yield a KnowledgeBase instance
    """
    Crea un'istanza pulita di KnowledgeBase prima di ciascun test e pulisce il database dopo il test.
    """
    base_name = "kb1"
    kb1 = KnowledgeBase(base_name, kb1_dir)
    kb1.run()

    yield kb1

    # Ferma Observer
    kb1.stop()

    # Elimina file dal workspace, database chroma e indice dei file interno
    shutil.rmtree(kb1_dir, ignore_errors=True)
    shutil.rmtree(db_dir, ignore_errors=True)
    os.makedirs(db_dir, exist_ok=True)
    shutil.rmtree(files_index, ignore_errors=True)


def add_file(kb: KnowledgeBase, file_url: str, file_name: str):
    response = requests.get(file_url)

    with open(os.path.join(kb.watch_dir, file_name), mode="wb") as f:
        f.write(response.content)


def test_add_file(test_kb):
    # files = ["https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "https://www.oclc.org/content/dam/oclc/dewey/versions/print/intro.pdf"]
    files = ["https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"]

    # Casi base: file pdf con contenuti e nomi "normali"
    for i, f in enumerate(files):
        base_file_name = f"file_{i}"
        file_name = f"{base_file_name}.pdf"
        add_file(test_kb, f, file_name)
        
        test_kb.ready.wait() # attende aggiunta

        # Verifica contenuti collezione chromadb (chunk aggiunti con metadati ed embedding)
        collection_contents = test_kb.get_vector_store_content()
        assert collection_contents["documents"]
        assert collection_contents["metadatas"]
        assert collection_contents["embeddings"].any()
        # logging.info(f"Contenuti collezione vector store: \"{collection_contents}\"")

        # Verifica indice dei file tinydb
        Base = Query()
        assert test_kb.files.search(Base.knowledge_base == "kb1" and Base.path == os.path.join(test_kb.watch_dir, file_name))

        # Verifica presenza chunk su FS
        file_chunks_dir = os.path.join(chunks_dir, test_kb.name, base_file_name)
        for e in os.scandir(file_chunks_dir):
            if e.is_file():
                with open(e, "r") as f:
                    assert f.read() in collection_contents["documents"]
    
    # Edge cases: file con contenuti e nomi "strani"
    # TODO


def test_add_dir():
    pass


def test_add_dirs():
    """
    Crea una base vuota e aggiunge una cartella con questa struttura:
    data/ # workspace
        kb1/
            dummy.pdf
            kb2/
                dummy2.pdf
    """
    pass
