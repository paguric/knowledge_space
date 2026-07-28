# AGENTS.md — Knowledge Space

> Standard project context for coding agents (humans and AI).  
> Keep this file in the repo root and keep it up to date when the master agent changes conventions.

## Project identity

- **Name:** Knowledge Space (`knowledge-space` / `ks`)
- **Goal:** Document ingestion, indexing, and retrieval pipeline with pluggable strategies for ingestion, chunking, embedding, retrieval, and LLM.
- **Repo type:** UV monorepo with 3 packages:
  - `packages/knowledge-base/` — pure library (models, persistence, managers, strategies).
  - `packages/mcp-server/` — MCP server adapter (future).
  - `src/knowledge_space/` — app layer (CLI, bootstrap, runtime paths, logging).
- **Primary sources:** `README.md`, `docs/00a-repo-context.md`, `docs/roadmap.md`.

## Quick orientation

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run package tests
uv run pytest packages/knowledge-base/tests/ -v

# Run app tests
uv run pytest tests/ -v

# CLI entry point
ks --help
```

## Architecture at a glance

- **No global state.** All dependencies are injected through `AppContext` (`src/knowledge_space/context.py`), built by `build_app_context()` (`src/knowledge_space/bootstrap.py`).
- **Strategy registries** in `packages/knowledge-base/src/knowledge_base/strategies/`: ingestion, chunking, embedding, retrieval, pre/post-retrieval, LLM.
- **Configuration cascade:** hardcoded defaults → `<workspace>/.knowledge-space/defaults.toml` → `<base>/.knowledge-space/base.toml` (`docs/30-configuration.md`).
- **Data model:** Pydantic models in `packages/knowledge-base/src/knowledge_base/models.py`; state lives in `state.json` per workspace and `~/.local/state/KnowledgeSpace/workspaces.json` globally.
- **Tests:** `packages/knowledge-base/tests/` for the library; `tests/` for the app layer. See `pyproject.toml` for markers (`api`, `neo4j`).

## Conventions

- **Language:** Italian everywhere — user-facing messages, docs, comments, docstrings, and commit messages. Use English only when required by external APIs or standard technical terms.
- **Style:** follow `ruff` / `uv` defaults; type hints where reasonable; docstrings in reStructuredText/Sphinx style.
- **No globals:** every class receives its dependencies explicitly; factories are injected.
- **Secrets:** never commit API keys or `hf_key`. Use environment variables or `UserSettings` (`~/.config/KnowledgeSpace/config.json`).

## Git workflow

- Lavora sul branch `dev`. Non commettere mai direttamente su `main`.
- Commit-message prefix: `fix:`, `feat:`, `docs:`, `test:`, `chore:` (repo style from `git log`).
- Include tests for every code change.
- Do not push without explicit authorization.
- Do not modify or commit files written by the master agent:
  - `docs/00a-repo-context.md`
  - `docs/specs/*.md`
  - `AGENTS.md`
  - `docs/roadmap.md` (master updates it)

## Testing expectations

- Add/modify unit tests for library changes in `packages/knowledge-base/tests/`.
- Add/modify app tests in `tests/` for CLI/bootstrap changes.
- Run the targeted test file before reporting completion.
- Run the full suite (`uv run pytest`) if the change can affect other parts.
- Skip remote-API tests unless the dependency is installed (`pytest.importorskip` or `skipif`).

## Master-agent workflow

- The master agent runs inside Herdr.
- Bugs are delegated to the **bugs** tab; features are delegated to the **features** tab.
- Sub-agents run as `pi` with model `opencode-go/mimo-v2.5-pro` and thinking level `high`:
  ```bash
  herdr agent start <name> --kind pi --pane <pane-id> -- --model opencode-go/mimo-v2.5-pro --thinking high
  ```
- Each sub-agent receives a `docs/specs/*.md` plan and must read `docs/00a-repo-context.md` before starting.
- Sub-agents report back branch name, files changed, test results, and open questions.

## Communication

- When joining a fresh session, read this file first, then read `docs/00a-repo-context.md`.
- If you are a bug/feature sub-agent, read the assigned spec from `docs/specs/` next.
- Ask the master for clarification rather than guessing.
- Summarize findings before writing code: "Here is what I found, here is what I plan to change."

---

## Session summary (2026-07-28 — da aggiornare al join)

### Stato attuale del repo

**Branch:** `dev` · **Ultimo commit:** `8b3cf9a` (chore: aggiorna roadmap — Step 14, bug 005/006/007 ✅)

**Commit principali su dev** (dal più recente):
| Commit | Descrizione |
|--------|-------------|
| `8b3cf9a` | chore: aggiorna roadmap — Step 14, bug 005/006/007 ✅ |
| `a1d917d` | fix: sync() ricorsivo + sync_and_ingest() con ingest automatica basi nuove |
| `e407e42` | fix: server MCP compatibile con MCP 2.0 |
| `e83b41c` | fix README: usa --sse nel service file |
| `e60a5c2` | fix README: rimuovi 'da implementare' da ks serve |
| `92d02a3` | fix: watcher con debounce 500ms |

**Suite test:** 609 passed, 13 failed (preesistenti, embedding/retrieval), 4 skipped.

### systemd service ks-serve

Percorso: `~/.config/systemd/user/ks-serve.service`

```ini
[Service]
ExecStart=/usr/bin/bash -c 'cd "$HOME/università/as25-26-sp/progtes/knowledge_space" && uv run ks serve --sse'
Restart=always
RestartSec=5
```

**Nota:** NON mettere `Environment=XDG_STATE_HOME=...` nel service — il servizio deve usare il default `~/.local/state/KnowledgeSpace/`.

**Dopo ogni modifica al codice (obbligatorio in questo ordine):**
1. `cd ~/università/as25-26-sp/progtes/knowledge_space && uv sync` — ricompila i `.pth` e sincronizza i package
2. `systemctl --user daemon-reload` — ricarica la configurazione systemd
3. `systemctl --user restart ks-serve` — riavvia con il codice nuovo

> **Senza `uv sync` il servizio continua a usare il bytecode/linking vecchio** (i package sono `.pth`-linked alla source tree, ma è buona norma ricompilare prima di riavviare).

### Bug in corso

Entrambi già risolti da bug-lead (commit `ee4c905`).

- **Bug 008** (`docs/specs/bug-008-ingest-file-in-existing-base.md`): `sync_and_ingest()` indicizza solo basi NUOVE. File creati DOPO la base non vengono indicizzati. → `_ingest_files_in_base()`, `_ingest_new_files_in_existing_base()` (mtime check).
- **Bug 009** (`docs/specs/bug-009-dot-knowledge-space-non-escluso.md`): `_discover_bases_recursive()` non esclude `.knowledge-space`. Le sottocartelle `chroma/`, `chunks/` vengono registrate come basi. → Filtra `if ".knowledge-space" in entry.parts`.

### Bug risolti di recente

| Bug | Root cause | Fix |
|-----|-----------|-----|
| Bug 005 | `on_any_event` non è un metodo watchdog | → `on_created`/`on_deleted`/`on_moved` + debounce |
| Bug 006 | MCP 2.0 API (`add_request_handler`) vs 1.x (`@server.on_list_tools`) | → `add_request_handler("tools/list", ...)` |
| Bug 008 | `sync_and_ingest()` non indicizzava file in basi esistenti | → mtime check per file nuovi/modificati |
| Bug 009 | `.knowledge-space` non escluso da `rglob` | → filtro `entry.parts` |
| Bug 007 | `sync()` non ricorsivo + no ingest | → `_discover_bases_recursive()` + `sync_and_ingest()` |
| Bug 004 | Rimosso — systemd+serve lo copre | — |
| Bug 003 | Refactor `info`+`tree` → `status` | 🟡 ancora da delegare |

### Bug ancora da fare

- **Bug 003**: collapse `info`+`tree` → `status` (KISS). Spec: `docs/specs/bug-003-tree-status-workspace.md`. Delegare a bug-lead.

### Step aperti

- **Step 14 — Server MCP + Watcher**: sostanzialmente completo. `ks serve --sse` gira come servizio systemd con watcher attivi.
- **Step 12-bis — Logging**: completo (`feat-002`). Commit `45d4361`.
- **Step 15 — Backend REST**: non iniziato.
- **Step 16 — Frontend React**: non iniziato.
- **Step 17 — Polish e documentazione**: non iniziato.

### Prossimi passi suggeriti

1. Verificare che `ks serve` su SSE accetti connessioni da un client MCP.
2. Delegare bug-003 a bug-lead (refactor `info`+`tree` → `status`).
3. Test end-to-end: `mkdir → base registrata → file indicizzato → search funziona`.
4. Testare che anche i workspace aggiunti DOPO l'avvio del servizio vengano monitorati.

### Convenzioni stabilite durante questa sessione

- Il master **non scrive codice** — delega sempre a sub-agenti.
- Sub-agenti leggono `AGENTS.md`, `docs/00a-repo-context.md` e lo spec assegnato prima di iniziare.
- Spec files vanno in `docs/specs/*.md`, creati dal master, mai modificati dai sub-agenti.
- I sub-agenti comunicano al master: branch, file cambiati, test risultati, domande aperte.
- Comandi `ketch` richiedono `/skill:ketch` caricato prima.
