# Roadmap — Overview

## Fasi di implementazione

Il lavoro è diviso in **4 fasi**:

1. **Fase 1A — Ingestione e indicizzazione vettoriale**: documento → ingestion → chunking → embedding → Chroma. Sync FS, configurazione, strategy registry, blocco cambio config, reindex incrementale vettoriale, `file_id`, `AppContext`. Dettagli: [91a-roadmap-fase1-ingestione.md](91a-roadmap-fase1-ingestione.md).
2. **Fase 1B — Ricerca sui documenti processati**: pipeline di retrieval (pre/retrieval/post) su vettori Chroma. Dettagli: [91b-roadmap-fase1-ricerca.md](91b-roadmap-fase1-ricerca.md).
3. **Fase 1C — Indicizzazione e retrieval su grafo (GraphRAG)**: costruzione grafo Neo4j, propagazione incrementale, retrieval su grafo. Dettagli: [91c-roadmap-fase1-graphrag.md](91c-roadmap-fase1-graphrag.md).

Al termine della Fase 1 `knowledge-base` è una libreria completa e testabile in isolamento.
2. **Fase 2 — Testing e validazione**: dataset sintetici e profili di configurazione predefiniti (ricercatore/consulente/studente) per validare end-to-end la pipeline completa e confrontare le configurazioni. Dettagli: [92-roadmap-fase2.md](92-roadmap-fase2.md).
3. **Fase 3 — MCP + CLI**: server MCP per interrogare i workspace e interfaccia a riga di comando. Entrambi si appoggiano ai manager già consolidati nella Fase 1. Dettagli: [93-roadmap-fase3.md](93-roadmap-fase3.md).
4. **Fase 4 — REST + Frontend**: layer FastAPI sopra i manager e frontend React collegato alle API. Dettagli: [94-roadmap-fase4.md](94-roadmap-fase4.md).

## Mappa degli step per fase

| Fase | Step | File |
|---|---|---|
| 1A | 0 — Modello di dominio e persistenza | [91a-roadmap-fase1-ingestione.md](91a-roadmap-fase1-ingestione.md) |
| 1A | 1 — Workspace e sync FS | 91a |
| 1A | 2 — Domini | 91a |
| 1A | 3 — Configurazione delle basi (TOML) | 91a |
| 1A | 4 — Strategie di ingestion | 91a |
| 1A | 5 — Strategie di chunking | 91a |
| 1A | 6 — Embedding configurabile per base | 91a |
| 1A | 7 — KnowledgeBaseManager e indicizzazione | 91a |
| 1A | 8-ter — `AppContext` e bootstrap | 91a |
| 1B | 8 — Pipeline di retrieval (pre/retrieval/post) | [91b-roadmap-fase1-ricerca.md](91b-roadmap-fase1-ricerca.md) |
| 1C | 8-bis — Pipeline GraphRAG + propagazione incrementale | [91c-roadmap-fase1-graphrag.md](91c-roadmap-fase1-graphrag.md) |
| 2 | 9 — Dataset sintetici | [92-roadmap-fase2.md](92-roadmap-fase2.md) |
| 2 | 10 — Profili di configurazione | 92 |
| 2 | 11 — Test end-to-end e benchmark | 92 |
| 3 | 12 — CLI con Typer | [93-roadmap-fase3.md](93-roadmap-fase3.md) |
| 3 | 13 — Server MCP | 93 |
| 4 | 14 — Backend REST | [94-roadmap-fase4.md](94-roadmap-fase4.md) |
| 4 | 15 — Frontend React / GUI | 94 |
| 4 | 16 — Polish e documentazione | 94 |

---

## Considerazioni e rischi

### Concurrency

- L'indice globale (`GlobalIndex`) e i `state.json` non sono concurrent-safe. Se il server REST gira con più worker, l'accesso deve essere sincronizzato.
- **Chroma** PersistentClient è generalmente sicuro per un singolo processo; più processi contemporanei possono creare conflitti.
- **watchdog** usa thread. Per i test, permettere di iniettare un observer fittizio.

### Sicurezza

- Non esporre `hf_key` o altri secrets via API.
- Validare i path passati dagli utenti per evitare path traversal.
- Se il backend è esposto in rete, aggiungere autenticazione.

### Compatibilità Python

- `requires-python = ">=3.14"` è molto avanzato. Valutare `>=3.11` o `>=3.12`.

### Esecuzione simultanea REST e MCP

- La CLI può esporre due comandi separati: `serve` e `mcp`.
- In futuro, MCP in modalità SSE sullo stesso server FastAPI.

### Strategie LLM-dipendenti

- Query rewriting (HyDE, multi-query) e compression richiedono un LLM. Per la Fase 1 usare mock/stub nei test; l'integrazione reale con un LLM (locale o API) sarà decisione di configurazione.
- `EmbeddingStrategy` per base può richiedere modelli diversi caricati in memoria contemporaneamente: valutare uso di RAM e lazy loading.

## Riepilogo delle scelte consigliate

| Aspetto | Scelta consigliata |
|---------|-------------------|
| Monorepo | Mantenere workspace uv con 3 pacchetti |
| Persistenza | Ibrida: indice globale + file `state.json` per workspace |
| Configurazione basi | TOML per base + `defaults.toml` (cascata) |
| Modelli di dominio | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Logica operativa | Classi manager/service separate dai modelli di dominio |
| Strategy pattern | Registry per ingestion, chunking, embedding, pre/post-retrieval |
| Profili di config | `ricercatore` / `consulente` / `studente` in `configs/profiles/` |
| Testing e2e | Dataset sintetici + query golden in `tests/data/synthetic/` |
| Backend REST | FastAPI + Pydantic + uvicorn |
| Server MCP | SDK ufficiale `mcp`, trasporto stdio (poi SSE) |
| CLI | Typer |
| Configurazione app | `RuntimePaths` + `UserSettings` + `AppConfig`, passaggio esplicito |
| Persistenza | Repository pattern a medio termine |
| Iniezione dipendenze | `AppContext` a livello di applicazione |
| Versione Python | Valutare `>=3.11` o `>=3.12` al posto di `>=3.14` |

---

*Ultimo aggiornamento: 21 luglio 2026*