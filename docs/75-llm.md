# Astrazione LLM (Large Language Model)

> **Stato:** in progress | **Step:** 6-bis | **Fase:** 1A | **Aggiornato:** 28 luglio 2026

## Panoramica

Interfaccia comune per tutte le chiamate a LLM nel sistema: pre-retrieval (query rewriting), retrieval (HyDE), post-retrieval (reranker, compressor) e GraphRAG (entity extraction). Ogni componente sceglie il proprio modello nella configurazione TOML — nessuna sezione `[llm]` globale.

**Provider supportati: LM Studio (locale) + provider remoti (OpenAI, Anthropic, Google, Cohere).** L'unico provider locale è LM Studio.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Interfaccia | `LLMStrategy` Protocol con `generate()` e `stream()` |
| Config per-componente | Nessuna sezione `[llm]` globale; ogni componente sceglie il modello |
| Provider | Solo LM Studio (locale) + OpenAI, Anthropic, Google, Cohere (remoti) |
| Mock per test | `mock/echo`, `mock/fixed` |
| Abbreviazioni | `local` → `lm-studio/auto` (rileva automaticamente il primo modello caricato) |
| Chiavi API | Env var per provider remoti; nessuna per LM Studio |
| Fallback | identity + warning per pre/post-retrieval; errore per hyde/extraction |

## Dettagli

### Interfaccia `LLMStrategy`

```python
from collections.abc import Iterator
from typing import Protocol

class LLMMetadata:
    model_name: str
    provider: str                 # "lm-studio" | "openai" | "anthropic" | "google" | "cohere" | "mock"
    context_window: int
    requires_api: bool            # True per provider remoti, False per LM Studio e mock
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
| `lm-studio/auto` | Rileva automaticamente il primo modello caricato (GET /v1/models) |

### Provider: endpoint OpenAI-compatibile generico

Un unico prefisso per **qualsiasi** servizio che espone l'API chat completions in formato OpenAI (OpenRouter, OpenAI, vLLM, llama.cpp, ...):

| Modello | Descrizione |
|---------|-------------|
| `openai-compatible/<path-modello>` | Il path è il model id dell'endpoint, slash inclusi (es. `openai-compatible/openrouter/auto-beta` → `https://openrouter.ai/openrouter/auto-beta`) |

L'endpoint si configura con due env var (vedi sotto); il model id passato all'API è tutto ciò che segue il prefisso `openai-compatible/`.

L'utente **non** sceglie da un elenco predefinito: scrive il nome del modello nel TOML e il programma tenta la connessione. Se LM Studio non è in esecuzione o il modello non è caricato, viene restituito un errore chiaro.

### Variabili d'ambiente

**LM Studio:**

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | Base URL dell'API |

**Endpoint OpenAI-compatibile generico:**

| Variabile | Descrizione |
|-----------|-------------|
| `OPENAI_COMPATIBLE_BASE_URL` | Base URL dell'endpoint (es. `https://openrouter.ai/api/v1`, `https://api.openai.com/v1`) |
| `OPENAI_COMPATIBLE_API_KEY` | API key (per OpenRouter: `sk-or-...`; per OpenAI: `sk-...`) |

**Provider remoti non OpenAI-compatibili (stub):**

| Variabile | Provider | Descrizione |
|-----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic | API key |
| `GEMINI_API_KEY` | Google | API key |
| `COHERE_API_KEY` | Cohere | API key |

Env var ha precedenza su `UserSettings`. Endpoint senza chiave → errore all'istanziazione.

### Registry

| Model string | Provider | Stato |
|---|---|---|
| `mock/echo`, `mock/fixed` | mock | istanziabile |
| `lm-studio/auto` | lm-studio | istanziabile (factory) |
| `anthropic/claude-3.5-haiku`, `claude-3.5-sonnet`, `claude-4-opus` | anthropic | stub (`ProviderNotImplementedError`) |
| `google/gemini-2.0-flash` | google | stub |
| `cohere/command-r-plus` | cohere | stub |

Oltre al registry, `llm_factory` accetta **prefissi dinamici** (costruiti al volo, non registrati): `lm-studio/<model-id>` e `openai-compatible/<path-modello>`.

### Abbreviazioni

| Abbreviazione | Risolve a |
|---|---|
| `fast` | `openai-compatible/gpt-4o-mini` |
| `cheap` | `openai-compatible/gpt-4o-mini` |
| `quality` | `openai-compatible/gpt-4o` |
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

La factory: riconosce il prefisso `lm-studio/`, estrae il model ID, istanzia `LMStudioLLM` (con caching). Per i provider remoti, convalida la API key e solleva `ProviderNotImplementedError` (le implementazioni reali arrivano dopo). Per i mock, istanzia `MockEchoLLM` o `MockFixedLLM`.

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
