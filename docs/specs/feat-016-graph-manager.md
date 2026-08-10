# Feature 016 — GraphManager: orchestratore della pipeline GraphRAG

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** alta (prerequisito di feat-017/018/019)

## Obiettivo

`GraphManager` che esegue la pipeline completa su un workspace: KSChunkLoader → schema → EntityRelationExtractor → Neo4jWriter → resolver. Oggi i pezzi esistono in `knowledge_base/graph/` ma nessuno li collega.

## Causa

`packages/knowledge-base/src/knowledge_base/graph/` contiene store, schema, extraction, resolver, writer, chunk_loader e retriever (82 test) ma non esiste un manager che li orchestri. `bootstrap.graph_store_factory` è già previsto ma inutilizzato.

## Fix (KISS)

1. **`GraphManager`** in `packages/knowledge-base/src/knowledge_base/graph_manager.py`:
   - `__init__(workspace, config_loader, graph_store_factory, llm_factory)` — store costruito da `GraphConfigData` (bolt_uri, database) in `graph.json` o default env `NEO4J_URI`/`NEO4J_AUTH`.
   - `build_graph()` — full build: per ogni base attiva, `KSChunkLoader` → estrazione entità (LLM) → `Neo4jWriter.write_nodes/edges` (MERGE idempotente) → resolver.
   - `sync_base(base_name)` — ri-estrae solo chunk nuovi/modificati (via `content_hash`), idempotente.
   - `remove_base(base_name)` — `delete_file_nodes` per ogni file della base.
   - Se `graph.enabled == False` o nessun LLM configurato → no-op con warning (l'estrazione entità richiede LLM; la parte lexical/chunk la si può costruire comunque se `schema_mode == "manuale"`).

2. **Persistenza**: `GraphConfigData` in `<workspace>/.knowledge-space/graph/graph.json` (bolt_uri, database, schema_ref, embedding_model) — salvato al primo `build_graph()`.

3. **Schema**: se `schema.json` esiste → load; altrimenti secondo `schema_mode` (`manuale` da TOML, `EXTRACTED` via LLM, `FREE` senza schema).

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/graph_manager.py` | **Nuovo**: GraphManager |
| `src/knowledge_space/bootstrap.py` | Cablare `graph_store_factory` in AppContext |

### Verifica

```bash
ks config set graph.enabled true
ks graph init -w ~/ws2
# → "Grafo costruito: N entità, M relazioni"
ks graph status -w ~/ws2
# → "Neo4j connesso, 12 basi, 349 chunk, 120 entità"
```
