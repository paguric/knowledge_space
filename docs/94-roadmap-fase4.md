# Fase 4 — REST + Frontend

> Per la collocazione di questa fase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md).

---

### Step 14: Backend REST

Thin layer FastAPI sopra i manager già testati.

- [ ] Aggiungere `fastapi` e `uvicorn` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/api/app.py` con `create_app`.
- [ ] Implementare router `health`, `workspaces`, `domains`, `bases`, `files`, `search`, `config`.
- [ ] Aggiungere CORS.
- [ ] Scrivere test per l'API.
- [ ] **Endpoint `/api/v1/models/embeddings`**: elenca i modelli di embedding registrati con i loro metadati (`model_name`, `languages`, `dim`, `max_context_tokens`, `license`, `requires_api`). Il frontend lo usa per mostrare all'utente le opzioni.

### Step 15: Frontend React / GUI

- [ ] Collegare il frontend alle API REST.
- [ ] Permettere modifica dei file TOML dall'interfaccia (quando prevista da 30-configuration.md).
- [ ] Visualizzare struttura ad albero (workspace → domini → basi → file → chunk).
- [ ] **Selettore modello di embedding**: quando l'utente configura una base, mostrare l'elenco dei modelli disponibili (da `/api/v1/models/embeddings`) e **evidenziare esplicitamente quali lingue supporta ciascun modello** (es. badge "🇮🇹 IT", "🇬🇧 EN", "🌍 multilingua"). Questo aiuta l'utente a scegliere un modello compatibile col proprio corpus e a evitare errori (es. modelli solo-EN su documenti italiani).
- [ ] **Avviso contesto**: mostrare `max_context_tokens` del modello e confrontarlo con `chunk_size` della strategia di chunking scelta, avvisando l'utente se configura un `chunk_size` che rischia di eccedere il limite (vedi nota Step 6 — lancio errore al runtime).

### Step 16: Polish e documentazione

- [ ] Rimuovere codice legacy e variabili globali residue (`base.py`, `workspace.py`, `domain.py` vecchi).
- [ ] Rimuovere entrypoint CLI da `knowledge-base`.
- [ ] Aggiornare i `README.md` di tutti i pacchetti.
- [ ] Aggiornare `AGENTS.md` con le convenzioni del progetto.
- [ ] Aggiungere test end-to-end.
- [ ] Valutare la versione minima di Python: `>=3.14` è molto restrittiva. Considerare `>=3.11` o `>=3.12`.

---

*Ultimo aggiornamento: 21 luglio 2026*