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

### Convenzioni stabilite durante questa sessione

- Il master **non scrive codice** — delega sempre a sub-agenti.
- Sub-agenti leggono `AGENTS.md`, `docs/00a-repo-context.md` e lo spec assegnato prima di iniziare.
- Spec files vanno in `docs/specs/*.md`, creati dal master, mai modificati dai sub-agenti.
- I sub-agenti comunicano al master: branch, file cambiati, test risultati, domande aperte.
- Comandi `ketch` richiedono `/skill:ketch` caricato prima.
