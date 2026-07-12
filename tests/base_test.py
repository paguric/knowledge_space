import logging
import os
import pytest
import requests
import shutil
import time

import knowledge_base.base
from knowledge_base.base import KnowledgeBase
from knowledge_space.config import ConfigManager
from knowledge_space import ks_logging

import chromadb


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
    # TODO: Use pytest's built-in tmp_path fixture to create temp directories. Configure knowledge_base.settings to point to those temp paths inside the fixture, then yield a KnowledgeBase instance
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

    client = chromadb.PersistentClient(path=db_dir)


def test_add_file(test_kb):
    data_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf" # https://www.oclc.org/content/dam/oclc/dewey/versions/print/intro.pdf
    response = requests.get(data_url)

    with open(os.path.join(test_kb.watch_dir, "dummy.pdf"), mode="wb") as f:
        f.write(response.content)

    # Attende calcolo chunk
    logging.info(f"Attendo aggiunta file...")
    time.sleep(10)
    
    # Verifica chunk
    # TODO

    # Verifica contenuti collezione chromadb
    collection_contents = test_kb.get_vector_store_content()
    logging.info(f"Contenuti collezione vector store: \"{collection_contents}\"")

    # Verifica indice dei file tinydb
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
