"""CLI Typer per Knowledge Space.

Comando principale: ``knowledge-space`` (alias ``ks``).

Modalità standalone (Fase 1-3): ogni comando crea un ``AppContext``
temporaneo, opera su ``state.json``/Chroma, termina.

Step 13 della roadmap.
"""

from __future__ import annotations

import typer

from knowledge_space.cli.workspace import app as workspace_app
from knowledge_space.cli.domain import app as domain_app
from knowledge_space.cli.base import app as base_app
from knowledge_space.cli.file import app as file_app
from knowledge_space.cli.chunk import app as chunk_app
from knowledge_space.cli.config import app as config_app
from knowledge_space.cli.models_cmd import app as models_app

app = typer.Typer(
    name="knowledge-space",
    help="Knowledge Space — gestione basi di conoscenza con ricerca vettoriale.",
    no_args_is_help=True,
)

# Registra i sub-comandi multi-command (Typer con subcommands)
app.add_typer(workspace_app, name="workspace", help="Gestione workspace.")
app.add_typer(domain_app, name="domain", help="Gestione domini.")
app.add_typer(base_app, name="base", help="Gestione basi di conoscenza.")
app.add_typer(file_app, name="file", help="Gestione file indicizzati.")
app.add_typer(chunk_app, name="chunk", help="Gestione chunk.")
app.add_typer(config_app, name="config", help="Gestione configurazione.")
app.add_typer(models_app, name="models", help="Gestione modelli di embedding.")

# Registra i comandi singoli direttamente
from knowledge_space.cli.tree import tree_command  # noqa: E402
from knowledge_space.cli.search import search_command  # noqa: E402
from knowledge_space.cli.reindex import reindex_command  # noqa: E402
from knowledge_space.cli.status import status_command  # noqa: E402
from knowledge_space.cli.serve import serve_command  # noqa: E402

app.command(name="tree", help="Visualizzazione struttura ad albero.")(tree_command)
app.command(name="search", help="Ricerca vettoriale.")(search_command)
app.command(name="reindex", help="Reindicizzazione basi.")(reindex_command)
app.command(name="status", help="Panoramica dello stato.")(status_command)
app.command(name="serve", help="Avvia watcher + server MCP.")(serve_command)


@app.command()
def version() -> None:
    """Mostra la versione."""
    typer.echo("knowledge-space 0.1.0")


# Alias per comodità: `ks` punta alla stessa app
def cli() -> None:
    """Entry point alternativo (alias ``ks``)."""
    app()


if __name__ == "__main__":
    app()
