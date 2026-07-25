> ⚠️ **Deprecato.** Questo file è stato sostituito da [roadmap.md](roadmap.md). Conservato per riferimento storico. Non aggiornare.

# Fase 4 — REST + Frontend (deprecato)

> Per la collocazione di questa fase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md).

---

### Step 15: Backend REST

Thin layer FastAPI sopra i manager già testati.

- [ ] Aggiungere `fastapi` e `uvicorn` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/api/app.py` con `create_app`.
- [ ] Implementare router `health`, `workspaces`, `domains`, `bases`, `files`, `search`, `config`.
- [ ] Aggiungere CORS.
- [ ] Scrivere test per l'API.
- [ ] **Endpoint `/api/v1/models/embeddings`**: elenca i modelli di embedding registrati con i loro metadati (`model_name`, `languages`, `dim`, `max_context_tokens`, `license`, `requires_api`). Il frontend lo usa per mostrare all'utente le opzioni.

### Step 16: Frontend React / GUI

- [ ] Collegare il frontend alle API REST.
- [ ] Permettere modifica dei file TOML dall'interfaccia (quando prevista da 30-configuration.md).
- [ ] Visualizzare struttura ad albero (workspace → domini → basi → file → chunk).
- [ ] **Selettore modello di embedding**: quando l'utente configura una base, mostrare l'elenco dei modelli disponibili (da `/api/v1/models/embeddings`) e **evidenziare esplicitamente quali lingue supporta ciascun modello** (es. badge "🇮🇹 IT", "🇬🇧 EN", "🌍 multilingua"). Questo aiuta l'utente a scegliere un modello compatibile col proprio corpus e a evitare errori (es. modelli solo-EN su documenti italiani).
- [ ] **Avviso contesto**: mostrare `max_context_tokens` del modello e confrontarlo con `chunk_size` della strategia di chunking scelta, avvisando l'utente se configura un `chunk_size` che rischia di eccedere il limite (vedi nota Step 6 — lancio errore al runtime).

### Step 17: Polish e documentazione

- [ ] Rimuovere codice legacy e variabili globali residue (`base.py`, `workspace.py`, `domain.py` vecchi).
- [ ] Rimuovere entrypoint CLI da `knowledge-base`.
- [ ] Aggiornare i `README.md` di tutti i pacchetti.
- [ ] Aggiornare `AGENTS.md` con le convenzioni del progetto.
- [ ] Aggiungere test end-to-end.
- [ ] Valutare la versione minima di Python: `>=3.14` è molto restrittiva. Considerare `>=3.11` o `>=3.12`.

### Step 18: Imballaggio e distribuzione (Docker + Windows .exe) — *provvisorio*

> **Scelte da definire.** Questo step è solo un segnaposto: le tecnologie concrete, la struttura delle immagini e i flussi di build sono ancora da valutare. Dettagli operativi in [12-deployment.md](12-deployment.md). Vedi anche [11-app-lifecycle.md §Packaging](11-app-lifecycle.md#packaging) per il bundle GUI (pywebview/Tauri/Electron), che è ortogonale a questo step.

- [ ] **Immagine Docker** del backend REST (`ks serve`):
  - Base image: da definire (es. `python:3.12-slim` vs `python:3.12-alpine` vs base con CUDA per embedding GPU).
  - Gestione dei modelli locali sentence-transformers: pre-bundled nell'immagine vs mount esterno vs download all'avvio.
  - Gestione dei secrets (API keys): env vars vs Docker secrets vs mount di `~/.config/KnowledgeSpace/config.json`.
  - Persistenza: volumi per `XDG_STATE_HOME` (Chroma, `state.json`, log) e workspace utente.
  - Esposizione: porta REST + (opzionale) MCP SSE.
- [ ] **Eseguibile Windows `.exe`** (utente desktop, bundle GUI):
  - Tool da definire: PyInstaller vs Nuitka vs pyoxidizer vs Briefcase.
  - Bundle di Python + dipendenze + frontend React compilato + (opzionale) runtime Neo4j/Chroma embedded.
  - Gestione dei modelli locali pesanti: scaricamento al primo avvio vs incluso nel `.exe` (dimensione).
  - Firma del binario (code signing) — opzionale per tesi.
  - Destinazione: `dist/KnowledgeSpace.exe` + cartella `data/` o installer (NSIS/Inno Setup) — da definire.
- [ ] **CI/CD** (opzionale): workflow GitHub Actions che builda entrambi gli artifact su tag.
- [ ] Documentare i flussi di build e i prerequisiti nel `README.md` principale.

---

*Ultimo aggiornamento: 21 luglio 2026*