# Gestione della configurazione

## Stato attuale e problemi

- `settings.py` calcola i path XDG come costanti globali.
- `config.py` gestisce un file JSON con le preferenze utente (es. `hf_key`).
- `knowledge_space/main.py` chiama `setup()` e imposta **variabili globali** dentro `knowledge_base.base`, `knowledge_base.domain`, `knowledge_base.workspace`.
- I moduli di `knowledge-base` leggono queste variabili globali.

### Problemi

1. Test difficili: i test devono resettare manualmente le variabili globali.
2. Non thread-safe.
3. `knowledge-base` non è riutilizzabile in modo isolato.
4. Inversione di controllo: la libreria dipende da come il chiamante imposta le globali.
5. La configurazione di ingestion/chunking/embedding è hardcoded nel codice.

---

## Stato vs configurazione

Conviene tenere separati due concetti distinti:

| | Stato | Configurazione |
|---|------|----------------|
| Cosa | domini, basi, file, chunk, flag `active`, mtime | ingestion, chunking, embedding, parametri |
| Cambia spesso? | Sì, a runtime | No, raramente |
| Chi lo scrive | il programma | l'utente (a mano) |
| Formato | JSON (machine-friendly) | TOML (human-friendly, con commenti) |

- Lo **stato** del workspace vive in `<workspace>/.knowledge-space/config.json` (vedi [data-model.md](data-model.md)).
- La **configurazione** di ogni base vive in **TOML**, un file per base.

---

## Configurazione delle basi di conoscenza

### Filesystem

```
<workspace>/.knowledge-space/
├── config.json              # stato (struttura ad albero)
├── defaults.toml            # default per tutte le basi del workspace
└── bases/
    ├── test_kb1.toml         # configurazione specifica della base test_kb1
    └── test_kb2.toml         # configurazione specifica della base test_kb2
```

- `<workspace>/.knowledge-space/defaults.toml` → default di tutto il workspace.
- `<workspace>/.knowledge-space/bases/<base_name>.toml` → configurazione specifica di una base.

Se una base non ha il proprio `.toml`, usa i default del workspace. Se non esiste `defaults.toml`, usa i default hardcoded del programma.

### Esempio di `defaults.toml`

```toml
# Default per tutte le basi del workspace

[ingestion]
library = "docling"
# params = {}

[chunking]
method = "fixed_size"
chunk_size = 1000
chunk_overlap = 200
separator = "\n\n"

[embedding]
model = "sentence-transformers/all-mpnet-base-v2"
# device = "cpu"
```

### Esempio di `bases/test_kb1.toml`

```toml
# Configurazione della base test_kb1
# I campi mancanti ereditano da defaults.toml

[chunking]
chunk_size = 500          # override del default del workspace
chunk_overlap = 100

[embedding]
model = "sentence-transformers/all-MiniLM-L6-v2"   # base con modello più leggero
```

### Strategie (plugin/strategy pattern)

Ogni componente è identificato da un **nome** + eventuali **parametri**, in modo da poter aggiungere nuove librerie/metodi senza riscrivere il codice:

| Sezione | Campo `library`/`method`/`model` | Esempi |
|---|---|---|
| `[ingestion]` | `library` | `"docling"`, `"pypdf"`, `"unstructured"` |
| `[chunking]` | `method` | `"fixed_size"`, `"recursive"`, `"sentence"`, `"markdown"` |
| `[embedding]` | `model` | qualsiasi modello HuggingFace |

Il programma mantiene un **registro di strategie** per `ingestion`, `chunking`, `embedding`, e istanzia quella giusta in base al nome nel config. Aggiungere una nuova libreria di ingestion = registrare una nuova strategia, senza toccare il codice esistente.

### Regole di modifica

- I file TOML sono pensati per essere **modificati a mano** dall'utente (file aperto in un editor).
- La **CLI non deve poter scrivere** i file TOML: li legge soltanto.
- In futuro l'interfaccia grafica potrà modificarli, ma per ora no.
- Il programma deve **validare** il TOML all'avvio: se un valore non è riconosciuto, loggare un warning e usare il default.

### Come leggere la configurazione

Python 3.11+ include `tomllib` per leggere (non scrivere) TOML:

```python
import tomllib
from pathlib import Path

def load_base_config(base_name: str, workspace_paths) -> BaseConfig:
    # 1. Defaults hardcoded
    config = BaseConfig()
    # 2. Override con defaults.toml del workspace
    defaults_path = workspace_paths.defaults_toml
    if defaults_path.exists():
        with open(defaults_path, "rb") as f:
            config = config.override(BaseConfig.from_toml(tomllib.load(f)))
    # 3. Override con config specifica della base
    base_toml = workspace_paths.base_config_dir / f"{base_name}.toml"
    if base_toml.exists():
        with open(base_toml, "rb") as f:
            config = config.override(BaseConfig.from_toml(tomllib.load(f)))
    return config
```

---

## Configurazione dell'applicazione: `RuntimePaths` + `AppConfig`

### `RuntimePaths`

Classe Pydantic che racchiude tutti i path necessari, mantenendo lo standard XDG.

### `UserSettings`

Gestisce il file JSON con preferenze e secrets (es. `hf_key`). Separato dalla configurazione delle basi.

### `AppConfig`

Aggrega `RuntimePaths` e `UserSettings`, permettendo override da CLI/env.

```
AppConfig
├── RuntimePaths    # path XDG (config, data, state)
├── UserSettings    # config.json (hf_key, preferenze)
└── EnvSettings     # variabili d'ambiente
```

## Opzioni per passare la configurazione

1. **Fase immediata**: passare `RuntimePaths` esplicitamente ai costruttori di `Workspace` e `KnowledgeBase`.
2. **Fase successiva**: estrarre i repository (`WorkspaceRepository`, `KnowledgeBaseRepository`, `VectorStore`, `ChunkStore`) e creare `WorkspaceService`/`KnowledgeBaseService`.
3. A livello di applicazione (`knowledge-space` e `mcp-server`), usare un `AppContext` che crea una sola istanza di `RuntimePaths` e dei service per processo.

## Variabili d'ambiente

| Variabile | Descrizione |
|-----------|-------------|
| `KS_CONFIG_FILE` | Path del file config.json |
| `KS_DATA_DIR` | Directory base per dati (chunks) |
| `KS_STATE_DIR` | Directory base per stato (TinyDB, Chroma, log) |
| `KS_LOG_LEVEL` | Livello di log |
| `KS_HF_TOKEN` | Token HuggingFace (alternativa a config.json) |

## Note sulla sicurezza

- I secrets (es. `hf_key`) devono rimanere in `config.json` con permessi 600 o in variabili d'ambiente.
- L'endpoint REST `/api/v1/config` non deve mai restituire `hf_key` in chiaro.
- Considerare l'uso di `keyring` per la gestione dei token in futuro.
- I file TOML delle basi **non** contengono secrets: solo parametri di ingestion/chunking/embedding.