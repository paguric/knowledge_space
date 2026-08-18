# Embedding configurabile per base

> **Stato:** implementato | **Step:** 6 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Panoramica

Ogni base di conoscenza può usare un modello di embedding indipendente, registrato in un registry con metadati discoverable. Il modello converte i chunk in vettori numerici per la similarity search in Chroma. La scelta è per-base e blocca il cambio se la collection non è vuota.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Modelli locali | 7 (mpnet, MiniLM, gte, bge-large, bge-m3, e5-small, e5-large) |
| Modelli remoti | 5 (OpenAI ×2, Cohere, Voyage ×2) |
| Collection Chroma | Una per base, creata con `dim` del modello |
| Cambio modello | Bloccato se collection non vuota |
| Validazione chunk | Errore se chunk > `max_context_tokens` |
| Chiavi API | Env var o `UserSettings`, mai nei TOML |

## Dettagli

### Interfaccia `EmbeddingStrategy`

```python
from typing import Protocol

class EmbeddingMetadata:
    model_name: str
    languages: list[str]       # ["en"], ["en", "it"], ["multilingual"]
    dim: int
    max_context_tokens: int
    license: str
    requires_api: bool = False

class EmbeddingStrategy(Protocol):
    name: str
    metadata: EmbeddingMetadata

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Restituisce embedding per ogni testo in input."""
        ...
```

### Modelli supportati

| Modello | `languages` | `dim` | `max_context_tokens` | Licenza | API | Note |
|---|---|---|---|---|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` | EN, IT, DE, FR, ES, PT | 384 | 128 | Apache 2.0 | No | Multilingua leggero (~470MB), input corto |
| `all-mpnet-base-v2` | EN | 768 | 384 | Apache 2.0 | No | Solo inglese |
| `all-MiniLM-L6-v2` | EN | 384 | 384 | Apache 2.0 | No | Leggero, solo EN |
| `gte-large-en-v1.5` | EN | 1024 | 8192 | Apache 2.0 | No | Top EN su MTEB |
| `bge-large-en-v1.5` | EN | 1024 | 512 | MIT | No | Buona qualità EN, ctx corto |
| `bge-m3` | multilingua (100+, 🇮🇹) | 1024 | 8192 | MIT | No | **Default**: SOTA MIRACL; dense+sparse+colbert (~2,3GB) |
| `multilingual-e5-small` | multilingua (100+, 🇮🇹) | 384 | 512 | MIT | No | Leggero, ~470 MB |
| `multilingual-e5-large` | multilingua (100+, 🇮🇹) | 1024 | 512 | MIT | No | Più pesante, migliore qualità |
| `text-embedding-3-small` | multilingua | 1536 | 8191 | Proprietaria | Sì (OpenAI) | Economico |
| `text-embedding-3-large` | multilingua | 3072 | 8191 | Proprietaria | Sì (OpenAI) | Massima qualità OpenAI |
| `embed-multilingual-v3.0` | multilingua (100+, 🇮🇹) | 1024 | 512 | Proprietaria | Sì (Cohere) | Include embed_sparse nativo |
| `voyage-3` | multilingua | 1024 | 32000 | Proprietaria | Sì (Voyage) | Contesto lungo 32k |
| `voyage-3-lite` | multilingua | 1024 | 32000 | Proprietaria | Sì (Voyage) | Versione leggera |

> **Avvertenza**: modelli solo-EN (`all-mpnet`, `all-MiniLM`, `gte-large-en`, `bge-large-en`) non sono adatti a documenti italiani. Il frontend deve mostrare le lingue supportate.

### Modelli remoti con chiave API

| Provider | Variabile d'ambiente | Modelli registrati |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `text-embedding-3-small`, `text-embedding-3-large` |
| Cohere | `COHERE_API_KEY` | `embed-multilingual-v3.0` |
| Voyage | `VOYAGE_API_KEY` | `voyage-3`, `voyage-3-lite` |

Regole: chiave via env var o `~/.config/KnowledgeSpace/config.json` (UserSettings). Env var ha precedenza. Mai nei TOML o `state.json`.

**Override endpoint** per provider OpenAI-compatible (es. Ollama):

```toml
[embedding]
model = "openai/text-embedding-3-small"
api_base = "https://api.openai.com/v1"      # default
```

### Collection Chroma per base

Ogni base usa una collection separata, creata con `dim` del modello. Cambio modello su collection non vuota → bloccato (serve `ks reindex <base> --model-change`).

```toml
[embedding]
model = "BAAI/bge-m3"
mode = "standard"                         # "standard" | "late_chunking" (pausa)
```

### Rilevamento lingua (feat-010)

Prima del chunking, la lingua del documento viene rilevata (via `langdetect`, primi 500 caratteri del Markdown) e confrontata con `EmbeddingMetadata.languages` del modello configurato:

- lingua in `languages`, oppure `"*"`/`"multilingual"` → si procede;
- lingua non supportata → warning + **skip** del file:
  `Documento in 'it' ma il modello 'all-mpnet-base-v2' supporta solo ['en']. Skipping base/ita.md.`
- lingua non rilevabile (testo vuoto/ambiguo) → si procede senza controllo.

Il controllo avviene anche nel reindex `--model-change` (prima dello short-circuit): i documenti in lingua non supportata dal nuovo modello vengono saltati, gli altri re-embeddati.

### Validazione contesto

Prima di chiamare `embed()`, il `KnowledgeBaseManager` stima la lunghezza in token del chunk e la confronta con `max_context_tokens`:
- Chunk > `max_context_tokens` → errore esplicito (non troncatura silenziosa)
- Chunk > 80% del limite → warning opzionale

### `late_chunking` (in pausa)

Modalità che elabora l'intero documento e poi estrae embedding per sottosezioni sfruttando il contesto globale. Richiede modello con `max_context_tokens ≥ 8192`. Fallback automatico a `"standard"`.

### Test

| Test | Cosa verifica |
|------|---------------|
| Dimensione embedding | Modelli diversi → dimensioni `dim` diverse |
| `max_context_tokens` superato | Errore esplicito (non troncatura) |
| Collection per base | Chroma collection isolate |
| Metadata discovery | Registry espone model_name, languages, dim, etc. |
| Cambio modello bloccato | Errore se collection non vuota |

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 3 (BaseConfig) | Step 7 (KnowledgeBaseManager), Step 8-bis (GraphRAG) |
