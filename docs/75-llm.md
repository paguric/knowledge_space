# Astrazione LLM (Large Language Model)

> **Stato:** in progress | **Step:** 6-bis | **Fase:** 1A | **Aggiornato:** 28 luglio 2026

## Panoramica

Interfaccia comune per tutte le chiamate a LLM nel sistema: pre-retrieval (query rewriting), retrieval (HyDE), post-retrieval (reranker, compressor) e GraphRAG (entity extraction). Ogni componente sceglie il proprio modello nella configurazione TOML — nessuna sezione `[llm]` globale.

**Unico provider supportato: [LM Studio](https://lmstudio.ai/)** — server locale con API OpenAI-compatibile su `http://localhost:1234/v1`. L'utente installa LM Studio, carica un modello, e lo referenzia nei TOML come `lm-studio/<model-id>`.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Interfaccia | `LLMStrategy` Protocol con `generate()` e `stream()` |
| Config per-componente | Nessuna sezione `[llm]` globale; ogni componente sceglie il modello |
| Provider | Solo LM Studio (API OpenAI-compatibile locale) |
| Mock per test | `mock/echo`, `mock/fixed` |
| Abbreviazioni | `local` → `lm-studio/auto` (rileva automaticamente il primo modello caricato) |
| Chiavi API | Nessuna (LM Studio è locale, no auth) |
| Fallback | identity + warning per pre/post-retrieval; errore per hyde/extraction |

## Dettagli

### Interfaccia `LLMStrategy`

```python
from collections.abc import Iterator
from typing import Protocol

class LLMMetadata:
    model_name: str
    provider: str                 # "lm-studio" | "mock"
    context_window: int
    requires_api: bool            # sempre False per LM Studio
    supports_streaming: bool
    supports_json: bool

class LLMStrategy(Protocol):
    name: str
    metadata: LLMMetadata

    def generate(self, messages: list[dict[str, str]], *, max_tokens: int = 1024, temperature: float = 0.0, **kwargs) -> str:
        """Genera testo da una lista di messaggi (chat format)."""
        ...

    def stream(self, messages: list[dict[str, str]], *, max_tokens: int = 1024, temperature: float = 0.0, **kwargs) -> Iterator[str]:
        """Come generate, ma restituisce un iteratore di token in streaming."""
        ...
```

Formato messaggi: `list[dict]` con ruoli `system`, `user`, `assistant`.

### Provider: LM Studio

LM Studio espone un'API HTTP OpenAI-compatibile. Non serve API key — la connessione è locale.

| Modello | Descrizione |
|---------|-------------|
| `lm-studio/<model-id>` | Qualsiasi modello caricato in LM Studio (es. `lm-studio/qwen2.5-7b-instruct`) |

L'utente **non** sceglie da un elenco predefinito: scrive il nome del modello nel TOML e il programma tenta la connessione. Se LM Studio non è in esecuzione o il modello non è caricato, viene restituito un errore chiaro.

### Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LMSTUDIO_BASE_URL` | `http://localhost:1234/v1` | Base URL dell'API |

### Abbreviazioni

| Abbreviazione | Risolve a |
|---|---|
| `local` | `lm-studio/auto` (primo modello caricato) |

### Configurazione per-componente nei TOML

**Pre-retrieval:**
```toml
[pre_retrieval]
stages = [
  { method = "multi_query", model = "lm-studio/qwen2.5-7b-instruct", params = { n_queries = 3 } },
]
```

**Retrieval (HyDE):**
```toml
[retrieval]
query_mode = "hyde"
hyde_model = "lm-studio/qwen2.5-7b-instruct"
```

**Post-retrieval:**
```toml
[post_retrieval]
reranker = "llm"
reranker_model = "lm-studio/qwen2.5-7b-instruct"
```

**GraphRAG:**
```toml
[graph]
extraction_model = "lm-studio/qwen2.5-7b-instruct"
```

### Integrazione con `AppContext`

L'`AppContext` espone una factory:

```python
llm_factory: Callable[[str], LLMStrategy]  # model_name → strategy
```

La factory: riconosce il prefisso `lm-studio/`, estrae il model ID, istanzia `LMStudioLLM` (con caching). Per i mock, istanzia `MockEchoLLM` o `MockFixedLLM`.

### Gestione errori

| Scenario | Comportamento |
|---|---|
| LM Studio non in esecuzione | `ConnectionError`: "LM Studio non raggiungibile a http://localhost:1234/v1. Avviare LM Studio e caricare un modello." |
| Modello non trovato | `ValueError`: "Modello 'qwen2.5-7b-instruct' non caricato in LM Studio. Modelli disponibili: [...]" |
| Stage pre-retrieval senza `model` | Fallback a `identity` con warning |
| `query_mode = "hyde"` ma `hyde_model` assente | Errore esplicito |
| Reranker/compressor `llm` ma modello assente | Fallback a `identity` con warning |
| `[graph].extraction_model` assente | Errore esplicito |

### Fallback

| Scenario | Comportamento |
|---|---|
| Stage pre-retrieval con `requires_llm = True` ma senza `model` | Fallback a `identity` con warning |
| `query_mode = "hyde"` ma `hyde_model` assente | Errore esplicito |
| Reranker/compressor `llm` ma modello assente | Fallback a `identity` con warning |
| `[graph].extraction_model` assente + `on_chunk_change = "eager"` | Errore esplicito |

### Test

- **Mock LLM**: `mock/echo` restituisce l'ultimo messaggio utente; `mock/fixed` restituisce "Risposta mock".
- **Factory test**: `llm_factory("lm-studio/test-model")` restituisce `LMStudioLLM`; errore su modello sconosciuto.
- **Integration test** (opzionale): test con LM Studio reale. Marcatore `@pytest.mark.llm`.

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 6 (EmbeddingStrategy per struttura registry) | Step 8 (pre/post-retrieval), Step 8-bis (GraphRAG extraction) |
