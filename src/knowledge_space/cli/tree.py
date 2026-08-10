"""Comando tree.

``ks tree`` — albero workspace → domain → base → file → chunk
``ks tree --base <name>`` — scope a base
``ks tree --json`` — output JSON
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import typer

logger = logging.getLogger(__name__)

from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    output_json,
    resolve_base_name,
)


def _build_tree(ws: Any, base_filter: Optional[str] = None) -> Dict[str, Any]:
    """Costruisce la struttura ad albero come dict."""
    tree: Dict[str, Any] = {
        "workspace": str(ws.path),
        "domains": [],
        "bases": {},
    }

    # Domini
    for domain in ws.domains:
        tree["domains"].append({
            "name": domain.name,
            "active": domain.active,
            "bases": domain.base_names,
        })

    # Basi
    bases_to_show = {}
    if base_filter:
        if base_filter in ws.bases:
            bases_to_show[base_filter] = ws.bases[base_filter]
    else:
        bases_to_show = ws.bases

    for bname, kb in bases_to_show.items():
        base_info: Dict[str, Any] = {
            "path": str(kb.path),
            "active": kb.active,
            "files": {},
        }
        for fname, entry in kb.files.items():
            base_info["files"][fname] = {
                "file_id": entry.file_id,
                "active": entry.active,
                "chunks": len(entry.chunks),
            }
        tree["bases"][bname] = base_info

    return tree


def _print_tree(ws: Any, base_filter: Optional[str] = None) -> None:
    """Stampa l'albero in formato testo."""
    typer.echo(f"📁 {ws.path}")

    # Raccogli basi già mostrate nei domini
    bases_in_domains: set[str] = set()

    # Domini
    for di, domain in enumerate(ws.domains):
        is_last_domain = di == len(ws.domains) - 1
        domain_prefix = "└── " if is_last_domain and not base_filter else "├── "
        status = "✓" if domain.active else "✗"
        typer.echo(f"{domain_prefix}📂 [{status}] {domain.name}")

        for i, bname in enumerate(domain.base_names):
            bases_in_domains.add(bname)
            if base_filter and bname != base_filter:
                continue
            is_last_base = i == len(domain.base_names) - 1
            child_prefix = "    " if is_last_domain else "│   "
            connector = "└── " if is_last_base else "├── "
            kb = ws.bases.get(bname)
            if kb:
                n_files = len(kb.files)
                n_chunks = sum(len(f.chunks) for f in kb.files.values())
                typer.echo(f"{child_prefix}{connector}📚 {bname} ({n_files} file, {n_chunks} chunk)")
            else:
                typer.echo(f"{child_prefix}{connector}📚 {bname} (non registrata)")

    # Basi standalone (non in domini)
    standalone = [
        name for name in ws.bases
        if name not in bases_in_domains and (base_filter is None or name == base_filter)
    ]

    for i, bname in enumerate(standalone):
        kb = ws.bases[bname]
        n_files = len(kb.files)
        n_chunks = sum(len(f.chunks) for f in kb.files.values())
        is_last = i == len(standalone) - 1 and not (base_filter and base_filter in ws.bases)
        prefix = "└── " if is_last else "├── "
        typer.echo(f"{prefix}📚 {bname} ({n_files} file, {n_chunks} chunk)")

    # File (se scope a una base)
    if base_filter and base_filter in ws.bases:
        kb = ws.bases[base_filter]
        files = list(kb.files.items())
        if files:
            typer.echo(f"└── 📄 File:")
            for i, (fname, entry) in enumerate(files):
                n_chunks = len(entry.chunks)
                is_last = i == len(files) - 1
                prefix = "    └── " if is_last else "    ├── "
                status = "✓" if entry.active else "✗"
                typer.echo(f"{prefix}[{status}] {fname} ({n_chunks} chunk)")


def tree_command(
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Scope a una base."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra la struttura ad albero del workspace."""
    app_ctx = get_context(verbose=verbose)
    ws = get_workspace(app_ctx, workspace, sync=True)
    logger.info("Visualizzazione albero workspace")
    if base is not None:
        base = resolve_base_name(base, workspace=ws)
        logger.debug("Filtro base: %s", base)

    if json_output:
        tree_data = _build_tree(ws, base)
        output_json(tree_data)
    else:
        _print_tree(ws, base)
