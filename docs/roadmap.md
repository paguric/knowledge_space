# Roadmap, scelte e rischi

## Roadmap di implementazione

### Step 0: Modello di dominio e persistenza ibrida

Fondamenta su cui poggiano tutti gli altri step.

- [x] Definire modelli Pydantic in `knowledge_base/models.py`:
  - `ChunkRef`, `FileEntry`, `KnowledgeBase`, `Domain`, `Workspace`, `GlobalIndexData`, `WorkspaceConfigData`.
- [x] Creare `GlobalIndex` per caricare/salvare `~/.local/state/KnowledgeSpace/workspaces.json`, includendo `last_workspace`.
- [x] Creare `WorkspaceConfig` per caricare/salvare `<workspace>/.knowledge-space/config.json`.
- [x] Iniziare la rimozione delle variabili globali da `knowledge-base` (nuovi moduli non le usano; legacy non ancora toccato).
- [x] Scrivere test di roundtrip JSON per `WorkspaceConfig` e `GlobalIndex` (16 test in `packages/knowledge-base/tests/`).

### Step 1: Workspace e sincronizzazione col filesystem

Implementare la logica operativa sui workspace.

- [ ] Creare `WorkspaceManager`:
  - `add(path)` / `remove(path)` / `list()`
  - `load(path)` → restituisce `Workspace`
  - `sync(workspace)` → allinea basi e file col filesystem
  - `set_last_workspace(path)`
- [ ] Integrare `watchdog` per sincronizzazione a runtime.
- [ ] Scrivere test per CRUD workspace e sincronizzazione FS.

### Step 2: Domini

Implementare la gestione dei domini.

- [ ] Creare `DomainManager`:
  - `create(workspace, name, base_names)`
  - `auto_generate(workspace)` dalla struttura di cartelle
  - `activate(workspace, name)` / `deactivate(workspace, name)`
  - `add_base(workspace, domain, base)` / `remove_base(workspace, domain, base)`
- [ ] Scrivere test per creazione, auto-generazione e flag `active`.

### Step 3: KnowledgeBase e indicizzazione

Implementare la logica operativa sulle basi di conoscenza.

- [ ] Creare `KnowledgeBaseManager`:
  - `add(workspace, path)` / `remove(workspace, name)`
  - `add_file(kb, path)` → ingestion, chunking, vector store
  - `remove_file(kb, path)` → rimozione da indice e vector store
  - `search(query, workspace?, domain?, kb?)` → rispetta i flag `active`
- [ ] Riutilizzare docling, langchain, chroma incapsulati nel manager.
- [ ] Scrivere test per ingestion, rimozione e ricerca.

### Step 4: CLI completa con Typer

Costruire l'interfaccia a riga di comando che chiama i manager.

- [ ] Aggiungere `typer` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/cli.py`.
- [ ] Implementare comandi per workspace, domini, basi e ricerca.
- [ ] Scrivere test di integrazione per i comandi CLI.

### Step 5: Server MCP

Esporre i manager tramite MCP, dopo che la CLI li ha consolidati.

- [ ] Aggiungere `mcp` alle dipendenze di `mcp-server`.
- [ ] Implementare `mcp_server/server.py` con stdio.
- [ ] Implementare i tool MCP (`list_workspaces`, `add_workspace`, `search`, etc.).
- [ ] Scrivere test per MCP.

### Step 6: Backend REST

Thin layer FastAPI sopra i manager già testati.

- [ ] Aggiungere `fastapi` e `uvicorn` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/api/app.py` con `create_app`.
- [ ] Implementare router `health`, `workspaces`, `bases`, `files`, `search`, `config`.
- [ ] Aggiungere CORS.
- [ ] Scrivere test per l'API.

### Step 7: Frontend React / GUI

- [ ] Collegare il frontend alle API REST.

### Step 8: Polish e documentazione

- [ ] Rimuovere codice legacy e variabili globali residue.
- [ ] Rimuovere entrypoint CLI da `knowledge-base`.
- [ ] Rimuovere dipendenza `mcp-server` da `knowledge-space`.
- [ ] Aggiornare i `README.md` di tutti i pacchetti.
- [ ] Aggiornare `AGENTS.md` con le convenzioni del progetto.
- [ ] Aggiungere test end-to-end.
- [ ] Valutare la versione minima di Python: `>=3.14` è molto restrittiva. Considerare `>=3.11` o `>=3.12`.

---

## Considerazioni e rischi

### Concurrency

- **TinyDB** non è concurrent-safe. Se il server REST gira con più worker, l'accesso all'indice deve essere sincronizzato.
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

## Riepilogo delle scelte consigliate

| Aspetto | Scelta consigliata |
|---------|-------------------|
| Monorepo | Mantenere workspace uv con 3 pacchetti |
| Persistenza | Ibrida: indice globale + file `.knowledge-space/config.json` per workspace |
| Modelli di dominio | Pydantic (`Workspace`, `Domain`, `KnowledgeBase`, `FileEntry`, `ChunkRef`) |
| Logica operativa | Classi manager/service separate dai modelli di dominio |
| Backend REST | FastAPI + Pydantic + uvicorn |
| Server MCP | SDK ufficiale `mcp`, trasporto stdio (poi SSE) |
| CLI | Typer |
| Configurazione | `RuntimePaths` + `UserSettings` + `AppConfig`, passaggio esplicito |
| Persistenza | Repository pattern a medio termine |
| Iniezione dipendenze | `AppContext` a livello di applicazione |
| Versione Python | Valutare `>=3.11` o `>=3.12` al posto di `>=3.14` |

---

*Ultimo aggiornamento: 16 luglio 2026*
