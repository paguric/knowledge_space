# Roadmap — Overview

## Fasi di implementazione

Il lavoro è diviso in **4 fasi**:

1. **Fase 1 — Logica di business completa**: tutta la logica di backend funzionante e testata (modelli, managers, configurazione, pipeline di ingestion/chunking/embedding/indicizzazione e retrieval). Al termine di questa fase `knowledge-base` è una libreria completa e testabile in isolamento. Dettagli: [06-roadmap-fase1.md](06-roadmap-fase1.md).
2. **Fase 2 — Testing e validazione**: dataset sintetici e profili di configurazione predefiniti (ricercatore/legale/studente) per validare end-to-end la pipeline completa e confrontare le configurazioni. Dettagli: [07-roadmap-fase2.md](07-roadmap-fase2.md).
3. **Fase 3 — MCP + CLI**: server MCP per interrogare i workspace e interfaccia a riga di comando. Entrambi si appoggiano ai manager già consolidati nella Fase 1. Dettagli: [08-roadmap-fase3.md](08-roadmap-fase3.md).
4. **Fase 4 — REST + Frontend**: layer FastAPI sopra i manager e frontend React collegato alle API. Dettagli: [09-roadmap-fase4.md](09-roadmap-fase4.md).

## Mappa degli step per fase

| Fase | Step | File |
|---|---|---|
| 1 | 0 — Modello di dominio e persistenza | 06-roadmap-fase1.md |
| 1 | 1 — Workspace e sync FS | 06-roadmap-fase1.md |
| 1 | 2 — Domini | 06-roadmap-fase1.md |
| 1 | 3 — Configurazione delle basi (TOML) | 06-roadmap-fase1.md |
| 1 | 4 — Strategie di ingestion | 06-roadmap-fase1.md |
| 1 | 5 — Strategie di chunking | 06-roadmap-fase1.md |
| 1 | 6 — Embedding configurabile per base | 06-roadmap-fase1.md |
| 1 | 7 — KnowledgeBaseManager e indicizzazione | 06-roadmap-fase1.md |
| 1 | 8 — Pipeline di retrieval (pre/retrieval/post) | 06-roadmap-fase1.md |
| 1 | 8-bis — Pipeline GraphRAG + edit-aware re-embedding | 06-roadmap-fase1.md |
| 1 | 8-ter — `AppContext` e bootstrap | 06-roadmap-fase1.md |
| 2 | 9 — Dataset sintetici | 07-roadmap-fase2.md |
| 2 | 10 — Profili di configurazione | 07-roadmap-fase2.md |
| 2 | 11 — Test end-to-end e benchmark | 07-roadmap-fase2.md |
| 3 | 12 — CLI con Typer | 08-roadmap-fase3.md |
| 3 | 13 — Server MCP | 08-roadmap-fase3.md |
| 4 | 14 — Backend REST | 09-roadmap-fase4.md |
| 4 | 15 — Frontend React / GUI | 09-roadmap-fase4.md |
| 4 | 16 — Polish e documentazione | 09-roadmap-fase4.md |

---

## Considerazioni e rischi

### Concurrency

- L'indice globale (`GlobalIndex`) e i `config.json` non sono concurrent-safe. Se il server REST gira con più worker, l'accesso deve essere sincronizzato.
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
| Persistenza | Ibrida: indice globale + file `config.json` per workspace |
| Configurazione basi | TOML per base + `defaults.toml` (cascata) |
| Modelli di dominio | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Logica operativa | Classi manager/service separate dai modelli di dominio |
| Strategy pattern | Registry per ingestion, chunking, embedding, pre/post-retrieval |
| Profili di config | `researcher` / `legal` / `student` in `configs/profiles/` |
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