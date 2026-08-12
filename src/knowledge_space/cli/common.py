"""Helper comuni per la CLI.

Fornisce funzioni di utilità usate da tutti i comandi:
- Costruzione ``AppContext`` temporaneo
- Risoluzione workspace (da path o ``last_workspace``)
- Formattazione output (tabella, JSON)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, List, Optional

import typer

from knowledge_base.models import Workspace
from knowledge_space.bootstrap import build_app_context
from knowledge_space.context import AppContext
from knowledge_space.runtime_paths import RuntimePaths


def normalize_base_name(name: str) -> str:
    """Normalizza un nome base ricevuto da argomento/opzione CLI.

    La tab-completion della shell aggiunge spesso uno slash finale alle
    directory (es. ``Progetto di Tesi/``). ``Path.name`` lo rimuove, così
    la chiave coincide con quella registrata in ``ws.bases`` da
    ``ks base add`` (che usa già ``Path(...).name``).

    Accetta anche un path relativo/assoluto: restituisce solo l'ultimo
    componente. Casi speciali: ``.`` e ``..`` restano invariati (non
    vengono ridotti a stringa vuota).
    """
    p = Path(name)
    result = p.name
    # Path('.').name == '' — recupera dal path risolto
    if not result and name in (".", ".."):
        result = p.resolve().name
    return result


def resolve_base_name(name: str, *, workspace: object) -> str:
    """Risolve un nome base da argomento/opzione CLI.

    Strategia a due fasi:
    1. Se il nome sembra un path (contiene ``/``, ``\\``, inizia con
       ``.``) prova la risoluzione: risolve il path e cerca la base il
       cui ``kb.path`` (risolto vs ``workspace.path`` se relativo)
       coincide.
    2. Fallback: normalizza con :func:`normalize_base_name` e cerca per
       nome esatto in ``workspace.bases``.

    Args:
        name: nome o path della base.
        workspace: oggetto ``Workspace`` (da ``knowledge_base.models``).

    Returns:
        Il nome normalizzato della base (chiave in ``workspace.bases``),
        oppure ``name`` normalizzato (il chiamante deve verificare la
        presenza in ``workspace.bases``).
    """
    from pathlib import Path as _Path

    ws_root = _Path(workspace.path).resolve()

    # Fase 1: lookup per path
    looks_like_path = any(str(name).startswith(p) or "/" in name or "\\" in name for p in (".", "~"))
    if looks_like_path:
        try:
            target = _Path(name).resolve()
            for bname, kb in workspace.bases.items():
                kb_abs = kb.path if kb.path.is_absolute() else (ws_root / kb.path)
                if kb_abs.resolve() == target:
                    return bname
        except Exception:
            pass

    # Fase 2: normalizza e cerca per nome
    return normalize_base_name(name)


def get_context(verbose: bool = False) -> AppContext:
    """Crea un ``AppContext`` temporaneo per il comando corrente.

    Configura il logging su file tramite ``setup_logging()`` usando
    ``RuntimePaths.state_home`` come directory di log.

    Args:
        verbose: se ``True``, imposta console handler a DEBUG.

    Returns:
        ``AppContext`` completamente cablato.
    """
    from knowledge_space.logging import setup_logging
    from knowledge_space.runtime_paths import RuntimePaths

    # Crea RuntimePaths temporaneo per ottenere la directory di log.
    rp = RuntimePaths.default()
    rp.ensure_dirs()

    # Configura logging su file. Il console handler resta a WARNING
    # per non interferire con l'output CLI (typer.echo).
    # Con --verbose il console handler passa a DEBUG.
    import logging as _logging

    console_level = _logging.DEBUG if verbose else _logging.WARNING
    setup_logging(log_dir=rp.state_home, console_level=console_level)

    return build_app_context()


def resolve_base_from_cwd(workspace: object) -> Optional[str]:
    """Cerca se il cwd è dentro una base registrata del workspace.

    Risale la gerarchia di directory dal cwd verso la root; se trova una
    directory il cui path assoluto corrisponde a ``kb.path`` di una base
    (risolto eventualmente contro ``workspace.path`` se relativo),
    restituisce il nome di quella base. Altrimenti ``None``.
    """
    from pathlib import Path as _Path

    ws_root = _Path(workspace.path).resolve()
    cwd = _Path.cwd()
    current = cwd
    while True:
        for bname, kb in workspace.bases.items():
            kb_abs = kb.path if kb.path.is_absolute() else (ws_root / kb.path)
            if kb_abs.resolve() == current:
                return bname
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def resolve_workspace_path(
    ctx: AppContext,
    workspace_path: Optional[str] = None,
) -> Path:
    """Risolvi il path del workspace.

    Priorità:
    1. ``workspace_path`` esplicito (flag ``--workspace``)
    2. ``last_workspace`` dal GlobalIndex
    3. Cwd-context: cerca ``.knowledge-space/`` dal cwd verso la root

    Args:
        ctx: contesto dell'applicazione.
        workspace_path: path esplicito (opzionale).

    Returns:
        Path del workspace risolto.

    Raises:
        typer.Exit: se il workspace non può essere determinato.
    """
    if workspace_path:
        p = Path(workspace_path).resolve()
        if not p.is_dir():
            typer.echo(f"Errore: workspace non trovato: {p}", err=True)
            raise typer.Exit(1)
        return p

    # Prova last_workspace
    last = ctx.workspace_manager.get_last_workspace()
    if last and last.is_dir():
        return last

    # Cwd-context (stile git)
    cwd = Path.cwd()
    current = cwd
    while True:
        dot_dir = current / ctx.runtime_paths.dot_folder_name
        if dot_dir.is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    typer.echo(
        "Errore: nessun workspace trovato. "
        "Usa --workspace <path> o esegui 'ks workspace add <path>'.",
        err=True,
    )
    raise typer.Exit(1)


def get_workspace(
    ctx: AppContext,
    workspace_path: Optional[str] = None,
    *,
    sync: bool = False,
) -> Workspace:
    """Carica il workspace (da path o ``last_workspace``).

    Args:
        ctx: contesto dell'applicazione.
        workspace_path: path esplicito (opzionale).
        sync: se ``True``, esegue :meth:`WorkspaceManager.sync` dopo il load
            così le basi rimosse/spostate su disco spariscono dallo stato
            (bug 019). Usato dai comandi di sola lettura.

    Returns:
        ``Workspace`` caricato.
    """
    ws_path = resolve_workspace_path(ctx, workspace_path)
    workspace = ctx.workspace_manager.load(ws_path)
    if sync:
        ctx.workspace_manager.sync(workspace)
    ctx.workspace_manager.set_last_workspace(ws_path)
    return workspace


def output_json(data: Any) -> None:
    """Stampa JSON formattato su stdout."""
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def save_workspace_state(ctx: Any, ws: Any) -> None:
    """Persiste lo stato di un workspace su ``state.json``.

    Usato dai comandi che modificano direttamente il modello
    (es. ``activate``/``deactivate`` di base/file/chunk).
    """
    from knowledge_base.models import WorkspaceConfigData
    from knowledge_base.persistence import WorkspaceConfig

    config_path = ctx.runtime_paths.workspace_state_file(ws.path)
    WorkspaceConfig(
        config_path=config_path, workspace_path=ws.path
    ).save(WorkspaceConfigData(version=1, domains=ws.domains, bases=ws.bases))


def output_table(headers: List[str], rows: List[List[str]]) -> None:
    """Stampa tabella formattata su stdout.

    Args:
        headers: intestazioni colonne.
        rows: righe di dati.
    """
    if not rows:
        typer.echo("(nessun risultato)")
        return

    # Calcola larghezza colonse
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    # Formatta header
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    typer.echo(header_line)
    typer.echo("  ".join("-" * w for w in col_widths))

    # Formatta righe
    for row in rows:
        line = "  ".join(
            str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)
        )
        typer.echo(line)
