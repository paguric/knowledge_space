"""Comandi config.

``ks config show [<base>]`` — mostra config risolta
``ks config init`` — genera defaults.toml template
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from knowledge_base.base_config import DEFAULTS_TOML_TEMPLATE
from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    output_json,
)

app = typer.Typer(help="Gestione configurazione.")


@app.command()
def show(
    base_name: Optional[str] = typer.Argument(None, help="Nome della base (opzionale)."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra la configurazione effettiva (cascata risolta)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    config_loader = ctx.base_config_loader_factory(ws.path)

    if base_name:
        # Config specifica per base
        if base_name not in ws.bases:
            typer.echo(f"Base non trovata: {base_name}", err=True)
            raise typer.Exit(1)

        config = config_loader.load(base_name)
        config_data = {
            "base": base_name,
            "ingestion": {
                "library": config.ingestion.library,
                "params": config.ingestion.params,
            },
            "chunking": {
                "method": config.chunking.method,
                "chunk_size": config.chunking.chunk_size,
                "chunk_overlap": config.chunking.chunk_overlap,
                "separator": repr(config.chunking.separator),
                "params": config.chunking.params,
            },
            "embedding": {
                "model": config.embedding.model,
                "device": config.embedding.device,
                "api_base": config.embedding.api_base,
                "params": config.embedding.params,
            },
            "pre_retrieval": {
                "stages": [
                    {"method": s.method, "params": s.params}
                    for s in config.pre_retrieval.stages
                ],
            },
            "retrieval": {
                "method": config.retrieval.method,
                "query_mode": config.retrieval.query_mode,
                "top_k": config.retrieval.top_k,
                "params": config.retrieval.params,
            },
            "post_retrieval": {
                "method": config.post_retrieval.method,
                "params": config.post_retrieval.params,
            },
            "graph": {
                "enabled": config.graph.enabled,
                "on_chunk_change": config.graph.on_chunk_change,
                "retriever": config.graph.retriever,
                "schema_mode": config.graph.schema_mode,
                "resolver": config.graph.resolver,
                "extraction_model": config.graph.extraction_model,
                "top_k": config.graph.top_k,
            },
        }
    else:
        # Defaults del workspace
        config = config_loader.load_workspace_defaults()
        config_data = {
            "scope": "workspace defaults",
            "ingestion": {"library": config.ingestion.library},
            "chunking": {
                "method": config.chunking.method,
                "chunk_size": config.chunking.chunk_size,
            },
            "embedding": {"model": config.embedding.model},
            "retrieval": {
                "method": config.retrieval.method,
                "top_k": config.retrieval.top_k,
            },
        }

    if json_output:
        output_json(config_data)
    else:
        typer.echo(f"Configurazione{' per ' + base_name if base_name else ' workspace'}:")
        _print_config(config_data, indent=2)


def _print_config(data: dict, indent: int = 0) -> None:
    """Stampa la configurazione in modo leggibile."""
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            typer.echo(f"{prefix}{key}:")
            _print_config(value, indent + 2)
        elif isinstance(value, list):
            typer.echo(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    for k, v in item.items():
                        typer.echo(f"{prefix}  {k}: {v}")
                else:
                    typer.echo(f"{prefix}  - {item}")
        else:
            typer.echo(f"{prefix}{key}: {value}")


@app.command()
def init(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Genera un defaults.toml template nel workspace."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)

    defaults_path = ws.path / ctx.runtime_paths.dot_folder_name / "defaults.toml"

    if defaults_path.exists():
        typer.echo(f"defaults.toml già esistente: {defaults_path}")
        overwrite = typer.confirm("Sovrascrivere?")
        if not overwrite:
            typer.echo("Annullato.")
            return

    defaults_path.parent.mkdir(parents=True, exist_ok=True)
    defaults_path.write_text(DEFAULTS_TOML_TEMPLATE, encoding="utf-8")
    typer.echo(f"Template generato: {defaults_path}")
