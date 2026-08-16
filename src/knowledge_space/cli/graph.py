"""Comando ``ks graph`` — gestione del grafo di conoscenza (refactor-001).

Sottocomandi: init, sync, status, schema, search. Tutti operano sul
workspace attivo (o ``--workspace``). Gating: senza ``graph.enabled`` o
``extraction_model`` il grafo è inattivo (no-op con warning). Errori di
connessione e dipendenze mancanti → messaggio chiaro, exit 1.
"""

from __future__ import annotations

from typing import Callable, Optional

import typer

from knowledge_base.graph.schema import format_schema
from knowledge_base.graph_search_service import GraphSearchService
from knowledge_space.cli.common import get_context, get_workspace

app = typer.Typer(help="Grafo di conoscenza (Neo4j).")


def _run(fn: Callable[[], None]) -> None:
    """Esegue un comando grafo gestendo gli errori attesi."""
    try:
        fn()
    except ImportError as exc:
        typer.echo(f"Errore: {exc}", err=True)
        raise typer.Exit(1)
    except ConnectionError as exc:
        typer.echo(f"Errore: {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Errore: {exc}", err=True)
        raise typer.Exit(1)


@app.command()
def init(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Path del workspace."
    ),
) -> None:
    """Costruzione completa del grafo (build_graph)."""

    def _do() -> None:
        ctx = get_context()
        ws = get_workspace(ctx, workspace, sync=True)
        graph_manager = ctx.graph_manager_factory(ws)
        counts = graph_manager.build_graph()
        typer.echo(
            f"Grafo costruito: {counts['chunk']} chunk, {counts['document']} "
            f"documenti, {counts['entity']} entità, {counts['relation']} relazioni"
        )

    _run(_do)


@app.command()
def sync(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Path del workspace."
    ),
    base: Optional[str] = typer.Option(
        None, "--base", "-b", help="Sincronizza solo questa base."
    ),
) -> None:
    """Propagazione incrementale (chunk nuovi/modificati)."""

    def _do() -> None:
        ctx = get_context()
        ws = get_workspace(ctx, workspace, sync=True)
        graph_manager = ctx.graph_manager_factory(ws)
        counts = graph_manager.sync_base(base_name=base)
        typer.echo(
            f"Grafo sincronizzato: {counts['chunk']} chunk, {counts['entity']} "
            f"entità, {counts['relation']} relazioni"
        )

    _run(_do)


@app.command()
def status(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Path del workspace."
    ),
) -> None:
    """Stato del grafo: connessione e conteggi dal DB."""

    def _do() -> None:
        ctx = get_context()
        ws = get_workspace(ctx, workspace, sync=True)
        graph_manager = ctx.graph_manager_factory(ws)
        info = graph_manager.status()
        if not info.get("connected"):
            typer.echo("Neo4j non raggiungibile.")
            raise typer.Exit(1)
        if "error" in info:
            typer.echo(f"Errore lettura conteggi: {info['error']}", err=True)
        typer.echo("Connessione: OK")
        typer.echo(f"Basi nel grafo: {len(info.get('bases', []))}")
        if info.get("bases"):
            typer.echo("  " + ", ".join(info["bases"]))
        typer.echo(f"Documenti: {info.get('document', 0)}")
        typer.echo(f"Chunk: {info.get('chunk', 0)}")
        typer.echo(f"Entità: {info.get('entity', 0)}")
        typer.echo(f"Relazioni: {info.get('relations', 0)}")

    _run(_do)


@app.command()
def schema(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Path del workspace."
    ),
) -> None:
    """Schema derivato dal DB (nessuno schema persistente)."""

    def _do() -> None:
        ctx = get_context()
        ws = get_workspace(ctx, workspace, sync=True)
        graph_manager = ctx.graph_manager_factory(ws)
        typer.echo(format_schema(graph_manager._store))

    _run(_do)


@app.command()
def search(
    query: str = typer.Argument(..., help="Query di ricerca."),
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Path del workspace."
    ),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Numero risultati."),
) -> None:
    """Ricerca sul grafo (rispetta basi/file/chunk attivi)."""

    def _do() -> None:
        ctx = get_context()
        ws = get_workspace(ctx, workspace, sync=True)
        graph_manager = ctx.graph_manager_factory(ws)
        service = GraphSearchService(graph_manager)
        results = service.search(ws, query, top_k=top_k)
        if not results:
            typer.echo("Nessun risultato trovato.")
            return
        for r in results:
            typer.echo(f"[{r.score:.4f}] {r.chunk_id}")
            typer.echo(f"  {r.text[:200]}")
            if r.metadata.get("entities"):
                typer.echo(f"  entità: {', '.join(r.metadata['entities'])}")

    _run(_do)
