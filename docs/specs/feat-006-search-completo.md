# Feature 006 — Comando `ks search` completo (pre-retrieval, retrieval, post-retrieval)

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** alta

## Obiettivo

`ks search` deve usare `SearchService` con la pipeline completa (pre/post-retrieval) e tutte le strategy (dense, sparse, hybrid), leggendo la configurazione dal TOML.

## Causa

Oggi `search.py` fa tutto inline: embedder hardcoded, solo dense, nessun pre/post-retrieval, nessun TOML. `SearchService` esiste ma non è usato da nessuno.

File coinvolti:
- `src/knowledge_space/cli/search.py` — implementazione inline da sostituire
- `packages/knowledge-base/src/knowledge_base/search_service.py` — orchestratore già pronto
- `packages/knowledge-base/src/knowledge_base/strategies/retrieval.py` — dense, sparse, hybrid
- `packages/knowledge-base/src/knowledge_base/base_config.py` — sezioni `[pre_retrieval]`, `[retrieval]`, `[post_retrieval]`
- `src/knowledge_space/context.py` — `AppContext` (ha già `llm_factory`, `embedder_factory`)

## Fix (KISS)

Sostituire il corpo di `search_command()`: invece di embeddare e chiamare Chroma a mano, istanziare `SearchService` e chiamare `service.search()`.

### Dettaglio

```python
# Per ogni base attiva, crea un SearchService con la config da TOML:
config_loader = ctx.base_config_loader_factory(ws.path)
base_config = config_loader.load(bname)
search_config = base_config.to_search_config()  # nuovo metodo nel BaseConfig

# Collection factory per quella base
def make_collection():
    client = PersistentClient(path=str(chroma_path))
    return client.get_collection(name=f"ks_{bname}")

service = SearchService(
    llm_factory=ctx.llm_factory,       # c'è già in AppContext
    embedder_factory=ctx.embedder_factory,
    collection_factory=make_collection,
)
results = service.search(query, config=search_config, top_k=top_k)
```

### `BaseConfig.to_search_config()`

Nuovo metodo che converte le sezioni TOML in `SearchConfig`:

```python
def to_search_config(self) -> SearchConfig:
    stages = []
    for s in self.pre_retrieval.stages:
        stages.append(PreRetrievalStageConfig(method=s.method, params=s.params))
    return SearchConfig(
        pre_retrieval=stages,
        retrieval=RetrievalConfig(
            method=self.retrieval.method,
            query_mode=self.retrieval.query_mode,
            top_k=self.retrieval.top_k,
            params=self.retrieval.params,
        ),
        post_retrieval=PostRetrievalConfig(
            method=self.post_retrieval.method,
            params=self.post_retrieval.params,
        ),
    )
```

### Filtro active (già fatto)

I filtri pre/post retrieval già implementati vanno mantenuti ma spostati PRIMA della chiamata a `service.search()` (filtro basi) e DOPO (filtro chunk). Il SearchService non sa nulla del Workspace — filtrare fuori è corretto.

### CLI flag aggiuntivi

Nessuno. L'unico override è `--top-k` (già esistente). I metodi si configurano nel TOML.

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/search.py` | Riscrivere corpo: `SearchService` al posto dell'embedding inline |
| `packages/knowledge-base/src/knowledge_base/base_config.py` | Nuovo metodo `to_search_config()` |
| `tests/test_cli.py` | Test: `ks search` usa `SearchService` (mock) |

### Verifica

```bash
ks search "machine learning" --top-k 5
# → risultati da tutte le basi attive, ordinati per score
```
