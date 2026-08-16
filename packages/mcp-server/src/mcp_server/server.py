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
    graph_manager_factory: Any = None,
) -> Server:
    """Costruisce il server MCP con tutti i tool registrati.

    Args:
        workspace_manager: manager CRUD workspace.
        config_path_for: factory per il path di config.json.
        state_home: directory di stato dell'applicazione.
        graph_manager_factory: factory ``(Workspace) -> GraphManager``
            (refactor-001, opzionale).

    Returns:
        Server MCP configurato.
    """
    server = Server(
        name="knowledge-space",
        version="0.1.0",
        description="Knowledge Space — gestione basi di conoscenza con ricerca vettoriale.",
    )

    # --- Tool definitions ---
    # L'MCP espone SOLO la lettura dello stato e la ricerca, sempre
    # rispetto al workspace attivo (ultimo usato). Niente operazioni di
    # scrittura (add/remove/ingest/sync) né elenchi globali.

    _TOOLS = [
        types.Tool(
            name="base_list",
            description="Elenca le basi del workspace attivo.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="domain_list",
            description="Elenca i domini del workspace attivo.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="search",
            description=(
                "Ricerca vettoriale nel workspace attivo "
                "(rispetta domini/basi/file/chunk attivi)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
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
                "required": ["query"],
            },
        ),
        types.Tool(
            name="graph_status",
            description=(
                "Stato del grafo di conoscenza del workspace attivo "
                "(connessione Neo4j, basi, chunk, entità, relazioni)."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="graph_search",
            description=(
                "Ricerca sul grafo di conoscenza del workspace attivo "
                "(rispetta domini/basi/file/chunk attivi come la ricerca "
                "vettoriale)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query di ricerca."},
                    "base": {
                        "type": "string",
                        "description": "Nome base (opzionale, non usato: "
                        "il filtro attivi è automatico).",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Numero massimo di risultati (default 5).",
                    },
                },
                "required": ["query"],
            },
        ),
    ]

    # --- Handler: list_tools ---

    async def _list_tools(
        ctx: ServerRequestContext,
        params: types.PaginatedRequestParams,
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=_TOOLS)

    server.add_request_handler("tools/list", types.PaginatedRequestParams, _list_tools)

    # --- Helper: workspace attivo ---

    def _get_active_workspace():
        """Carica il workspace attivo (ultimo usato nel GlobalIndex)."""
        ws_path = workspace_manager.get_last_workspace()
        if ws_path is None:
            raise ValueError(
                "Nessun workspace attivo. Attivane uno con 'ks workspace activate'."
            )
        ws = workspace_manager.load(ws_path)
        return ws

    # --- Handler: call_tool ---

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

    server.add_request_handler("tools/call", types.CallToolRequestParams, _call_tool)

    async def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
        """Dispatcha la chiamata al tool e restituisce il risultato come testo."""

        if name == "base_list":
            ws = _get_active_workspace()
            if not ws.bases:
                return "Nessuna base nel workspace."
            lines = []
            for bname, kb in ws.bases.items():
                n_files = len(kb.files)
                n_chunks = sum(len(f.chunks) for f in kb.files.values())
                stato = "attiva" if kb.active else "inattiva"
                lines.append(f"{bname}: {n_files} file, {n_chunks} chunk ({stato})")
            return "\n".join(lines)

        elif name == "domain_list":
            ws = _get_active_workspace()
            if not ws.domains:
                return "Nessun dominio nel workspace."
            lines = []
            for d in ws.domains:
                stato = "attivo" if d.active else "inattivo"
                basi = ", ".join(d.base_names) or "(vuoto)"
                lines.append(f"{d.name}: {stato} — basi: {basi}")
            return "\n".join(lines)

        elif name == "search":
            ws = _get_active_workspace()
            query = args["query"]
            base_name = args.get("base_name")
            top_k = args.get("top_k", 5)

            from knowledge_base.base_config import BaseConfigLoader
            from knowledge_base.knowledge_base_manager import chroma_collection_name
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
                    col = client.get_collection(name=chroma_collection_name(bname))

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

        elif name == "graph_status":
            ws = _get_active_workspace()
            if graph_manager_factory is None:
                return "Grafo non disponibile (graph_manager_factory non configurata)."
            graph_manager = graph_manager_factory(ws)
            info = graph_manager.status()
            if not info.get("connected"):
                return "Neo4j non raggiungibile."
            if "error" in info:
                return f"Errore lettura conteggi: {info['error']}"
            bases = ", ".join(info.get("bases", [])) or "(nessuna)"
            return (
                f"Connessione: OK\n"
                f"Basi: {bases}\n"
                f"Documenti: {info.get('document', 0)}\n"
                f"Chunk: {info.get('chunk', 0)}\n"
                f"Entità: {info.get('entity', 0)}\n"
                f"Relazioni: {info.get('relations', 0)}"
            )

        elif name == "graph_search":
            ws = _get_active_workspace()
            if graph_manager_factory is None:
                return "Grafo non disponibile (graph_manager_factory non configurata)."
            from knowledge_base.graph_search_service import GraphSearchService

            query = args["query"]
            top_k = args.get("top_k", 5)
            graph_manager = graph_manager_factory(ws)
            service = GraphSearchService(graph_manager)
            results = service.search(ws, query, top_k=top_k)
            if not results:
                return "Nessun risultato trovato."
            lines = []
            for r in results:
                entities = ", ".join(r.metadata.get("entities", []))
                lines.append(
                    f"[{r.score:.4f}] {r.chunk_id} — {r.text[:200]}"
                    + (f" (entità: {entities})" if entities else "")
                )
            return "\n".join(lines)

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
    graph_manager_factory: Any = None,
) -> None:
    """Avvia il server MCP su trasporto stdio.

    Args:
        workspace_manager: manager CRUD workspace.
        config_path_for: factory per il path di config.json.
        state_home: directory di stato dell'applicazione.
        graph_manager_factory: factory GraphManager (refactor-001).
    """
    import mcp.server.stdio as stdio_mod

    server = _make_server(
        workspace_manager,
        config_path_for,
        state_home=state_home,
        graph_manager_factory=graph_manager_factory,
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
    port: int = 8456,
    mount_path: str = "knowledge-space",
    graph_manager_factory: Any = None,
) -> None:
    """Avvia il server MCP su trasporto Streamable HTTP.

    L'app MCP viene montata sotto ``/<mount_path>``: l'endpoint finale è
    ``http://<host>:<port>/<mount_path>/mcp`` (es.
    ``http://127.0.0.1:8456/knowledge-space/mcp``).

    Args:
        workspace_manager: manager CRUD workspace.
        config_path_for: factory per il path di config.json.
        state_home: directory di stato dell'applicazione.
        host: indirizzo di bind.
        port: porta di ascolto.
        mount_path: prefisso URL sotto cui montare l'app MCP.
        graph_manager_factory: factory GraphManager (refactor-001).
    """
    import uvicorn

    server = _make_server(
        workspace_manager,
        config_path_for,
        state_home=state_home,
        graph_manager_factory=graph_manager_factory,
    )
    logger.info(
        "Avvio server MCP su %s:%s/%s/mcp", host, port, mount_path
    )

    mcp_app = server.streamable_http_app()
    # L'app espone una sola route "/mcp": la ricostruisce sotto il
    # prefisso (es. /knowledge-space/mcp). Niente Mount: il lifespan
    # della sub-app non verrebbe avviato da uvicorn.
    from starlette.routing import Route

    for i, route in enumerate(mcp_app.router.routes):
        if getattr(route, "path", "") == "/mcp":
            mcp_app.router.routes[i] = Route(
                path=f"/{mount_path}/mcp",
                endpoint=route.endpoint,
                methods=route.methods,
                name=route.name,
            )
    config = uvicorn.Config(mcp_app, host=host, port=port, log_level="info")
    srv = uvicorn.Server(config)
    await srv.serve()
