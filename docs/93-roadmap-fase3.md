# Fase 3 — MCP + CLI

Esporre i manager consolidati nella Fase 1 tramite MCP e CLI.

> Per la collocazione di questa fase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md).

---

### Step 12: CLI con Typer

- [ ] Aggiungere `typer` alle dipendenze di `knowledge-space`.
- [ ] Creare `knowledge_space/cli.py`.
- [ ] Implementare comandi per workspace, domini, basi, file, ricerca.
- [ ] La CLI **legge** ma non scrive i file TOML (vedi [30-configuration.md](30-configuration.md)).
- [ ] Scrivere test di integrazione per i comandi CLI.

### Step 13: Server MCP

- [ ] Aggiungere `mcp` alle dipendenze di `mcp-server`.
- [ ] Rimuovere la dipendenza `mcp-server` da `knowledge-space`; aggiungere `knowledge-base` come dipendenza di `mcp-server`.
- [ ] Implementare `mcp_server/server.py` con trasporto stdio.
- [ ] Implementare i tool MCP (`list_workspaces`, `add_workspace`, `search`, `list_domains`, `activate_domain`, etc.).
- [ ] Scrivere test per MCP.

---

*Ultimo aggiornamento: 21 luglio 2026*