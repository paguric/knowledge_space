import os
import pytest
import shutil

import knowledge_base.base
from knowledge_base.base import KnowledgeBase
from knowledge_base.workspace import Workspace
from knowledge_space.config import ConfigManager
from knowledge_space import ks_logging


@pytest.fixture
def ks_env(): # NOTE: pytest fornisce tmp_path e tmp_path_factory, che creano directory in /tmp e le puliscono automaticamente.
    """
    Fornisce un setup a tutti i metodi di test.
    Crea i file e le cartelle dove salvare chunk, indice dei file, indice vettoriale, log e chunk.
    """
    # Data
    tests_dir = os.path.dirname(os.path.realpath(__file__))
    data_dir = os.path.join(tests_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    # Chunk
    chunks_dir = os.path.join(data_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    knowledge_base.base.chunks_dir = chunks_dir

    # Configurazione utente
    config_file = os.path.join(data_dir, "config.json")
    cm = ConfigManager(config_file)
    cm.create_default_config_file()

    # Database chroma
    db_dir = os.path.join(data_dir, "chroma_langchain_db")
    os.makedirs(db_dir, exist_ok=True)
    knowledge_base.base.db_dir = db_dir

    # Database tinydb
    files_index = os.path.join(data_dir, "bases.json")
    knowledge_base.base.files_index = files_index

    # Log
    log_file = os.path.join(data_dir, "log")
    ks_logging.setup(log_file)

    yield {
        "tests_dir": tests_dir,
        "data_dir": data_dir,
        "chunks_dir": chunks_dir,
        "config_file": config_file,
        "db_dir": db_dir,
        "files_index": files_index,
        "log_file": log_file,
    }

    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture
def files():
    return ["https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", "https://www.orimi.com/pdf-test.pdf", "https://pdfobject.com/pdf/sample.pdf"]
    

@pytest.fixture
def long_files():
    return ["https://www.oclc.org/content/dam/oclc/dewey/versions/print/intro.pdf"]


@pytest.fixture
def test_ws(ks_env):
    """
    Crea un'istanza pulita di Workspace prima di ciascun test.
    """
    watch_dir = os.path.join(ks_env["data_dir"], "ws1_dir")
    os.makedirs(watch_dir, exist_ok=True)
    ws1 = Workspace(watch_dir)
    ws1.run()

    yield ws1

    ws1.stop()
    shutil.rmtree(watch_dir, ignore_errors=True)


@pytest.fixture
def test_kb(ks_env, test_ws):
    """
    Crea un'istanza pulita di KnowledgeBase prima di ciascun test.
    """
    watch_dir = os.path.join(test_ws.watch_dir, "kb1_dir")
    os.makedirs(watch_dir, exist_ok=True)
    kb1 = KnowledgeBase(watch_dir)
    kb1.run()
    
    yield kb1

    kb1.stop()
    shutil.rmtree(watch_dir, ignore_errors=True)
