# Piano di Refactor: Knowledge Space

Questo documento è l'indice del piano di refactor. Ogni argomento è trattato in un file dedicato.

## Documenti di progetto

- [**10 — Architettura e organizzazione dei pacchetti**](10-architecture.md)
- [**11 — Ciclo di vita dell'app e processo backend**](11-app-lifecycle.md) — entry point, CLI standalone vs backend process, lifecycle, PID file, signal handling, MCP bridge, packaging.
- [**12 — Deployment e imballaggio**](12-deployment.md) — immagine Docker del backend REST, eseguibile Windows `.exe` con bundle GUI. *Provvisorio.*
- [**20 — Modello di dominio e persistenza**](20-data-model.md)
- [**30 — Gestione della configurazione**](30-configuration.md) — include il layout completo del filesystem del workspace e delle basi.
  - [**31 — Configurazione dell'applicazione (RuntimePaths, AppConfig, env)**](31-configurazione-app.md)
  - [**32 — Esempio di `defaults.toml`**](32-defaults-toml.md)
  - [**33 — Esempio di `<base>/.knowledge-space/base.toml`**](33-base-toml.md)
- [**40 — Pipeline GraphRAG**](40-graph.md)
- [**45 — Indicizzazione incrementale e ciclo di vita dell'indice**](45-indexing-incrementale.md) — 5 trigger di reindex (content change, move/rename, cambio modello/strategia/libreria), `file_id` stabile.
- [**50 — Strategie di ingestion**](50-ingestion.md) — librerie supportate, parametri e profili d'uso.
- [**60 — Strategie di chunking**](60-chunking.md) — chunker base e avanzati.
- [**70 — Embedding configurabile per base**](70-embedding.md) — modelli, registry, metadati e validazione contesto.
- [**75 — Astrazione LLM**](75-llm.md) — LLMStrategy Protocol, registry, per-component TOML, chiavi API, fallback.
- [**80 — Pipeline di retrieval**](80-retrieval.md) — pre-retrieval (query rewriting), retrieval (dense/sparse/hybrid), post-retrieval (rerank/compress).

## Roadmap

- [**90 — Roadmap overview**](90-roadmap-overview.md) — fasi, mappa degli step, considerazioni e rischi, riepilogo scelte.
- [**91a — Fase 1A — Ingestione e indicizzazione vettoriale**](91a-roadmap-fase1-ingestione.md) — Steps 0–7, 8-ter.
- [**91b — Fase 1B — Ricerca sui documenti processati**](91b-roadmap-fase1-ricerca.md) — Step 8 (retrieval pipeline).
- [**91c — Fase 1C — Indicizzazione e retrieval su grafo (GraphRAG)**](91c-roadmap-fase1-graphrag.md) — Step 8-bis.
- [**92 — Fase 2 — Testing e validazione**](92-roadmap-fase2.md) — Steps 9–11 (dataset sintetici, profili, benchmark).
- [**93 — Fase 3 — MCP + CLI**](93-roadmap-fase3.md) — Steps 13–14.
- [**94 — Fase 4 — REST + Frontend**](94-roadmap-fase4.md) — Steps 15–18.

## Interfacce utente

- [**95 — CLI standalone**](95-cli.md)
- [**96 — Server MCP**](96-mcp-server.md)
- [**97 — Backend REST**](97-rest-api.md)

---

*Ultimo aggiornamento: 21 luglio 2026*