# Strategie di chunking

> **Stato:** implementato | **Step:** 5 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Panoramica

Suddivisione del testo Markdown prodotto dall'ingestion in frammenti (chunk) secondo criteri configurabili. Ogni strategy implementa un algoritmo di split e registra metadati discoverable (nome, parametri, requisiti).

## Scelte

| Method | Descrizione | Richiede embedding |
|--------|-------------|:---:|
| `fixed_size` | Split a lunghezza fissa (no-overlap o sliding window) | No |
| `recursive` | Split gerarchico con separatori annidati | No |
| `semantic` | Split per similarità semantica tra frasi | Sì |
| `sentence` | Split per confini di frase | No |
| `markdown` | Split per header Markdown, code block intatti | No |

## Dettagli

### Interfaccia `ChunkingStrategy`

```python
from typing import Protocol
from pathlib import Path

class ChunkingStrategy(Protocol):
    name: str
    params_schema: dict[str, type]
    requires_embedding: bool = False  # True per semantic

    def split(self, text: str, **params) -> list[dict]:
        """Restituisce lista di chunk: [{"text": str, "index": int, ...}]."""
        ...
```

### Strategie base

**`fixed_size`**: split a lunghezza fissa per caratteri. `chunk_overlap = 0` → no-overlap; `> 0` → sliding window. Usa `langchain.text_splitter.CharacterTextSplitter`.

```toml
[chunking]
method = "fixed_size"
chunk_size = 1000
chunk_overlap = 200       # 0 = no-overlap, >0 = sliding window
separator = "\n\n"
```

**`recursive`**: split gerarchico usando separatori annidati (`"\n\n"` → `"\n"` → `" "` → `""`). Ideale per testo generico. Usa `langchain.text_splitter.RecursiveCharacterTextSplitter`.

```toml
[chunking]
method = "recursive"
chunk_size = 1000
chunk_overlap = 200
separators = ["\n\n", "\n", " ", ""]
```

**`semantic`**: split basato su similarità semantica tra frasi adiacenti. Ogni frase viene embeddata; il boundary è posto dove la similarità scende sotto una soglia. Richiede un modello di embedding (`requires_embedding = True`).

```toml
[chunking]
method = "semantic"
params.breakpoint_threshold_type = "percentile"  # "percentile" | "standard_deviation" | "interquartile"
params.buffer_size = 1
```

**`sentence`**: split per confini di frase (`.`, `?`, `!`). Parametro `granularity`: `"sentence"` (default) o `"paragraph"`.

```toml
[chunking]
method = "sentence"
params.granularity = "sentence"  # "sentence" | "paragraph"
```

**`markdown`**: split che rispetta la struttura Markdown. I chunk sono delimitati dagli header; il testo dentro un code block resta intatto. Usa `MarkdownHeaderTextSplitter` di langchain.

```toml
[chunking]
method = "markdown"
params.headers_to_split_on = [
    ["#", "header_1"],
    ["##", "header_2"],
    ["###", "header_3"],
]
```

### Strategie avanzate (in pausa)

- **`parent_child` (Small-to-Big)**: pattern di retrieval in `[retrieval].expansion = "parent_child"`. Vedi [80-retrieval.md](80-retrieval.md).
- **`late_chunking`**: modalità di embedding in `[embedding].mode = "late_chunking"`. Vedi [70-embedding.md](70-embedding.md).

### Registry metadati

Ogni strategy registra uno schema dei parametri accettati:

```python
{
    "fixed_size":    {"params_schema": {"chunk_size": int, "chunk_overlap": int, "separator": str}, "requires_embedding": False},
    "recursive":     {"params_schema": {"chunk_size": int, "chunk_overlap": int, "separators": list}, "requires_embedding": False},
    "semantic":      {"params_schema": {"breakpoint_threshold_type": str, "buffer_size": int}, "requires_embedding": True},
    "sentence":      {"params_schema": {"granularity": str}, "requires_embedding": False},
    "markdown":      {"params_schema": {"headers_to_split_on": list}, "requires_embedding": False},
}
```

### Test

| Test | Cosa verifica |
|------|---------------|
| `fixed_size` overlap=0 | Nessun carattere duplicato tra chunk |
| `fixed_size` overlap>0 | Sovrapposizione corretta |
| `recursive` Markdown | Split agli header, non nei code block |
| `semantic` | Richiede embedding; non crasha |
| `sentence` italiano | Boundary a `.?!` |
| `markdown` code block | Code block intatto |

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 3 (BaseConfig, strategy registry) | Step 7 (KnowledgeBaseManager) |
