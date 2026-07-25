# Astrazione LLM (Large Language Model)

> **Stato:** in progress | **Step:** 6-bis | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Panoramica

Interfaccia comune per tutte le chiamate a LLM nel sistema: pre-retrieval (query rewriting), retrieval (HyDE), post-retrieval (reranker, compressor), GraphRAG (entity extraction, text2cypher) e LLM generatore (futuro). Ogni componente sceglie il proprio modello nella configurazione TOML — nessuna sezione `[llm]` globale.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Interfaccia | `LLMStrategy` Protocol con `generate()` e `stream()` |
| Config per-componente | Nessuna sezione `[llm]` globale; ogni componente sceglie il modello |
| Provider remoti | OpenAI, Anthropic, Google, Cohere |
| Provider locali | Ollama, llama.cpp, vLLM |
| Mock per test | `mock/echo`, `mock/fixed` |
| Abbreviazioni | `fast`, `cheap` → gpt-4o-mini; `quality` → gpt-4o; `local` → ollama/llama3.1 |
| Chiavi API | Env var o `UserSettings`, mai nei TOML |
| Fallback | identity + warning per pre/post-retrieval; errore per hyde/extraction |

## Dettagli

### Interfaccia `LLMStrategy`

```python
from collections.abc import Iterator
from typing import Protocol

class LLMMetadata:
    model_name: str
    provider: str                 # "openai" | "anthropic" | "ollama" | "llamacpp" | "mock"
    context_window: int
    requires_api: bool
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

### Registry — Modelli API remoti

| Model string | Provider | `context_window` | `supports_json` | Chiave API |
|---|---|---|---|---|
| `openai/gpt-4o` | OpenAI | 128000 | sì | `OPENAI_API_KEY` |
| `openai/gpt-4o-mini` | OpenAI | 128000 | sì | `OPENAI_API_KEY` |
| `openai/gpt-4.1` | OpenAI | ~1000000 | sì | `OPENAI_API_KEY` |
| `openai/o3-mini` | OpenAI | 200000 | sì | `OPENAI_API_KEY` |
| `anthropic/claude-3.5-haiku` | Anthropic | 200000 | sì | `ANTHROPIC_API_KEY` |
| `anthropic/claude-3.5-sonnet` | Anthropic | 200000 | sì | `ANTHROPIC_API_KEY` |
| `anthropic/claude-4-opus` | Anthropic | 200000 | sì | `ANTHROPIC_API_KEY` |
| `google/gemini-2.0-flash` | Google | ~1000000 | sì | `GEMINI_API_KEY` |
| `cohere/command-r-plus` | Cohere | ~128000 | sì | `COHERE_API_KEY` |

### Registry — Modelli locali / self-hosted

| Model string | Provider | `context_window` | Note |
|---|---|---|---|
| `ollama/<model>` | Ollama | dipende dal modello | `OLLAMA_BASE_URL` default `http://localhost:11434/v1` |
| `llamacpp/<model>` | llama.cpp | dipende dal modello | `LLAMACPP_BASE_URL` default `http://localhost:8080/v1` |
| `vllm/<model>` | vLLM | dipende dal modello | `VLLM_BASE_URL` default `http://localhost:8000/v1` |
| `mock/<name>` | Mock | 4096 | Per test, nessuna chiave richiesta |

### Abbreviazioni

| Abbreviazione | Risolve a |
|---|---|
| `fast` | `openai/gpt-4o-mini` |
| `cheap` | `openai/gpt-4o-mini` |
| `quality` | `openai/gpt-4o` |
| `local` | `ollama/llama3.1` |

### Chiavi API e base URL

| Provider | Variabile d'ambiente | Campo `UserSettings` |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `api_keys.OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` | `api_keys.ANTHROPIC_API_KEY` |
| Google (Gemini) | `GEMINI_API_KEY` | `api_keys.GEMINI_API_KEY` |
| Cohere | `COHERE_API_KEY` | `api_keys.COHERE_API_KEY` |
| Ollama | `OLLAMA_BASE_URL` | `api_bases.OLLAMA` |
| llama.cpp | `LLAMACPP_BASE_URL` | `api_bases.LLAMACPP` |
| vLLM | `VLLM_BASE_URL` | `api_bases.VLLM` |

Env var ha precedenza su `UserSettings`. Provider remoti senza chiave → errore all'istanziazione. Provider locali non raggiungibili → errore esplicito.

### Configurazione per-componente nei TOML

**Pre-retrieval:**
```toml
[pre_retrieval]
stages = [
  { method = "multi_query", model = "openai/gpt-4o-mini", params = { n_queries = 3 } },
  { method = "step_back",   model = "openai/gpt-4o-mini" },
]
```

**Retrieval (HyDE):**
```toml
[retrieval]
query_mode = "hyde"
hyde_model = "openai/gpt-4o-mini"
```

**Post-retrieval:**
```toml
[post_retrieval]
reranker = "llm"
reranker_model = "openai/gpt-4o"
compressor = "llm_chain_extract"
compressor_model = "openai/gpt-4o-mini"
```

**GraphRAG (Fase 1C):**
```toml
[graph]
extraction_model = "openai/gpt-4o"
schema_model = "openai/gpt-4o"
```

### Integrazione con `AppContext`

L'`AppContext` espone una factory:

```python
llm_factory: Callable[[str], LLMStrategy]  # model_name → strategy
```

La factory: risolve il `model_name`, cerca chiave/base URL nell'env var, istanzia la strategy (con caching), solleva errore se modello non registrato.

### Fallback

| Scenario | Comportamento |
|---|---|
| Stage pre-retrieval con `requires_llm = True` ma senza `model` | Fallback a `identity` con warning |
| `query_mode = "hyde"` ma `hyde_model` assente | Errore esplicito |
| Reranker/compressor `llm` ma modello assente | Fallback a `identity` con warning |
| `[graph].extraction_model` assente + `on_chunk_change = "eager"` | Errore esplicito |
| `[graph].retriever = "text2cypher"` ma modello assente | Errore esplicito |
| Modello specificato ma chiave API mancante | Errore all'istanziazione |

### Test

- **Mock LLM**: `mock/echo` restituisce l'ultimo messaggio utente; `mock/fixed` restituisce "Risposta mock".
- **Registry test**: verifica metadati coerenti per tutti i modelli.
- **Factory test**: `llm_factory(model)` restituisce strategy corretta; errore su modello sconosciuto; errore su chiave API mancante.
- **Integration test** (opzionale): test con LLM reale su query golden. Marcatore `@pytest.mark.llm`.

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 6 (EmbeddingStrategy per struttura registry) | Step 8 (pre/post-retrieval), Step 8-bis (GraphRAG extraction) |
