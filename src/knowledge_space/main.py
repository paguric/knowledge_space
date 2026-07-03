import os
from knowledge_base.base import KnowledgeBase


path = os.path.join(os.getcwd(), "tests/")

kb = KnowledgeBase(path)
kb.refresh()
kb.run()
