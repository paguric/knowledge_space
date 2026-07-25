# Documentazione — Knowledge Space

> **Aggiornato:** 22 luglio 2026

## Piano di progetto

- [**Roadmap unificata**](roadmap.md) — stato, step, dipendenze, priorità. **Fonte di verità per la pianificazione.**

## Specifiche tecniche

### Architettura e configurazione

| # | File | Contenuto |
|---|------|-----------|
| 10 | [Architettura](10-architecture.md) | Organizzazione pacchetti, separazione responsabilità, GraphRAG module |
| 11 | [Ciclo di vita app](11-app-lifecycle.md) | CLI standalone vs backend process, PID, signal handling, MCP bridge |
| 12 | [Deployment](12-deployment.md) | Docker, .exe, CI/CD *(provvisorio)* |
| 20 | [Modello di dominio](20-data-model.md) | Pydantic models, persistenza ibrida, schema JSON |
| 30 | [Configurazione](30-configuration.md) | TOML per-base, cascata default, strategy registry, trigger reindex |
| 31 | [Configurazione app](31-configurazione-app.md) | RuntimePaths, UserSettings, env vars |

### Pipeline di indicizzazione

| # | File | Contenuto | Step |
|---|------|-----------|------|
| 40 | [GraphRAG](40-graph.md) | Pipeline Neo4j, KSChunkLoader, entity resolution, retrieval su grafo | 8-bis |
| 45 | [Indicizzazione incrementale](45-indexing-incrementale.md) | 5 trigger reindex, file_id stabile, diff hash | 7 |
| 50 | [Ingestion](50-ingestion.md) | Docling, PyMuPDF4LLM, markitdown, identity | 4 |
| 60 | [Chunking](60-chunking.md) | fixed_size, recursive, semantic, sentence, markdown | 5 |
| 70 | [Embedding](70-embedding.md) | 12 modelli, registry, validazione contesto | 6 |
| 75 | [LLM](75-llm.md) | LLMStrategy, registry, per-component config, fallback | 6-bis |
| 80 | [Retrieval](80-retrieval.md) | pre-retrieval, dense/sparse/hybrid, rerank, compress | 8 |

### Interfacce utente

| # | File | Contenuto | Step |
|---|------|-----------|------|
| 85 | [CLI](85-cli.md) | Comandi Typer, autocompletamento, profili | 13 |
| 86 | [MCP](86-mcp-server.md) | Server MCP stdio/SSE, tools | 14 |
| 87 | [REST API](87-rest-api.md) | FastAPI, endpoints, CORS | 15 |

## File deprecati

Conservati per riferimento storico. Non aggiornare.

- ~~90-roadmap-overview.md~~ → [roadmap.md](roadmap.md)
- ~~91a-roadmap-fase1-ingestione.md~~ → [roadmap.md §2](roadmap.md#2--fase-1a-ingestione-e-indicizzazione-vettoriale)
- ~~91b-roadmap-fase1-ricerca.md~~ → [roadmap.md §3](roadmap.md#3--fase-1b-ricerca-sui-documenti-processati)
- ~~91c-roadmap-fase1-graphrag.md~~ → [roadmap.md §4](roadmap.md#4--fase-1c-graphrag)
- ~~92-roadmap-fase2.md~~ → [roadmap.md §5](roadmap.md#5--fase-2-testing-e-validazione)
- ~~93-roadmap-fase3.md~~ → [roadmap.md §6](roadmap.md#6--fase-3-mcp--cli)
- ~~94-roadmap-fase4.md~~ → [roadmap.md §7](roadmap.md#7--fase-4-rest--frontend)
- ~~32-defaults-toml.md~~ → [30-configuration.md §Appendix A](30-configuration.md#appendix-a--esempio-defaultstoml)
- ~~33-base-toml.md~~ → [30-configuration.md §Appendix B](30-configuration.md#appendix-b--esempio-basetoml)

---

*Ultimo aggiornamento: 22 luglio 2026*
