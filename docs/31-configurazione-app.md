---
title: Configurazione dell'applicazione
status: in_progress
step: 8-ter
fase: 1A
updated: 2026-07-22
---

# Configurazione dell'applicazione: `RuntimePaths` + `AppConfig`

Vedi [30-configuration.md](30-configuration.md) per la configurazione delle basi di conoscenza (TOML).

---

## `RuntimePaths`

Classe Pydantic che racchiude tutti i path necessari, mantenendo lo standard XDG.

## `UserSettings`

Gestisce il file `~/.config/KnowledgeSpace/config.json` con secrets e preferenze utente (es. `hf_token`, chiavi API remote embedding). Separato dalla configurazione delle basi (TOML) e dallo stato del workspace (`state.json`). Machine-writable via `config set`, ma anche editabile manualmente dall'utente.

## `AppConfig`

Aggrega `RuntimePaths` e `UserSettings`, permettendo override da CLI/env.

```
AppConfig
├── RuntimePaths    # path XDG (config, data, state)
├── UserSettings    # ~/.config/KnowledgeSpace/config.json (secrets, preferenze)
└── EnvSettings     # variabili d'ambiente
```

## Opzioni per passare la configurazione

1. **Fase immediata**: passare `RuntimePaths` esplicitamente ai costruttori di `Workspace` e `KnowledgeBase`.
2. **Fase successiva**: estrarre i repository (`WorkspaceRepository`, `KnowledgeBaseRepository`, `VectorStore`, `ChunkStore`) e creare `WorkspaceService`/`KnowledgeBaseService`.
3. A livello di applicazione (`knowledge-space` e `mcp-server`), usare un `AppContext` che crea una sola istanza di `RuntimePaths` e dei service per processo.

## Variabili d'ambiente

| Variabile | Descrizione |
|-----------|-------------|
| `KS_CONFIG_FILE` | Path del file UserSettings `config.json` (`~/.config/KnowledgeSpace/config.json` di default) |
| `KS_DATA_DIR` | Directory base per dati (chunks) |
| `KS_STATE_DIR` | Directory base per stato (TinyDB, Chroma, log) |
| `KS_LOG_LEVEL` | Livello di log |
| `KS_HF_TOKEN` | Token HuggingFace (alternativa a config.json) |
| `OPENAI_API_KEY` | Chiave API OpenAI (embedding remoto `openai/*`) |
| `COHERE_API_KEY` | Chiave API Cohere (embedding remoto `cohere/*`) |
| `VOYAGE_API_KEY` | Chiave API Voyage AI (embedding remoto `voyage/*`) |

I modelli remoti leggono la chiave da `~/.config/KnowledgeSpace/config.json` (UserSettings) o da env var. Vedi [70-embedding.md §Modelli remoti](70-embedding.md#modelli-remoti-con-chiave-api) per i dettagli.

## Note sulla sicurezza

- I secrets (es. `hf_token`, chiavi API remote) devono rimanere in `~/.config/KnowledgeSpace/config.json` con permessi 600 o in variabili d'ambiente.
- L'endpoint REST `/api/v1/config` non deve mai restituire `hf_key` in chiaro.
- Considerare l'uso di `keyring` per la gestione dei token in futuro.
- I file TOML delle basi **non** contengono secrets: solo parametri di ingestion/chunking/embedding.

---

*Ultimo aggiornamento: 21 luglio 2026*
