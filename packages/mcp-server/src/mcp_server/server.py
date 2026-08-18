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

    # --- Cache a livello di server (bug-027): un solo SearchService per
    # workspace, un solo client Chroma, un solo config loader. Il tool
    # search veniva costruito per-riconstruito a ogni chiamata e per ogni
    # base: il modello di embedding veniva RICARICATO da disco a ogni base
    # ("Loading weights" ripetuto nel log) → request timed out.
    _search_services: dict[Path, Any] = {}
    _chroma_clients: dict[Path, Any] = {}
    _config_loaders: dict[Path, Any] = {}
    _graph_services: dict[Path, Any] = {}

    def _get_search_service(ws):
        """SearchService condiviso per workspace (cache embedder interna)."""
        if ws.path not in _search_services:
            from knowledge_base.search_service import SearchService
            from knowledge_base.strategies import embedding_registry

            def embedder_factory(model_name: str):
                return embedding_registry.get(model_name)()

            _search_services[ws.path] = SearchService(
                embedder_factory=embedder_factory
            )
        return _search_services[ws.path]

    def _get_config_loader(ws):
        """BaseConfigLoader condiviso per workspace (evita warning ripetuti)."""
        if ws.path not in _config_loaders:
            from knowledge_base.base_config import BaseConfigLoader

            _config_loaders[ws.path] = BaseConfigLoader(
                workspace_path=ws.path,
                dot_folder_name=".knowledge-space",
            )
        return _config_loaders[ws.path]

    def _get_chroma_client(ws):
        """PersistentClient Chroma condiviso per workspace."""
        if ws.path not in _chroma_clients:
            from chromadb import PersistentClient

            chroma_path = ws.path / ".knowledge-space" / "chroma"
            _chroma_clients[ws.path] = PersistentClient(path=str(chroma_path))
        return _chroma_clients[ws.path]

    def _get_graph_service(ws):
        """GraphSearchService condiviso per workspace; ricreato solo se
        l'insieme delle basi cambia (embedder del grafo resta in memoria)."""
        key = (ws.path, tuple(sorted(ws.bases.keys())))
        if key not in _graph_services:
            from knowledge_base.graph_search_service import GraphSearchService

            graph_manager = graph_manager_factory(ws)
            _graph_services[key] = GraphSearchService(graph_manager)
        return _graph_services[key]

    def _prewarm() -> None:
        """Pre-carica in background gli embedder delle basi del workspace
        attivo (bug-027).

        Il primo load di un SentenceTransformer è il costo dominante
        (bge-m3 ~16s su CPU): senza prewarm la prima ricerca MCP dopo il
        restart del serve va in timeout sul client. Eseguita in un thread
        daemon dai trasporti, gli errori non sono fatali.
        """
        try:
            ws = _get_active_workspace()
        except Exception:
            return
        service = _get_search_service(ws)
        config_loader = _get_config_loader(ws)
        for bname, kb in ws.bases.items():
            if not kb.files:
                continue
            try:
                config = config_loader.load(bname)
                embedder = service._get_embedder(config.embedding.model)  # noqa: SLF001
                # L'istanziazione è lazy: i pesi si caricano al primo
                # embed. Una query dummy forza il load in background così
                # la prima ricerca MCP non paga i ~16s di bge-m3.
                embedder.embed([" "])
                logger.info(
                    "Prewarm: embedder %s pronto (base %s)",
                    config.embedding.model,
                    bname,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Prewarm fallito (base %s): %s", bname, exc)

    server.prewarm = _prewarm  # type: ignore[attr-defined]

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

            from knowledge_base.knowledge_base_manager import chroma_collection_name

            if base_name:
                if base_name not in ws.bases:
                    return f"Base non trovata: {base_name}"
                bases_to_search = {base_name: ws.bases[base_name]}
            else:
                bases_to_search = ws.bases

            service = _get_search_service(ws)
            config_loader = _get_config_loader(ws)
            chroma_client = _get_chroma_client(ws)

            results: list[str] = []
            for bname, kb in bases_to_search.items():
                if not kb.files:
                    continue
                try:
                    config = config_loader.load(bname)
                    collection_name = chroma_collection_name(bname)
                    retrieved = service.search(
                        query,
                        config=config.to_search_config(),
                        top_k=top_k,
                        kb=kb,
                        collection_factory=lambda cn=collection_name: chroma_client.get_collection(name=cn),
                    )
                    for r in retrieved:
                        results.append(
                            f"[{bname}] {r.chunk_id} (score={r.score:.4f}): {r.text[:120]}"
                        )
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

            query = args["query"]
            top_k = args.get("top_k", 5)
            service = _get_graph_service(ws)
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
    # Prewarm: carica gli embedder del workspace attivo in background così
    # la prima ricerca non paga il load del modello (bug-027).
    import threading

    threading.Thread(target=server.prewarm, daemon=True).start()
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
    # Prewarm: carica gli embedder del workspace attivo in background così
    # la prima ricerca non paga il load del modello (bug-027).
    import threading

    threading.Thread(target=server.prewarm, daemon=True).start()
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
