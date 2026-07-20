# Embedding configurabile per base

## Obiettivo

Ogni base di conoscenza può usare un modello di embedding indipendente, registrato in un registry con metadati discoverable. Il modello converte i chunk in vettori numerici per la similarity search in Chroma. La scelta del modello è per-base e blocca il cambio se la collection non è vuota (vedi [40-graph.md §9](40-graph.md)).

## Interfaccia `EmbeddingStrategy`

```python
from typing import Protocol

class EmbeddingMetadata:
    model_name: str
    languages: list[str]       # ["en"], ["en", "it"], ["multilingual"]
    dim: int                   # dimensionalità del vettore
    max_context_tokens: int    # lunghezza massima in token
    license: str              # "Apache 2.0", "MIT", "CC-BY-NC-4.0", …
    requires_api: bool = False # False = locale, True = OpenAI/Cohere/…

class EmbeddingStrategy(Protocol):
    name: str
    metadata: EmbeddingMetadata

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Restituisce embedding per ogni testo in input."""
        ...
```

## Registry e metadati discoverable

Il registry (`knowledge_base.strategies.embedding`) contiene tutte le strategie registrate. Ogni entry espone `metadata` con:

- `model_name`: identificatore HuggingFace o nome modello (es. `BAAI/bge-m3`).
- `languages`: lingue supportate dal modello. Il frontend (Fase 4) deve mostrare badge per lingua (🇮🇹 IT, 🇬🇧 EN, 🌍 multilingua) per evitare che l'utente scelga un modello solo-EN su documenti italiani.
- `dim`: dimensione del vettore di output (necessaria per creare la collection Chroma).
- `max_context_tokens`: limite massimo di token che il modello accetta in input. Se un chunk eccede questo limite, il `KnowledgeBaseManager` (Step 7) **deve** lanciare un errore esplicito (non troncare silenziosamente).
- `license`: tipo di licenza del modello (es. Apache 2.0, MIT, CC-BY-NC-4.0).
- `requires_api`: `False` se il modello gira localmente, `True` se richiede una chiamata API (OpenAI, Cohere, …).

### Modelli di embedding supportati

| Modello | `languages` | `dim` | `max_context_tokens` | Licenza | Note |
|---|---|---|---|---|---|
| `sentence-transformers/all-mpnet-base-v2` | EN | 768 | 384 | Apache 2.0 | Solo inglese; non adatto a documenti italiani. |
| `sentence-transformers/all-MiniLM-L6-v2` | EN | 384 | 384 | Apache 2.0 | Leggero; solo EN. |
| `Alibaba-NLP/gte-large-en-v1.5` | EN | 1024 | 8192 | Apache 2.0 | Top EN su MTEB (65.39); lungo contesto. |
| `BAAI/bge-large-en-v1.5` | EN | 1024 | 512 | MIT | Buona qualità EN, ctx corto. |
| `BAAI/bge-m3` | multilingua (100+, 🇮🇹) | 1024 | 8192 | MIT | SOTA MIRACL; dense+sparse+colbert; ideale per IT + terminologia tecnica. |
| `intfloat/multilingual-e5-small` | multilingua (100+, 🇮🇹) | 384 | 512 | MIT | Leggero, ~470 MB; buon compromesso per studenti IT. |
| `intfloat/multilingual-e5-large` | multilingua (100+, 🇮🇹) | 1024 | 512 | MIT | Più pesante ma migliore qualità di e5-small. |

> **Avvertenza critica — contesto e lingue**:
> - Ogni modello ha un `max_context_tokens` (es. 384 per `all-mpnet`, 8192 per `gte`/`bge-m3`). Se un chunk supera questo limite, il `KnowledgeBaseManager` deve **lanciare un errore esplicito** (non troncare silenziosamente).
> - I modelli solo-EN (`all-mpnet`, `all-MiniLM`, `gte-large-en`, `bge-large-en`) **non sono adatti a documenti italiani**: il frontend deve mostrarne le lingue supportate per evitare scelte errate (Step 15).

## Collection Chroma per base

Ogni base usa una collection Chroma separata, creata con la dimensionalità (`dim`) del modello scelto. La collection è identificata dal nome della base. Il cambio del modello di embedding su una base con collection non vuota è **bloccato** (serve `ks reindex <base> --model-change`, vedi [40-graph.md §9](40-graph.md)).

```toml
[embedding]
model = "BAAI/bge-m3"                    # modello per questa base
mode = "standard"                         # "standard" | "late_chunking" (pausa)
```

### `late_chunking` (in pausa)

Modalità di embedding che elabora l'intero documento e poi estrae embedding per sottosezioni (chunk più piccoli) sfruttando il contesto globale del documento. Richiede un modello con `max_context_tokens ≥ 8192`. Fallback automatico a `"standard"` se il documento supera il limite.

Implementazione rimandata a dopo la validazione della Fase 2.

## Validazione contesto (chunk vs modello)

Prima di chiamare `EmbeddingStrategy.embed()`, il `KnowledgeBaseManager` stima la lunghezza in token del chunk (es. via `tiktoken` per modelli EN, tokenizer HF per multilingua) e la confronta con `max_context_tokens` del modello:

- Se chunk > `max_context_tokens` → **errore esplicito**: `"Base '{base}', file '{file}', chunk {index}: lunghezza stimata {n} token supera il limite del modello ({max} token)"`.
- Se chunk > 80% di `max_context_tokens` → warning opzionale (soglia configurabile).

## Integrazione frontend

L'API REST espone un endpoint `/api/v1/models/embeddings` con l'elenco dei modelli registrati. Il frontend mostra:

- Nome modello
- Badge lingue (🇮🇹 / 🇬🇧 / 🌍)
- `dim`
- `max_context_tokens`
- Licenza

Al momento della configurazione di una base, l'utente vede il confronto tra `chunk_size` scelto e `max_context_tokens` del modello, con avviso se rischia di eccedere il limite.

## Fasi di implementazione

- **F0 — Interfaccia e registry**: definire `EmbeddingStrategy` e `EmbeddingMetadata`, modulo `knowledge_base/strategies/embedding.py`.
- **F1 — Registry model table**: popolare il registry con i 7 modelli sopra, ciascuno con i propri metadati.
- **F2 — Collection per base**: creazione collection Chroma con `dim` dal modello; isolamento per nome base.
- **F3 — Context validation**: validatore chunk-size vs `max_context_tokens` prima dell'embedding.
- **F4 — Test**: embedding della stessa query con modelli diversi produce vettori di dimensioni diverse; errore atteso su chunk troppo grande.

## Test

| Test | Cosa verifica |
|------|---------------|
| Dimensione embedding | Modelli diversi → dimensioni `dim` diverse |
| `max_context_tokens` superato | Errore esplicito (non troncatura) |
| Collection per base | Chroma collection isolate |
| Metadata discovery | Registry espone model_name, languages, dim, etc. |
| Cambio modello bloccato | Errore se collection non vuota |

---

*Ultimo aggiornamento: 21 luglio 2026*