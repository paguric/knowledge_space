# Strategie di chunking

> **Stato:** implementato | **Step:** 5 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Decisioni chiave

| Method | Descrizione | Richiede embedding |
|--------|-------------|:---:|
| `fixed_size` | Split a lunghezza fissa (no-overlap o sliding window) | No |
| `recursive` | Split gerarchico con separatori annidati | No |
| `semantic` | Split per similarità semantica tra frasi | Sì |
| `sentence` | Split per confini di frase | No |
| `markdown` | Split per header Markdown, code block intatti | No |

## Obiettivo

Suddividere il testo Markdown prodotto dall'ingestion in frammenti (chunk) secondo criteri configurabili. Ogni strategy implementa un algoritmo di split e registra metadati discoverable (nome, parametri, requisiti). I chunk vengono poi scritti su disco (Step 7) e indicizzati in Chroma.

## Interfaccia `ChunkingStrategy`

```python
from typing import Protocol
from pathlib import Path

class ChunkingStrategy(Protocol):
    name: str
    params_schema: dict[str, type]  # mappa nome → tipo atteso
    requires_embedding: bool = False  # True per semantic

    def split(self, text: str, **params) -> list[dict]:
        """Restituisce lista di chunk: [{"text": str, "index": int, ...}].
        
        Args:
            text: testo Markdown da suddividere
            params: parametri specifici della strategy (da BaseConfig.chunking.params)
        
        Returns:
            lista di dict, ciascuno con almeno "text" e "index"
        """
        ...
```


## Strategie base (priorità 1)

### `fixed_size`

Split a lunghezza fissa per caratteri. Unica strategy, due comportamenti via parametro:

- `chunk_overlap = 0` → **no-overlap**: ogni carattere appartiene a un solo chunk.
- `chunk_overlap > 0` → **sliding window**: i chunk si sovrappongono di `chunk_overlap` caratteri.

Internamente usa `langchain.text_splitter.CharacterTextSplitter`.

```toml
[chunking]
method = "fixed_size"
chunk_size = 1000
chunk_overlap = 200       # 0 = no-overlap, >0 = sliding window
separator = "\n\n"
```

### `recursive`

Split gerarchico usando separatori annidati. Prova a splittare con `"\n\n"`, poi `"\n"`, poi `" "`, poi `""`. Ideale per testo generico (Markdown, prosa).

Internamente usa `langchain.text_splitter.RecursiveCharacterTextSplitter`.

```toml
[chunking]
method = "recursive"
chunk_size = 1000
chunk_overlap = 200
separators = ["\n\n", "\n", " ", ""]
```

### `semantic`

Split basato su similarità semantica tra frasi adiacenti. Ogni frase viene embeddata (costo: una chiamata di embedding per frase) e il boundary viene posto dove la similarità tra embedding consecutivi scende sotto una soglia.

**Richiede un modello di embedding** (`requires_embedding = True`). Non adatto come default: va abilitato esplicitamente dall'utente.

```toml
[chunking]
method = "semantic"
params.breakpoint_threshold_type = "percentile"  # "percentile" | "standard_deviation" | "interquartile"
params.buffer_size = 1
```

### `sentence`

Split per confini di frase (`.`, `?`, `!`). Parametro `granularity`:

- `"sentence"` (default): un chunk per frase.
- `"paragraph"`: un chunk per paragrafo (unione di frasi consecutive).

```toml
[chunking]
method = "sentence"
params.granularity = "sentence"  # "sentence" | "paragraph"
```

### `markdown`

Split che rispetta la struttura Markdown. Usa `MarkdownHeaderTextSplitter` di langchain: i chunk sono delimitati dagli header (`#`, `##`, `###`); il testo all'interno di un code block resta intatto.

```toml
[chunking]
method = "markdown"
params.headers_to_split_on = [
    ["#", "header_1"],
    ["##", "header_2"],
    ["###", "header_3"],
]
```

## Strategie avanzate (priorità 2 — in pausa)

### `parent_child` (Small-to-Big)

**Non è una strategy di chunking**: è un pattern di retrieval che arricchisce un chunker base. Viene esposto in `[retrieval].expansion = "parent_child"` con `parent_granularity = "section" | "paragraph"`. Il chunker base produce i child (chunk piccoli, precisi); a runtime il retrieval matcha sul child ma restituisce il parent (chunk più ampio) per più contesto. Vedi [80-retrieval.md](80-retrieval.md).

### `late_chunking`

**Non è una strategy di chunking**: è una modalità di embedding che richiede un modello long-context (≥8192 token). Viene esposto in `[embedding].mode = "late_chunking"` con fallback automatico a `"standard"` se il documento supera `max_context_tokens`. Vedi [70-embedding.md](70-embedding.md).

## Registry metadati

Ogni strategy registra (oltre al nome) uno schema dei parametri accettati. Il registry espone una lista discoverable che il frontend (Fase 4) userà per guidare la configurazione utente.

```python
{
    "fixed_size": {
        "params_schema": {"chunk_size": int, "chunk_overlap": int, "separator": str},
        "requires_embedding": False,
    },
    "recursive": {
        "params_schema": {"chunk_size": int, "chunk_overlap": int, "separators": list},
        "requires_embedding": False,
    },
    "semantic": {
        "params_schema": {"breakpoint_threshold_type": str, "buffer_size": int},
        "requires_embedding": True,
    },
    "sentence": {
        "params_schema": {"granularity": str},
        "requires_embedding": False,
    },
    "markdown": {
        "params_schema": {"headers_to_split_on": list},
        "requires_embedding": False,
    },
}
```

## Fasi di implementazione

- **F0 — Interfaccia e registry**: definire `ChunkingStrategy` (Protocol), modulo `knowledge_base/strategies/chunking.py`, registrare tutte le 5 strategy base.
- **F1 — `fixed_size`**: implementare con `CharacterTextSplitter`. Test per `chunk_overlap = 0` (no-overlap) e `> 0` (sliding window). Verificare che i chunk non si sovrappongano quando overlap = 0.
- **F2 — `recursive`**: implementare con `RecursiveCharacterTextSplitter`. Test su testo Markdown annidato.
- **F3 — `semantic`**: implementare con `SemanticChunker` di langchain (o custom). Aggiungere controllo su `requires_embedding`: il manager deve passare un embedder o rifiutare.
- **F4 — `sentence`**: split per confini `.`/`?`/`!`. Attenzione: il boundary corretto richiede un tokenizer linguistico (NLTK `punkt` multilingua) o una regex. Test con testo italiano e inglese.
- **F5 — `markdown`**: implementare con `MarkdownHeaderTextSplitter`. Test con code block, header annidati.
- **F6 — Test**: test unit per ogni strategy; test specifici per `fixed_size` no-overlap vs sliding-window.

## Test

| Test | Cosa verifica |
|------|---------------|
| `fixed_size` overlap=0 | Nessun carattere duplicato tra chunk |
| `fixed_size` overlap>0 | Sovrapposizione corretta |
| `recursive` Markdown | Split agli header, non nei code block |
| `semantic` | Richiede embedding; non crasha |
| `sentence` italiano | Boundary a `.`?`!` |
| `markdown` code block | Code block intatto |

## Dipendenze

- **Dipende da:** Step 3 (BaseConfig, strategy registry)
- **Usato da:** Step 7 (KnowledgeBaseManager)

---

*Ultimo aggiornamento: 22 luglio 2026 (Step 5 implementato: 5 strategy con registry, params_schema discoverable, semantic custom con EmbeddingStrategy, 46 test)*