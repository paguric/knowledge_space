import logging
import os
import pytest
import requests
import shutil
import threading

import chromadb
from tinydb import TinyDB, Query


def add_file(kb: KnowledgeBase, file_url: str, file_name: str):
    response = requests.get(file_url)

    with open(os.path.join(kb.watch_dir, file_name), mode="wb") as f:
        f.write(response.content)


@pytest.mark.skip(reason="troppo lungo")
def test_add_file(ks_env, test_kb, files):
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
        # Base = Query()
        # assert test_kb.files.search(Base.knowledge_base == test_kb.name and Base.path == os.path.join(test_kb.watch_dir, file_name))

        # Verifica presenza chunk su FS
        # file_chunks_dir = os.path.join(ks_env["chunks_dir"], test_kb.name, base_file_name)
        # for e in os.scandir(file_chunks_dir):
        #     if e.is_file():
        #         with open(e, "r") as f:
        #             assert f.read() in collection_contents["documents"]
    
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
