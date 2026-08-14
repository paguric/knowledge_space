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
    ConfigChangeBlockedError,
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
# Autocomplete e help per le chiavi config
# --------------------------------------------------------------------------- #


def _build_keys_help() -> str:
    """Genera una tabella testuale delle chiavi configurabili da BaseConfig.

    Itera sui model_fields di BaseConfig, per ogni sezione itera sui campi
    della sotto-sezione Pydantic, e produce una tabella con tipo e default.
    """
    cfg = BaseConfig()
    lines = []
    # Header
    lines.append(f"{'KEY':<40} {'TIPO':<20} {'DEFAULT'}")
    lines.append(f"{'—'*40} {'—'*20} {'—'*30}")

    for section_name, field_info in BaseConfig.model_fields.items():
        # Ottieni l'istanza della sotto-sezione
        section_instance = getattr(cfg, section_name)
        section_type = type(section_instance)

        # Per ogni campo nella sotto-sezione
        for field_name, sub_field in section_type.model_fields.items():
            key = f"{section_name}.{field_name}"
            default_val = getattr(section_instance, field_name)

            # Determina il tipo
            ann = sub_field.annotation
            if ann is int:
                tipo = "int"
            elif ann is float:
                tipo = "float"
            elif ann is bool:
                tipo = "bool"
            elif ann is str:
                tipo = "str"
            elif ann is Optional[str]:
                tipo = "str | None"
            elif ann is Optional[int]:
                tipo = "int | None"
            elif "Dict" in str(ann) or "dict" in str(ann):
                tipo = "dict"
            elif "List" in str(ann) or "list" in str(ann):
                tipo = "list"
            else:
                tipo = str(ann).replace("typing.", "").replace("knowledge_base.base_config.", "")

            # Formatta il default
            if isinstance(default_val, str):
                # Escape newlines per visualizzazione compatta
                escaped = default_val.replace("\n", "\\n")
                if len(escaped) > 30:
                    default_str = f'"{escaped[:27]}..."'
                else:
                    default_str = f'"{escaped}"'
            elif isinstance(default_val, list):
                if not default_val:
                    default_str = "list()"
                else:
                    truncated = str(default_val)
                    if len(truncated) > 30:
                        default_str = truncated[:27] + "..."
                    else:
                        default_str = truncated
            elif isinstance(default_val, dict):
                if not default_val:
                    default_str = "dict()"
                else:
                    default_str = str(default_val)
            elif default_val is None:
                default_str = "None"
            else:
                default_str = str(default_val)

            lines.append(f"{key:<40} {tipo:<20} {default_str}")

    return "\n".join(lines)


def _all_valid_keys() -> list[str]:
    """Restituisce la lista di tutte le chiavi dotted valide per config set/unset."""
    cfg = BaseConfig()
    keys = []
    for section_name in BaseConfig.model_fields:
        section_instance = getattr(cfg, section_name)
        section_type = type(section_instance)
        for field_name in section_type.model_fields:
            keys.append(f"{section_name}.{field_name}")
    return keys


def _key_autocomplete(
    ctx: typer.Context,
    args: list[str],
    incomplete: str,
) -> list[tuple[str, str]]:
    """Autocomplete per l'argomento key in config set/unset."""
    keys = _all_valid_keys()
    return [(k, "") for k in keys if k.startswith(incomplete)]


# Valori hardcodati per autocomplete (chiave → lista valori)
_VALUE_CHOICES: Dict[str, List[str]] = {
    "ingestion.library": ["docling", "pymupdf4llm", "markitdown"],
    "chunking.method": ["recursive", "semantic", "sliding"],
    "chunking.separator": ['"\\n\\n"', '"\\n"', '" "', '"\\r\\n"'],
    "embedding.device": ["cpu", "cuda", "mps"],
    "retrieval.method": ["dense", "sparse", "hybrid"],
    "retrieval.query_mode": ["original", "hyde"],
    "pre_retrieval.stages.method": ["identity", "multi_query", "step_back", "least_to_most"],
    "post_retrieval.method": [
        "identity", "relevance", "mmr", "cross_encoder",
        "llm", "llm_chain_extract", "selective_context",
    ],
    "graph.on_chunk_change": ["lazy", "eager"],
    "graph.retriever": ["hybrid_cypher"],
    "graph.schema_mode": ["llm"],
    "graph.resolver": ["exact", "embedding"],
}

# Chiavi booleane: autocomplete true/false
_BOOL_KEYS: set[str] = {
    "graph.enabled",
}


def _value_autocomplete(
    ctx: typer.Context,
    args: list[str],
    incomplete: str,
) -> list[tuple[str, str]]:
    """Autocomplete per l'argomento value in config set.

    Suggerisce valori hardcodati se la chiave è nota, true/false per booleani,
    altrimenti nessun suggerimento.
    """
    key = args[1] if len(args) >= 2 else ""
    choices = _VALUE_CHOICES.get(key)
    if choices is not None:
        return [(v, "") for v in choices if v.startswith(incomplete)]
    if key in _BOOL_KEYS:
        return [(v, "") for v in ["true", "false"] if v.startswith(incomplete)]
    return []


# Precomputa la tabella chiavi per l'help (evita valutazione lazy nella docstring)
_KEYS_HELP_TABLE: str = _build_keys_help()

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


def _autodetect_scope(ws: Any) -> Optional[str]:
    """Rileva automaticamente lo scope in base al cwd.

    - Se il cwd è dentro una base registrata → restituisce il nome base.
    - Se il cwd è dentro il workspace (ma non in una base) → ``"defaults"``.
    - Altrimenti → ``None``.
    """
    base = resolve_base_from_cwd(ws)
    if base is not None:
        return base
    # Verifica se siamo dentro il workspace
    cwd = Path.cwd()
    ws_root = Path(ws.path).resolve()
    try:
        cwd.relative_to(ws_root)
        return "defaults"
    except ValueError:
        return None


def _resolve_base_scope(base: str, ws: Any) -> str:
    """Risolve una base specificata con -b nel nome esatto in ``ws.bases``.

    Supporta sia nomi semplici (``"papers1"``) che path relativi
    (``"Paper Accademici/papers1"``), cercando prima la chiave esatta
    e poi facendo fallback a ``normalize_base_name``.
    """
    if base in ws.bases:
        return base
    normalized = normalize_base_name(base)
    if normalized in ws.bases:
        return normalized
    return normalized  # sarà poi validato dal chiamante con messaggio di errore


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
    # Prova prima come chiave esatta (supporta basi nidificate "Paper/papers1")
    if scope in ws.bases:
        kb = ws.bases[scope]
        path = kb.path / dot / "base.toml"
        return path, f"base.toml ({scope})"
    # Fallback: normalizza (toglie trailing slash, ecc.)
    base_name = normalize_base_name(scope)
    if base_name in ws.bases:
        kb = ws.bases[base_name]
        path = kb.path / dot / "base.toml"
        return path, f"base.toml ({base_name})"
    typer.echo(f"Base non trovata: {base_name}", err=True)
    raise typer.Exit(1)


def _ensure_toml_exists(scope: str, ws: Any, ctx: Any) -> Path:
    """Crea il TOML se assente, restituisce il path."""
    dot = ctx.runtime_paths.dot_folder_name
    if scope == "defaults":
        path, _ = ensure_defaults_toml(ws.path, dot)
    else:
        base_name = _resolve_base_scope(scope, ws)
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
        metavar="[BASE]",
        help="Base da mostrare: nome o percorso di una base. "
             "Se omesso, rileva automaticamente la base dalla "
             "directory corrente o mostra i default del workspace.",
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra la configurazione effettiva (cascata risolta)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    config_loader = ctx.base_config_loader_factory(ws.path)
    logger.info("Visualizzazione configurazione")

    if scope:
        scope = resolve_base_name(scope, workspace=ws)
    else:
        scope = resolve_base_from_cwd(ws)

    if scope:
        logger.info("Configurazione per base: %s", scope)
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
    logger.info("Generazione defaults.toml template")

    defaults_path = ws.path / ctx.runtime_paths.dot_folder_name / "defaults.toml"

    if defaults_path.exists():
        logger.info("defaults.toml già esistente: %s", defaults_path)
        typer.echo(f"defaults.toml già esistente: {defaults_path}")
        overwrite = typer.confirm("Sovrascrivere?")
        if not overwrite:
            typer.echo("Annullato.")
            return

    defaults_path.parent.mkdir(parents=True, exist_ok=True)
    defaults_path.write_text(DEFAULTS_TOML_TEMPLATE, encoding="utf-8")
    logger.info("Template defaults.toml generato: %s", defaults_path)
    typer.echo(f"Template generato: {defaults_path}")


@app.command(
    help=f"Imposta una preferenza nel file TOML (defaults.toml o base.toml).\n\n"
    f"Auto-rileva se scrivere in defaults.toml o base.toml in base al cwd. "
    f"Usare -b per forzare una base specifica.\n\n"
    f"Chiavi disponibili:\n\n{_KEYS_HELP_TABLE}",
)
def set(  # noqa: A001 — ombreggia la builtin, ma è il nome CLI voluto
    key: str = typer.Argument(
        help="Chiave dotted (es. chunking.chunk_size).",
        autocompletion=_key_autocomplete,
    ),
    value: str = typer.Argument(
        help="Valore da assegnare.",
        autocompletion=_value_autocomplete,
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Nome base (se omesso: auto-rileva dal cwd o usa defaults)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Config set: base=%s, key=%s, value=%s", base, key, value)

    # Determina scope: -b esplicito → base, altrimenti auto-rileva
    if base:
        scope = _resolve_base_scope(base, ws)
        if scope not in ws.bases:
            typer.echo(f"Base non trovata: {scope}", err=True)
            raise typer.Exit(1)
    else:
        scope = _autodetect_scope(ws)
        if scope is None:
            typer.echo(
                "Errore: impossibile rilevare lo scope. "
                "Specificare una base con -b, o spostarsi in un workspace/base.",
                err=True,
            )
            raise typer.Exit(1)
        logger.info("Scope auto-rilevato: %s", scope)

    # Auto-rileva scope se omesso
    if scope is None:
        scope = _autodetect_scope(ws)
        if scope is None:
            typer.echo(
                "Errore: impossibile rilevare lo scope. "
                "Specificare 'defaults' o un nome base, oppure usare -w.",
                err=True,
            )
            raise typer.Exit(1)
        logger.info("Scope auto-rilevato: %s", scope)

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
    logger.info("Config salvata: %s = %s in %s", key, _format_value(new_value), label)
    typer.echo(f"{key} = {_format_value(new_value)} salvato in {label}")


@app.command()
def unset(
    key: str = typer.Argument(
        help="Chiave dotted da rimuovere (es. chunking.chunk_size).",
        autocompletion=_key_autocomplete,
    ),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Nome base (se omesso: auto-rileva dal cwd o usa defaults)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Rimuove una chiave dal file TOML (il valore torna al default della cascata)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Config unset: base=%s, key=%s", base, key)

    # Determina scope
    if base:
        scope = _resolve_base_scope(base, ws)
        if scope not in ws.bases:
            typer.echo(f"Base non trovata: {scope}", err=True)
            raise typer.Exit(1)
    else:
        scope = _autodetect_scope(ws)
        if scope is None:
            typer.echo(
                "Errore: impossibile rilevare lo scope. "
                "Specificare una base con -b, o spostarsi in un workspace/base.",
                err=True,
            )
            raise typer.Exit(1)
        logger.info("Scope auto-rilevato: %s", scope)

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
    logger.info("Config chiave rimossa: %s da %s", key, label)
    typer.echo(f"Chiave '{key}' rimossa da {label}.")


@app.command("edit")
def edit_cmd(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Nome base (se omesso: auto-rileva dal cwd o usa defaults)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Apre il file TOML nell'editor ($EDITOR, fallback nano)."""
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    logger.info("Config edit: base=%s", base)

    # Determina scope
    if base:
        scope = _resolve_base_scope(base, ws)
        if scope not in ws.bases:
            typer.echo(f"Base non trovata: {scope}", err=True)
            raise typer.Exit(1)
    else:
        scope = _autodetect_scope(ws)
        if scope is None:
            typer.echo(
                "Errore: impossibile rilevare lo scope. "
                "Specificare una base con -b, o spostarsi in un workspace/base.",
                err=True,
            )
            raise typer.Exit(1)
        logger.info("Scope auto-rilevato: %s", scope)

    # Assicurati che il file esista
    toml_path, label = _resolve_scope(scope, ws, ctx)
    _ensure_toml_exists(scope, ws, ctx)

    editor = os.environ.get("EDITOR", "nano")
    logger.info("Apertura editor %s per %s", editor, label)
    typer.echo(f"Apertura {label} con {editor}...")
    result = subprocess.run([editor, str(toml_path)])
    if result.returncode != 0:
        typer.echo(f"Editor terminato con codice {result.returncode}.", err=True)
        raise typer.Exit(result.returncode)

    typer.echo(f"File salvato. Usa 'ks config show' per verificare la configurazione.")


@app.command(name="refresh")
def refresh_config(
    base: Optional[str] = typer.Option(None, "-b", "--base", help="Nome base da ricaricare."),
    all_bases: bool = typer.Option(False, "--all", help="Ricarica tutte le basi del workspace."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Path workspace."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Ricarica e valida la configurazione TOML dal disco (feat-014).

    Dopo modifiche manuali ai file TOML (``defaults.toml`` / ``base.toml``,
    ignorati dal watcher), ricarica la configurazione e la valida:
    TOML malformato o chiavi sconosciute → errore immediato. Poi confronta
    con i valori registrati nello stato: se ``embedding.model`` /
    ``chunking.method`` / ``ingestion.library`` sono cambiati, segnala il
    reindex necessario (``ks reindex <base> --...``) oppure blocca con
    errore se la collection non è vuota (come ``add_file``).
    """
    ctx = get_context(verbose=verbose)
    ws = get_workspace(ctx, workspace)
    manager = ctx.base_manager_factory(ws)
    logger.info("Config refresh")

    # 1. Determina i target
    if all_bases:
        targets = list(ws.bases)
    elif base:
        base = resolve_base_name(base, workspace=ws)
        if base not in ws.bases:
            typer.echo(f"Base non trovata: {base}", err=True)
            raise typer.Exit(1)
        targets = [base]
    else:
        scope = _autodetect_scope(ws)
        if scope is None or scope == "defaults":
            typer.echo(
                "Specifica una base con -b oppure usa --all.",
                err=True,
            )
            raise typer.Exit(1)
        targets = [scope]

    # 2. Valida i file TOML coinvolti (malformato / chiavi sconosciute)
    loader = ctx.base_config_loader_factory(ws.path)
    toml_paths = [loader.defaults_toml_path]
    for bn in targets:
        toml_paths.append(loader.base_toml_path(bn))
    for p in toml_paths:
        if p.exists():
            _validate_toml_file(p)

    # 3. Ricarica e confronta con i valori registrati
    any_change = False
    for bn in targets:
        try:
            config, changes = manager.reload_and_check_config(bn)
        except Exception as exc:
            typer.echo(f"Errore nel ricaricamento di '{bn}': {exc}", err=True)
            raise typer.Exit(1)
        summary = (
            f"modello={config.embedding.model}, "
            f"chunking={config.chunking.method}, "
            f"library={config.ingestion.library}"
        )
        if not changes:
            typer.echo(f"Configurazione ricaricata per '{bn}': {summary}. Nessun cambiamento.")
            continue
        any_change = True
        typer.echo(f"Configurazione ricaricata per '{bn}': {summary}.")
        for field, old, new in changes:
            typer.echo(f"  ⚠ {field}: '{old}' -> '{new}'")
        try:
            manager.check_config_change(bn, config=config)
            typer.echo(
                "  Reindex non necessario (collection vuota o registrati assenti)."
            )
        except ConfigChangeBlockedError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
    if not any_change:
        typer.echo("Configurazione ricaricata: nessun cambiamento rilevato.")


def _validate_toml_file(path: Path) -> None:
    """Valida un file TOML: malformato o chiavi sconosciute → errore (feat-014)."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        typer.echo(f"Configurazione non valida in {path}: {exc}", err=True)
        raise typer.Exit(1)
    for section, values in data.items():
        if section not in _VALID_SECTIONS:
            typer.echo(
                f"Configurazione non valida in {path}: sezione [{section}] sconosciuta.",
                err=True,
            )
            raise typer.Exit(1)
        if not isinstance(values, dict):
            typer.echo(
                f"Configurazione non valida in {path}: [{section}] non è una sezione.",
                err=True,
            )
            raise typer.Exit(1)
        for key in values:
            if key == "params":
                continue  # dict libero di parametri della strategy
            try:
                cfg = BaseConfig()
                if not hasattr(getattr(cfg, section), key):
                    raise AttributeError
            except AttributeError:
                typer.echo(
                    f"Configurazione non valida in {path}: campo '{section}.{key}' "
                    "sconosciuto.",
                    err=True,
                )
                raise typer.Exit(1)


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
