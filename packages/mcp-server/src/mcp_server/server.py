"""Server MCP per Knowledge Space.

Espone le operazioni principali come tool MCP, wrappando i manager
già esistenti (WorkspaceManager, KnowledgeBaseManager, ecc.).
Supporta trasporto **stdio** (default) e **SSE** (opzionale).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server import Server, ServerRequestContext

from knowledge_base.persistence import GlobalIndex
from knowledge_base.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configurazione
# --------------------------------------------------------------------------- #

# Funzione che, dato il path di un workspace, restituisce il path del suo
# file di configurazione (config.json).
ConfigPathFor = Any  # Callable[[Path], Path]


def _make_server(
    workspace_manager: WorkspaceManager,
    config_path_for: ConfigPathFor,
    *,
    state_home: Path,
) -> Server:
    """Costruisce il server MCP con tutti i tool registrati.

    Args:
        workspace_manager: manager CRUD workspace.
        config_path_for: factory per il path di config.json.
        state_home: directory di stato dell'applicazione.

    Returns:
        Server MCP configurato.
    """
    from knowledge_base.base_config import BaseConfigLoader
    from knowledge_base.knowledge_base_manager import KnowledgeBaseManager

    server = Server(
        name="knowledge-space",
        version="0.1.0",
        description="Knowledge Space — gestione basi di conoscenza con ricerca vettoriale.",
    )

    # --- Tool definitions ---

    _TOOLS = [
        types.Tool(
            name="workspace_list",
            description="Elenca tutti i workspace registrati.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="workspace_add",
            description="Registra un nuovo workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path assoluto del workspace."},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="workspace_remove",
            description="Rimuove un workspace dal registro.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path assoluto del workspace."},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="base_list",
            description="Elenca le basi di un workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "Path del workspace. Se omesso usa l'ultimo usato.",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="base_add",
            description="Aggiunge una nuova base a un workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string", "description": "Path del workspace."},
                    "base_path": {"type": "string", "description": "Path della cartella base."},
                },
                "required": ["workspace_path", "base_path"],
            },
        ),
        types.Tool(
            name="file_ingest",
            description="Ingestisce un file in una base.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string", "description": "Path del workspace."},
                    "base_name": {"type": "string", "description": "Nome della base."},
                    "file_path": {"type": "string", "description": "Path del file da ingestire."},
                },
                "required": ["workspace_path", "base_name", "file_path"],
            },
        ),
        types.Tool(
            name="search",
            description="Ricerca vettoriale nelle basi di un workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string", "description": "Path del workspace."},
                    "query": {"type": "string", "description": "Query di ricerca."},
                    "base_name": {
                        "type": "string",
                        "description": "Nome della base. Se omesso cerca in tutte.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Numero massimo di risultati (default 5).",
                    },
                },
                "required": ["workspace_path", "query"],
            },
        ),
        types.Tool(
            name="sync",
            description="Forza la sincronizzazione di un workspace col filesystem.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string", "description": "Path del workspace."},
                },
                "required": ["workspace_path"],
            },
        ),
    ]

    # --- Handler: list_tools ---

    @server.on_list_tools  # type: ignore[attr-defined]
    async def _list_tools(
        ctx: ServerRequestContext,
        params: types.PaginatedRequestParams | None = None,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=_TOOLS)

    # --- Helper: risolvi workspace ---

    def _resolve_ws_path(workspace_path: str) -> Path:
        p = Path(workspace_path).resolve()
        if not p.is_dir():
            raise ValueError(f"Workspace non trovato: {p}")
        return p

    def _get_workspace(workspace_path: str):
        ws_path = _resolve_ws_path(workspace_path)
        return workspace_manager.load(ws_path)

    def _get_base_manager(workspace):
        from knowledge_base.base_config import BaseConfigLoader

        config_loader = BaseConfigLoader(
            workspace_path=workspace.path,
            dot_folder_name=".knowledge-space",
        )
        return KnowledgeBaseManager(
            workspace=workspace,
            config_loader=config_loader,
            config_path_for=config_path_for,
        )

    # --- Handler: call_tool ---

    @server.on_call_tool  # type: ignore[attr-defined]
    async def _call_tool(
        ctx: ServerRequestContext,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        name = params.name
        args = params.arguments or {}
        logger.info("MCP tool call: %s(%s)", name, args)

        try:
            result_text = await _dispatch_tool(name, args)
            logger.info("MCP tool %s completato", name)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=result_text)]
            )
        except Exception as exc:
            logger.error("MCP tool %s errore: %s", name, exc)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Errore: {exc}")],
                isError=True,
            )

    async def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
        """Dispatcha la chiamata al tool e restituisce il risultato come testo."""

        if name == "workspace_list":
            workspaces = workspace_manager.list()
            if not workspaces:
                return "Nessun workspace registrato."
            lines = [str(p) for p in workspaces]
            return "\n".join(lines)

        elif name == "workspace_add":
            path = Path(args["path"]).resolve()
            added = workspace_manager.add(path)
            if added:
                return f"Workspace registrato: {path}"
            return f"Workspace già registrato: {path}"

        elif name == "workspace_remove":
            path = Path(args["path"]).resolve()
            removed = workspace_manager.remove(path)
            if removed:
                return f"Workspace rimosso: {path}"
            return f"Workspace non trovato: {path}"

        elif name == "base_list":
            ws = _get_workspace(args["workspace_path"])
            if not ws.bases:
                return "Nessuna base nel workspace."
            lines = []
            for bname, kb in ws.bases.items():
                n_files = len(kb.files)
                n_chunks = sum(len(f.chunks) for f in kb.files.values())
                lines.append(f"{bname}: {n_files} file, {n_chunks} chunk")
            return "\n".join(lines)

        elif name == "base_add":
            ws = _get_workspace(args["workspace_path"])
            bm = _get_base_manager(ws)
            base_path = Path(args["base_path"]).resolve()
            kb = bm.add(base_path)
            return f"Base aggiunta: {base_path.name}"

        elif name == "file_ingest":
            ws = _get_workspace(args["workspace_path"])
            bm = _get_base_manager(ws)
            base_name = args["base_name"]
            file_path = Path(args["file_path"]).resolve()
            entry = bm.add_file(base_name, file_path)
            return (
                f"File ingerito: {entry.name} "
                f"(file_id={entry.file_id}, {len(entry.chunks)} chunk)"
            )

        elif name == "search":
            ws = _get_workspace(args["workspace_path"])
            query = args["query"]
            base_name = args.get("base_name")
            top_k = args.get("top_k", 5)

            from knowledge_base.base_config import BaseConfigLoader
            from knowledge_base.search_service import SearchService

            config_loader = BaseConfigLoader(
                workspace_path=ws.path,
                dot_folder_name=".knowledge-space",
            )

            # Determina la base
            if base_name:
                if base_name not in ws.bases:
                    return f"Base non trovata: {base_name}"
                bases_to_search = {base_name: ws.bases[base_name]}
            else:
                bases_to_search = ws.bases

            results: list[str] = []
            for bname, kb in bases_to_search.items():
                if not kb.files:
                    continue
                try:
                    config = config_loader.load(bname)
                    from knowledge_base.strategies import embedding_registry

                    embedder_cls = embedding_registry.get(config.embedding.model)
                    embedder = embedder_cls()

                    from chromadb import PersistentClient

                    chroma_path = ws.path / ".knowledge-space" / "chroma"
                    if not chroma_path.exists():
                        continue
                    client = PersistentClient(path=str(chroma_path))
                    col = client.get_collection(name=f"ks_{bname}")

                    query_vec = embedder.embed([query])[0]
                    res = col.query(
                        query_embeddings=[query_vec],
                        n_results=min(top_k, col.count()),
                        include=["documents", "metadatas", "distances"],
                    )
                    if res and res["ids"] and res["ids"][0]:
                        for i, cid in enumerate(res["ids"][0]):
                            doc = res["documents"][0][i] if res["documents"] else ""
                            dist = res["distances"][0][i] if res["distances"] else 0.0
                            score = 1.0 - dist
                            results.append(f"[{bname}] {cid} (score={score:.4f}): {doc[:120]}")
                except Exception as exc:
                    results.append(f"[{bname}] errore: {exc}")

            if not results:
                return "Nessun risultato trovato."
            return "\n".join(results[:top_k])

        elif name == "sync":
            ws = _get_workspace(args["workspace_path"])
            workspace_manager.sync(ws)
            n_bases = len(ws.bases)
            return f"Sincronizzazione completata: {n_bases} basi scoperte."

        else:
            raise ValueError(f"Tool sconosciuto: {name}")

    return server


# --------------------------------------------------------------------------- #
# Entry point per trasporto stdio
# --------------------------------------------------------------------------- #


async def run_stdio(
    workspace_manager: WorkspaceManager,
    config_path_for: ConfigPathFor,
    *,
    state_home: Path,
) -> None:
    """Avvia il server MCP su trasporto stdio.

    Args:
        workspace_manager: manager CRUD workspace.
        config_path_for: factory per il path di config.json.
        state_home: directory di stato dell'applicazione.
    """
    import mcp.server.stdio as stdio_mod

    server = _make_server(
        workspace_manager,
        config_path_for,
        state_home=state_home,
    )
    logger.info("Avvio server MCP su stdio")

    async with stdio_mod.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# --------------------------------------------------------------------------- #
# Entry point per trasporto SSE
# --------------------------------------------------------------------------- #


async def run_sse(
    workspace_manager: WorkspaceManager,
    config_path_for: ConfigPathFor,
    *,
    state_home: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:
    """Avvia il server MCP su trasporto SSE (HTTP).

    Args:
        workspace_manager: manager CRUD workspace.
        config_path_for: factory per il path di config.json.
        state_home: directory di stato dell'applicazione.
        host: indirizzo di bind.
        port: porta di ascolto.
    """
    import uvicorn

    server = _make_server(
        workspace_manager,
        config_path_for,
        state_home=state_home,
    )
    logger.info("Avvio server MCP su SSE %s:%s", host, port)

    app = server.streamable_http_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()
