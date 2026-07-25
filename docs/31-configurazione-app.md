# Configurazione dell'applicazione

> **Stato:** in progress | **Step:** 8-ter | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Panoramica

Configurazione dell'applicazione: path XDG (`RuntimePaths`), secrets (`UserSettings`), variabili d'ambiente e il loro rapporto con la configurazione delle basi (TOML).

## Scelte

| Aspetto | Scelta |
|---------|--------|
| `RuntimePaths` | Pydantic, path XDG (config, data, state) |
| `UserSettings` | `~/.config/KnowledgeSpace/config.json` (secrets, preferenze) |
| Secrets | Mai nei TOML — env var o `UserSettings` |
| `AppContext` | Unico punto DI (Step 8-ter) |

## Dettagli

### `RuntimePaths`

Classe Pydantic che racchiude tutti i path necessari, mantenendo lo standard XDG.

| Path | Default | Contenuto |
|------|---------|-----------|
| `config_home` | `~/.config/KnowledgeSpace/` | UserSettings, secrets |
| `data_home` | `~/.local/share/KnowledgeSpace/` | Chunk, dati grandi |
| `state_home` | `~/.local/state/KnowledgeSpace/` | Indici, log, DB |

**Path derivati:**
- `user_settings_file`: `config_home/config.json`
- `workspaces_index`: `state_home/workspaces.json`
- `workspace_state_file`: `<workspace>/.knowledge-space/state.json`
- `workspace_defaults_toml`: `<workspace>/.knowledge-space/defaults.toml`
- `base_toml`: `<workspace>/<base>/.knowledge-space/base.toml`
- `base_chunks_dir`: `<workspace>/<base>/.knowledge-space/chunks/`

### `UserSettings`

Gestisce `~/.config/KnowledgeSpace/config.json` con secrets e preferenze utente.

### Variabili d'ambiente

| Variabile | Descrizione |
|-----------|-------------|
| `KS_CONFIG_FILE` | Path del file `config.json` |
| `KS_DATA_DIR` | Directory base per dati |
| `KS_STATE_DIR` | Directory base per stato |
| `KS_LOG_LEVEL` | Livello di log |
| `KS_HF_TOKEN` | Token HuggingFace |
| `OPENAI_API_KEY` | Chiave API OpenAI |
| `COHERE_API_KEY` | Chiave API Cohere |
| `VOYAGE_API_KEY` | Chiave API Voyage |
| `ANTHROPIC_API_KEY` | Chiave API Anthropic |
| `GEMINI_API_KEY` | Chiave API Google Gemini |

La variabile d'ambiente ha precedenza su `UserSettings`.

### Sicurezza

- Secrets in `config.json` con permessi 600 o in env var
- L'endpoint REST `/api/v1/config` non restituisce secrets in chiaro
- I file TOML delle basi **non** contengono secrets

### Fasi di implementazione

- [x] `RuntimePaths` in `knowledge_space/runtime_paths.py`
- [ ] `AppContext` con `RuntimePaths` e `UserSettings` (Step 8-ter)
- [ ] `build_app_context()` in `knowledge_space/bootstrap.py` (Step 8-ter)

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 0 (modelli) | Step 8-ter (AppContext), Step 12 (logging), Step 13 (CLI) |
