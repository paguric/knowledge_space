# Piano di Refactor: Knowledge Space

Questo documento è l'indice del piano di refactor. Ogni argomento è trattato in un file dedicato.

## Documenti di progetto

- [**10 — Architettura e organizzazione dei pacchetti**](10-architecture.md)
- [**20 — Modello di dominio e persistenza**](20-data-model.md)
- [**30 — Gestione della configurazione**](30-configuration.md) — include il layout completo del filesystem del workspace e delle basi.
- [**40 — Pipeline GraphRAG + edit-aware re-embedding**](40-graph.md)
- [**50 — Strategie di ingestion**](50-ingestion.md) — librerie supportate, parametri e profili d'uso.
- [**60 — Strategie di chunking**](60-chunking.md) — chunker base e avanzati.
- [**70 — Embedding configurabile per base**](70-embedding.md) — modelli, registry, metadati e validazione contesto.
- [**80 — Pipeline di retrieval**](80-retrieval.md) — pre-retrieval (query rewriting), retrieval (dense/sparse/hybrid), post-retrieval (rerank/compress).

## Roadmap

- [**90 — Roadmap overview**](90-roadmap-overview.md) — fasi, mappa degli step, considerazioni e rischi, riepilogo scelte.
- [**91 — Fase 1 — Logica di business completa**](91-roadmap-fase1.md) — Steps 0–8-ter.
- [**92 — Fase 2 — Testing e validazione**](92-roadmap-fase2.md) — Steps 9–11 (dataset sintetici, profili, benchmark).
- [**93 — Fase 3 — MCP + CLI**](93-roadmap-fase3.md) — Steps 12–13.
- [**94 — Fase 4 — REST + Frontend**](94-roadmap-fase4.md) — Steps 14–16.

## Interfacce utente

- [**95 — CLI standalone**](95-cli.md)
- [**96 — Server MCP**](96-mcp-server.md)
- [**97 — Backend REST**](97-rest-api.md)

---

*Ultimo aggiornamento: 21 luglio 2026*