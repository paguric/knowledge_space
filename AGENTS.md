# AGENTS.md — Knowledge Space

> Standard project context for coding agents (humans and AI).  
> Keep this file in the repo root and keep it up to date when the master agent changes conventions.

## Project identity

- **Name:** Knowledge Space (`knowledge-space` / `ks`)
- **Goal:** Document ingestion, indexing, and retrieval pipeline with pluggable strategies for ingestion, chunking, embedding, retrieval, and LLM.
- **Repo type:** UV monorepo with 3 packages:
  - `packages/knowledge-base/` — pure library (models, persistence, managers, strategies).
  - `packages/mcp-server/` — MCP server adapter.
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

- Work on the `dev` branch. Never commit directly to `main`.
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

### Spec structure (KISS)

Master specs follow the **KISS** methodology (keep it simple, stupid). No long prose, no analysis of alternatives, no architectural discussions. The sub-agent must be able to read the spec in 30 seconds and know exactly what to do.

Fixed structure:

1. **Title** — `Bug XXX — description` or `Feature XXX — description`
2. **Metadata** — author, type, status, priority (one line)
3. **Cause** (for bugs) — root cause in 1-2 sentences + links to involved files
4. **Goal** (for features) — what the end user should be able to do
5. **Fix / Implementation** — approach in 2-3 numbered points, with code snippets if helpful
6. **Files to touch** — table: path → change
7. **Verification** — bash commands to test the fix works

Rules:
- No "Context" or "Overview" sections — the sub-agent reads `docs/00a-repo-context.md` for that.
- No "Option A vs Option B" — the master already chose.
- Code snippets are indicative (pseudo-code), they don't need to compile.
- Maximum 60 lines. If you need more, the spec is too complex: split it.

## Communication

- When joining a fresh session, read this file first, then read `docs/00a-repo-context.md`.
- If you are a bug/feature sub-agent, read the assigned spec from `docs/specs/` next.
- Ask the master for clarification rather than guessing.
- Summarize findings before writing code: "Here is what I found, here is what I plan to change."

## systemd service ks-serve

Path: `~/.config/systemd/user/ks-serve.service`

```ini
[Service]
ExecStart=/usr/bin/bash -c 'cd "$HOME/università/as25-26-sp/progtes/knowledge_space" && uv run ks serve --sse'
Restart=always
RestartSec=5
```

**Note:** do NOT set `Environment=XDG_STATE_HOME=...` in the service — it must use the default `~/.local/state/KnowledgeSpace/`.

**After every code change (mandatory, in this order):**
1. `cd ~/università/as25-26-sp/progtes/knowledge_space && uv sync` — rebuild `.pth` and sync packages
2. `systemctl --user daemon-reload` — reload systemd configuration
3. `systemctl --user restart ks-serve` — restart with the new code

> **Without `uv sync` the service keeps using the old bytecode/linking** (packages are `.pth`-linked to the source tree, but it's best practice to rebuild before restarting).

## CLI globale `ks` (uv tool install)

Il comando `ks` globale (senza `uv run`) è installato come tool uv in **modalità editable**:

```bash
uv tool install --editable --force --refresh .
```

- **`--editable`**: il tool punta ai sorgenti del repo (`.pth`) → le modifiche al codice sono visibili subito, nessuna reinstallazione per il codice.
- **`--refresh` è ESSENZIALE**: senza, uv riusa il wheel cacheato (build cache) e installa codice vecchio anche con `--force` (già capitato due volte).
- **Reinstallare** (stesso comando) solo quando cambiano le **dipendenze** in `pyproject.toml`.
- Il servizio systemd NON usa il tool: gira con `uv run` dal repo (vedi sopra), quindi per il servizio valgono `uv sync` + restart.

Verifica rapida dopo l'install: `ks workspace --help` deve mostrare `activate`/`deactivate`; `ks status` deve mostrare `[attivo]` sul workspace attivo.
