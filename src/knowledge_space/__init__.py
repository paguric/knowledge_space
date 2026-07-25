"""Knowledge Space — app layer (CLI, REST, bootstrap)."""

from knowledge_space.context import AppContext
from knowledge_space.bootstrap import build_app_context

__all__ = ["AppContext", "build_app_context"]


def main() -> None:
    print("Hello from knowledge-space!")
