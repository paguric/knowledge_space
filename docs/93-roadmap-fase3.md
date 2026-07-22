# Fase 3 — MCP + CLI

Esporre i manager consolidati nella Fase 1 tramite MCP e CLI.

> Per la collocazione di questa fase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md).

---

### Step 13: CLI con Typer

- [ ] Aggiungere `typer` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/cli.py`.
- [ ] Implementare comandi per workspace, domini, basi, file, chunk, tree, search, reindex, graph, config, auth, models, status — secondo la specifica in [95-cli.md](95-cli.md).
- [ ] La CLI opera in **modalità standalone**: ogni comando è un processo separato, crea `AppContext` temporaneo, opera su `state.json`/Chroma, termina. Niente watcher in background, niente backend process. Vedi [11-app-lifecycle.md](11-app-lifecycle.md).
- [ ] La CLI chiama `setup_logging()` (Step 12) subito dopo il parse dei flag globali (`--verbose`, `KS_LOG_LEVEL`), prima di qualsiasi operazione.
- [ ] **Scrittura TOML** (`config set`/`unset`): la CLI scrive nei file TOML (`defaults.toml`, `base.toml`) — questo completa la transizione dalla Fase 1 (sola lettura) alla Fase 2 (modifica via CLI). Le restrizioni sui campi bloccanti (embedding.model, chunking.method, ingestion.library) sono applicate dal comando stesso con `--reason`.
- [ ] I comandi `serve` e `stop` (backend process, Fase 4) sono **solo elencati** in `95-cli.md` come riferimento; la loro implementazione è differita a Fase 4 (Step 15 — REST, vedi [94-roadmap-fase4.md](94-roadmap-fase4.md) e [11-app-lifecycle.md](11-app-lifecycle.md)).
- [ ] Scrivere test di integrazione per i comandi CLI (standalone mode).

### Step 14: Server MCP

- [ ] Aggiungere `mcp` alle dipendenze di `mcp-server`.
- [ ] Rimuovere la dipendenza `mcp-server` da `knowledge-space`; aggiungere `knowledge-base` come dipendenza di `mcp-server`.
- [ ] Implementare `mcp_server/server.py` con trasporto stdio (default) e SSE (opzionale, `--sse --port 8001`).
- [ ] In Fase 3, MCP stdio opera come **processo standalone** (non bridge verso backend — il backend non esiste ancora). Carica `AppContext` direttamente e opera su `state.json`/Chroma. In Fase 4+, MCP stdio diventerà bridge verso il backend (vedi [11-app-lifecycle.md §8](11-app-lifecycle.md#8-mcp-stdio--rest-bridge)).
- [ ] Implementare i tool MCP (`list_workspaces`, `add_workspace`, `search`, `list_domains`, `activate_domain`, etc.).
- [ ] Scrivere test per MCP.

---

*Ultimo aggiornamento: 21 luglio 2026*