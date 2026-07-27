"""Comandi config.

``ks config show [<base>]`` — mostra config risolta
``ks config init`` — genera defaults.toml template
``ks config set <scope> <key> <value>`` — imposta preferenza TOML
``ks config unset <scope> <key>`` — rimuove chiave TOML
``ks config edit <scope>`` — apre TOML in $EDITOR
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import typer

from knowledge_base.base_config import (
    DEFAULTS_TOML_TEMPLATE,
    BaseConfig,
    BaseConfigLoader,
    ensure_base_toml,
    ensure_defaults_toml,
    write_toml,
)
from knowledge_space.cli.common import (
    get_context,
    get_workspace,
    normalize_base_name,
    output_json,
    resolve_base_from_cwd,
    resolve_base_name,
)

logger = logging.getLogger(__name__)

app = typer.Typer(help="Gestione configurazione.")

# --------------------------------------------------------------------------- #
# Trigger di reindex
# --------------------------------------------------------------------------- #

_TRIGGERS: Dict[str, str] = {
    "embedding.model": "--model-change",
    "chunking.method": "--chunking-change",
    "chunking.chunk_size": "--chunking-change",
    "chunking.chunk_overlap": "--chunking-change",
    "ingestion.library": "--ingestion-change",
}


def _detect_trigger(key: str) -> Optional[str]:
    """Restituisce il flag di reindex per la chiave, o ``None``."""
    return _TRIGGERS.get(key)


# --------------------------------------------------------------------------- #
# Helper scope
# --------------------------------------------------------------------------- #


def _resolve_scope(
    scope: str,
    ws: Any,
    ctx: Any,
) -> Tuple[Path, str]:
    """Risolvi lo scope in un path TOML e un etichetta.

    Returns:
        ``(toml_path, label)`` dove label è ``"defaults.toml"`` o
        ``"base.toml (<nome>)"``.
    """
    dot = ctx.runtime_paths.dot_folder_name
    if scope == "defaults":
        path = ws.path / dot / "defaults.toml"
        return path, "defaults.toml"
    # Scope = nome base
    base_name = normalize_base_name(scope)
    if base_name not in ws.bases:
        typer.echo(f"Base non trovata: {base_name}", err=True)
        raise typer.Exit(1)
    kb = ws.bases[base_name]
    path = kb.path / dot / "base.toml"
    return path, f"base.toml ({base_name})"


def _ensure_toml_exists(scope: str, ws: Any, ctx: Any) -> Path:
    """Crea il TOML se assente, restituisce il path."""
    dot = ctx.runtime_paths.dot_folder_name
    if scope == "defaults":
        path, _ = ensure_defaults_toml(ws.path, dot)
    else:
        base_name = normalize_base_name(scope)
        kb = ws.bases[base_name]
        path, _ = ensure_base_toml(kb.path, dot)
    return path


# --------------------------------------------------------------------------- #
# Parsing valore da CLI
# --------------------------------------------------------------------------- #


def _parse_value(raw: str) -> Any:
    """Converti una stringa CLI nel tipo Python più appropriato.

    Prova nell'ordine: bool → int → float → literal (list/dict/tuple) → str.
    """
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        val = ast.literal_eval(raw)
        if isinstance(val, (list, dict, tuple)):
            return val
    except (ValueError, SyntaxError):
        pass
    return raw


def _set_nested(d: dict, dotted_key: str, value: Any) -> None:
    """Imposta un valore in un dict annidato via path dotted.

    Es. ``_set_nested(d, "chunking.chunk_size", 500)`` →
    ``d["chunking"]["chunk_size"] = 500``.

    Crea le sezioni intermedie se mancanti.
    """
    parts = dotted_key.split(".")
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _get_nested(d: dict, dotted_key: str) -> Any:
    """Leggi un valore annidato via path dotted. Solleva KeyError se mancante."""
    parts = dotted_key.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted_key)
        current = current[part]
    return current


def _remove_nested(d: dict, dotted_key: str) -> bool:
    """Rimuovi una chiave annidata. Restituisce ``True`` se era presente."""
    parts = dotted_key.split(".")
    current = d
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if parts[-1] in current:
        del current[parts[-1]]
        return True
    return False


def _is_empty_toml(data: dict) -> bool:
    """``True`` se il dict non contiene sezioni con chiavi utili."""
    return all(
        not isinstance(v, dict) or len(v) == 0
        for v in data.values()
    )


# --------------------------------------------------------------------------- #
# Rilevamento trigger di reindex
# --------------------------------------------------------------------------- #


def _check_triggers_for_base(
    base_name: str,
    config_loader: BaseConfigLoader,
    manager: Any,
    key: str,
    old_value: Any,
    new_value: Any,
) -> Optional[str]:
    """Controlla se il cambio attiva un trigger. Restituisce il flag o ``None``."""
    trigger = _detect_trigger(key)
    if trigger is None:
        return None
    if old_value == new_value:
        return None
    return trigger


def _collection_non_empty(manager: Any, base_name: str) -> bool:
    """Verifica se la collection Chroma della base è non vuota."""
    try:
        return manager._collection_non_empty(base_name)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Comandi
# --------------------------------------------------------------------------- #


@app.command()
def show(
    scope: Optional[str] = typer.Argument(
        None,
        metavar="[SCOPE]",
        help="Cosa mostrare: nome o percorso di una base, oppure 'defaults' "
             "per i default del workspace. Se omesso e sei dentro una base, "
             "usa quella; altrimenti mostra i default del workspace.",
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra la configurazione effettiva (cascata risolta)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    config_loader = ctx.base_config_loader_factory(ws.path)

    if scope and scope.strip().lower() == "defaults":
        scope = None  # forza ramo workspace defaults
    elif scope:
        scope = resolve_base_name(scope, workspace=ws)
    else:
        scope = resolve_base_from_cwd(ws)

    if scope:
        if scope not in ws.bases:
            typer.echo(f"Base non trovata: {scope}", err=True)
            raise typer.Exit(1)

        config = config_loader.load(scope)
        config_data = {
            "base": scope,
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
        label = f" per {scope}" if scope else " workspace"
        typer.echo(f"Configurazione{label}:")
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


@app.command()
def set(  # noqa: A001 — ombreggia la builtin, ma è il nome CLI voluto
    scope: str = typer.Argument(help="Scope: 'defaults' o nome di una base."),
    key: str = typer.Argument(help="Chiave dotted (es. chunking.chunk_size)."),
    value: str = typer.Argument(help="Valore da assegnare."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Imposta una preferenza nel file TOML (defaults.toml o base.toml)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)

    # Valida che la chiave esista nel modello BaseConfig
    _validate_key(key)

    # 1. Determina il file TOML target e assicurati che esista
    toml_path, label = _resolve_scope(scope, ws, ctx)
    _ensure_toml_exists(scope, ws, ctx)

    # 2. Leggi TOML corrente
    with open(toml_path, "rb") as f:
        data: Dict[str, Any] = tomllib.load(f)

    # 3. Valore corrente resolved per rilevamento trigger
    config_loader = ctx.base_config_loader_factory(ws.path)
    if scope == "defaults":
        old_config = config_loader.load_workspace_defaults()
    else:
        base_name = normalize_base_name(scope)
        old_config = config_loader.load(base_name)
    old_value = _get_config_field(old_config, key)

    # 4. Parsa il nuovo valore e applica
    new_value = _parse_value(value)
    _set_nested(data, key, new_value)

    # 5. Rileva trigger
    if scope == "defaults":
        # Per defaults: controlla tutte le basi non vuote
        triggers_info: List[Tuple[str, str]] = []
        for bn in ws.bases:
            try:
                base_old = config_loader.load(bn)
                base_old_val = _get_config_field(base_old, key)
                if base_old_val != new_value:
                    trigger = _detect_trigger(key)
                    if trigger:
                        mgr = ctx.base_manager_factory(ws)
                        if _collection_non_empty(mgr, bn):
                            triggers_info.append((bn, trigger))
            except Exception:
                pass
        if triggers_info:
            _confirm_trigger_defaults(triggers_info, key, new_value)
    else:
        base_name = normalize_base_name(scope)
        if old_value != new_value:
            trigger = _detect_trigger(key)
            if trigger:
                mgr = ctx.base_manager_factory(ws)
                non_empty = _collection_non_empty(mgr, base_name)
                _confirm_trigger_base(base_name, trigger, key, old_value, new_value, non_empty)

    # 6. Salva
    write_toml(toml_path, data)
    typer.echo(f"{key} = {_format_value(new_value)} salvato in {label}")


@app.command()
def unset(
    scope: str = typer.Argument(help="Scope: 'defaults' o nome di una base."),
    key: str = typer.Argument(help="Chiave dotted da rimuovere (es. chunking.chunk_size)."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove una chiave dal file TOML (il valore torna al default della cascata)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)

    # Per unset: valida solo il formato (dotted key), non l'esistenza nel modello
    parts = key.split(".")
    if len(parts) < 2:
        typer.echo(
            f"Errore: chiave '{key}' non valida. Usa il formato 'sezione.campo'",
            err=True,
        )
        raise typer.Exit(1)

    # 1. Determina il file TOML
    toml_path, label = _resolve_scope(scope, ws, ctx)
    if not toml_path.exists():
        typer.echo(f"Il file {label} non esiste, nessuna chiave da rimuovere.")
        return

    # 2. Leggi TOML corrente
    with open(toml_path, "rb") as f:
        data: Dict[str, Any] = tomllib.load(f)

    # 3. Prova a rimuovere
    try:
        old_value = _get_nested(data, key)
    except KeyError:
        typer.echo(f"Chiave '{key}' non presente in {label}.")
        return

    removed = _remove_nested(data, key)
    if not removed:
        typer.echo(f"Chiave '{key}' non presente in {label}.")
        return

    # 4. Rileva trigger (il valore effettivo cambia)
    config_loader = ctx.base_config_loader_factory(ws.path)
    try:
        if scope == "defaults":
            # Dopo l'unset, il valore torna a quello hardcoded
            hardcoded = BaseConfig()
            new_value = _get_config_field(hardcoded, key)
        else:
            base_name = normalize_base_name(scope)
            # Dopo l'unset su base.toml, il valore torna a defaults.toml/hardcoded
            new_config = config_loader.load_workspace_defaults()
            new_value = _get_config_field(new_config, key)
    except (AttributeError, KeyError):
        # Chiave non nel modello Pydantic — nessun trigger rilevabile
        write_toml(toml_path, data)
        typer.echo(f"Chiave '{key}' rimossa da {label}.")
        return

    if old_value != new_value:
        trigger = _detect_trigger(key)
        if trigger:
            if scope == "defaults":
                triggers_info = []
                for bn in ws.bases:
                    try:
                        mgr = ctx.base_manager_factory(ws)
                        if _collection_non_empty(mgr, bn):
                            triggers_info.append((bn, trigger))
                    except Exception:
                        pass
                if triggers_info:
                    _confirm_trigger_defaults(triggers_info, key, new_value)
            else:
                base_name = normalize_base_name(scope)
                mgr = ctx.base_manager_factory(ws)
                non_empty = _collection_non_empty(mgr, base_name)
                _confirm_trigger_base(base_name, trigger, key, old_value, new_value, non_empty)

    # 5. Salva
    write_toml(toml_path, data)
    typer.echo(f"Chiave '{key}' rimossa da {label}.")


@app.command("edit")
def edit_cmd(
    scope: str = typer.Argument(help="Scope: 'defaults' o nome di una base."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Apre il file TOML nell'editor ($EDITOR, fallback nano)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)

    # Assicurati che il file esista
    toml_path, label = _resolve_scope(scope, ws, ctx)
    _ensure_toml_exists(scope, ws, ctx)

    editor = os.environ.get("EDITOR", "nano")
    typer.echo(f"Apertura {label} con {editor}...")
    result = subprocess.run([editor, str(toml_path)])
    if result.returncode != 0:
        typer.echo(f"Editor terminato con codice {result.returncode}.", err=True)
        raise typer.Exit(result.returncode)

    typer.echo(f"File salvato. Usa 'ks config show' per verificare la configurazione.")


# --------------------------------------------------------------------------- #
# Validazione chiave
# --------------------------------------------------------------------------- #

_VALID_SECTIONS = {
    "ingestion", "chunking", "embedding",
    "pre_retrieval", "retrieval", "post_retrieval", "graph",
}


def _validate_key(key: str) -> None:
    """Valida che la chiave dotted corrisponda a un campo esistente in BaseConfig."""
    parts = key.split(".")
    if len(parts) < 2:
        typer.echo(
            f"Errore: chiave '{key}' non valida. Usa il formato 'sezione.campo' "
            f"(es. chunking.chunk_size).",
            err=True,
        )
        raise typer.Exit(1)

    section = parts[0]
    if section not in _VALID_SECTIONS:
        typer.echo(
            f"Errore: sezione '{section}' non riconosciuta. "
            f"Sezioni valide: {', '.join(sorted(_VALID_SECTIONS))}.",
            err=True,
        )
        raise typer.Exit(1)

    # Verifica che il campo esista nella sotto-sezione Pydantic
    try:
        cfg = BaseConfig()
        sub = getattr(cfg, section)
        # Per le sotto-sezioni con 'stages' (pre_retrieval), il campo
        # potrebbe essere una lista — accetta anche 'stages' direttamente
        field_name = parts[1]
        if not hasattr(sub, field_name):
            raise AttributeError
    except AttributeError:
        typer.echo(
            f"Errore: campo '{parts[1]}' non esiste nella sezione [{section}].",
            err=True,
        )
        raise typer.Exit(1)


def _get_config_field(config: BaseConfig, key: str) -> Any:
    """Leggi un campo dalla config risolta via path dotted."""
    parts = key.split(".")
    sub = getattr(config, parts[0])
    return getattr(sub, parts[1])


def _format_value(value: Any) -> str:
    """Formatta un valore per la stampa."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


# --------------------------------------------------------------------------- #
# Conferma trigger
# --------------------------------------------------------------------------- #


def _confirm_trigger_base(
    base_name: str,
    trigger: str,
    key: str,
    old_value: Any,
    new_value: Any,
    collection_non_empty: bool,
) -> None:
    """Mostra il trigger per una base e chiedi conferma se bloccato."""
    typer.echo(
        f"⚠ Modifica rilevata: {key}: {_format_value(old_value)} → {_format_value(new_value)}"
    )
    typer.echo(f"  Trigger di reindex: {trigger}")
    if collection_non_empty:
        typer.echo(
            f"  La collection Chroma della base '{base_name}' non è vuota. "
            f"Dopo il salvataggio sarà necessario: ks reindex {base_name} {trigger}"
        )
        if not typer.confirm("Procedere con il salvataggio?"):
            typer.echo("Annullato.")
            raise typer.Exit(0)
    else:
        typer.echo(f"  (collection vuota: nessun blocco, ma tieni presente il trigger)")


def _confirm_trigger_defaults(
    triggers_info: List[Tuple[str, str]],
    key: str,
    new_value: Any,
) -> None:
    """Mostra i trigger per le basi impattate da una modifica a defaults.toml."""
    typer.echo(f"⚠ La modifica di '{key}' nel defaults.toml impatta:")
    for bn, trigger in triggers_info:
        typer.echo(f"  - base '{bn}': {trigger}")
    if not typer.confirm("Procedere con il salvataggio?"):
        typer.echo("Annullato.")
        raise typer.Exit(0)
