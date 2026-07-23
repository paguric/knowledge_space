# Astrazione LLM (Large Language Model)

## Obiettivo

Definire un'interfaccia comune per tutte le chiamate a LLM all'interno del sistema, usata da:
- **Pre-retrieval**: `multi_query`, `step_back`, `least_to_most` (query rewriting).
- **Retrieval**: `query_mode = "hyde"` (documento ipotetico).
- **Post-retrieval**: `llm` reranker, `llm_chain_extract` compressor.
- **GraphRAG (Fase 1C)**: `LLMEntityRelationExtractor`, `SchemaFromTextExtractor`, `Text2CypherRetriever`.
- **LLM generatore (Fase 3/4)**: risposta finale all'utente dopo il retrieval.

Ogni componente **sceglie il proprio modello LLM** nella configurazione TOML (nessuna sezione `[llm]` globale). Il sistema fornisce un registry di modelli supportati (locali e API) e una `llm_factory` nell'`AppContext` per istanziarli.

---

## Interfaccia `LLMStrategy`

```python
from collections.abc import Iterator
from typing import Protocol


class LLMMetadata:
    model_name: str
    provider: str                 # "openai" | "anthropic" | "ollama" | "llamacpp" | "mock"
    context_window: int           # max input token (es. 128000 per gpt-4o)
    requires_api: bool            # False = locale, True = chiamata API remota
    supports_streaming: bool      # True se supporta output token-a-token
    supports_json: bool           # True se supporta output strutturato JSON (function calling)


class LLMStrategy(Protocol):
    name: str
    metadata: LLMMetadata

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs,
    ) -> str:
        """Genera testo a partire da una lista di messaggi (chat format).

        Args:
            messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
            max_tokens: token massimi in output
            temperature: 0.0 = deterministico, >0 = più creativo

        Returns:
            Testo generato.
        """
        ...

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs,
    ) -> Iterator[str]:
        """Come generate, ma restituisce un iteratore di token in streaming.

        Usato dall'LLM generatore in Fase 3/4 per risposte in tempo reale.
        """
        ...
```

### Formato messaggi

Tutte le chiamate usano il formato chat `list[dict]` con ruoli standard:
- `system` — contesto/istruzioni di sistema (es. "Sei un assistente che risponde a domande...").
- `user` — input dell'utente.
- `assistant` — risposta precedente (usata in multi-turno o few-shot).

Ogni strategy prepone il system prompt appropriato prima di chiamare il LLM.

---

## Registry

Il registry (`knowledge_base.strategies.llm`) contiene tutti i modelli LLM supportati, ciascuno con metadati discoverable.

### Modelli API remoti

| Model string | Provider | `context_window` | `supports_json` | Richiede chiave API |
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

### Modelli locali / self-hosted

| Model string | Provider | `context_window` | `supports_json` | Note |
|---|---|---|---|---|
| `ollama/<model>` | Ollama | dipende dal modello | dipende dal modello | `OLLAMA_BASE_URL` default `http://localhost:11434/v1` |
| `llamacpp/<model>` | llama.cpp | dipende dal modello | no | `LLAMACPP_BASE_URL` default `http://localhost:8080/v1` |
| `vllm/<model>` | vLLM | dipende dal modello | sì | `VLLM_BASE_URL` default `http://localhost:8000/v1` |
| `mock/<name>` | Mock | 4096 | sì | Per test, nessuna chiave richiesta. Restituisce testo prevedibile (vedi § Test). |

> I modelli locali usano API OpenAI-compatibile. Il registry li registra col prefisso `ollama/`, `llamacpp/`, `vllm/` seguito dal nome del modello (es. `ollama/llama3.1`, `vllm/mistral-nemo`).

### Strategie di default

Alcune voci comode per evitare di specificare sempre il modello completo nei TOML di esempio:

| Abbreviazione | Risolve a |
|---|---|
| `fast` | `openai/gpt-4o-mini` |
| `cheap` | `openai/gpt-4o-mini` |
| `quality` | `openai/gpt-4o` |
| `local` | `ollama/llama3.1` |

Le abbreviazioni sono overrideabili in fase di init del registry.

---

## Chiavi API e base URL

Le chiavi API **non vanno mai nei file TOML** (stessa regola di `[embedding]`). Seguono il meccanismo di `UserSettings`/env var già definito in [31-configurazione-app.md](31-configurazione-app.md):

| Provider | Variabile d'ambiente | Campo `UserSettings` |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `api_keys.OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` | `api_keys.ANTHROPIC_API_KEY` |
| Google (Gemini) | `GEMINI_API_KEY` | `api_keys.GEMINI_API_KEY` |
| Cohere | `COHERE_API_KEY` | `api_keys.COHERE_API_KEY` |
| Ollama | `OLLAMA_BASE_URL` | `api_bases.OLLAMA` |
| llama.cpp | `LLAMACPP_BASE_URL` | `api_bases.LLAMACPP` |
| vLLM | `VLLM_BASE_URL` | `api_bases.VLLM` |

Regole:
- La variabile d'ambiente ha precedenza su `UserSettings`.
- Per provider remoti (OpenAI, Anthropic, etc.), se la chiave non è presente né in env né in `UserSettings` → errore all'istanziazione della strategy.
- Per provider locali (Ollama, vLLM, llama.cpp), il base URL default è quello noto del provider; se non raggiungibile, la strategy fallisce con un errore esplicito (non timeout infinito).
- `api_base` non è configurabile per-componente nei TOML: si usa l'env var per overridare l'endpoint. Questo evita duplicazione e mantiene la configurazione di connessione separata da quella di selezione del modello.

---

## Configurazione per-componente nei TOML

Non esiste una sezione `[llm]` globale. Ogni componente che richiede un LLM specifica il proprio modello nel proprio parametro o stage.

### Pre-retrieval

```toml
[pre_retrieval]
stages = [
  { method = "multi_query", model = "openai/gpt-4o-mini", params = { n_queries = 3 } },
  { method = "step_back",   model = "openai/gpt-4o-mini" },
]
```

Ogni stage con `requires_llm = True` accetta un campo `model` opzionale. Se omesso → fallback a `identity` con warning (nessun LLM disponibile).

### Retrieval (HyDE)

```toml
[retrieval]
query_mode = "hyde"
hyde_model = "openai/gpt-4o-mini"
```

Se `query_mode = "hyde"` ma `hyde_model` non è specificato → errore (HyDE senza LLM non è implementabile; non c'è fallback identity sensato).

### Post-retrieval

```toml
[post_retrieval]
reranker = "llm"
reranker_model = "openai/gpt-4o"
compressor = "llm_chain_extract"
compressor_model = "openai/gpt-4o-mini"
```

### GraphRAG (Fase 1C)

```toml
[graph]
extraction_model = "openai/gpt-4o"       # per LLMEntityRelationExtractor
schema_model = "openai/gpt-4o"           # per SchemaFromTextExtractor (una tantum)
```

### LLM generatore (Fase 3/4)

Il modello usato per generare la risposta finale all'utente dopo il retrieval è configurato nell'applicazione (non per-base):

```toml
# In defaults.toml a livello workspace o in UserSettings
[generation]
model = "openai/gpt-4o"
```

Oppure passato come parametro della query (sovrascrivibile dall'utente). Da dettagliare in Fase 3/4.

---

## Integrazione con `AppContext`

L'`AppContext` (Step 8-ter) espone una factory per istanziare strategie LLM:

```python
from knowledge_base.strategies.llm import LLMStrategy

# Firma della factory in AppContext
llm_factory: Callable[[str], LLMStrategy]  # model_name → strategy
```

La factory:
1. Risolve il `model_name` (es. `"openai/gpt-4o-mini"` → provider OpenAI, modello `gpt-4o-mini`).
2. Cerca la chiave API o base URL nell'env var corrispondente.
3. Istanzia la strategy (con caching: stessa strategy per stesso model_name).
4. Se `model_name` non è registrato → solleva errore (non degrada silenziosamente).

I componenti che usano LLM ricevono la factory e chiamano `llm_factory(model)` per ottenere la strategy. Non devono mai istanziare strategie direttamente.

---

## Fallback

| Scenario | Comportamento |
|---|---|
| Stage pre-retrieval con `requires_llm = True` ma senza `model` | Fallback a `identity` con warning (la base funziona in degrado) |
| `query_mode = "hyde"` ma `hyde_model` assente | Errore esplicito all'avvio (HyDE senza LLM non ha senso) |
| Reranker/compressor `llm` / `llm_chain_extract` ma modello assente | Fallback a `identity` con warning |
| `[graph].extraction_model` assente ma `on_chunk_change = "eager"` | Errore esplicito (non si può estrarre entità senza LLM). Se `on_chunk_change = "lazy"`, il grafo non usa LLM → ok |
| `[graph].retriever = "text2cypher"` ma modello assente | Errore esplicito (text2cypher richiede LLM) |
| Modello specificato ma chiave API mancante | Errore all'istanziazione della strategy (non a runtime) |
| Provider locale non raggiungibile | Errore a runtime con messaggio esplicito |

Il fallback a `identity` per pre/post-retrieval è già specificato in [80-retrieval.md](80-retrieval.md) come comportamento atteso.

---

## Test

- **Mock LLM**: `mock/<name>` restituisce testo deterministico basato sul prompt. Es. `mock/echo` restituisce l'ultimo messaggio utente; `mock/fixed` restituisce "Risposta mock". Permette di testare query rewriting, HyDE, compressione senza chiamate API.
- **Registry test**: verifica che tutti i modelli registrati abbiano metadati coerenti.
- **Factory test**: verifica che `llm_factory(model)` restituisca la strategy corretta; errore su modello sconosciuto; errore su chiave API mancante.
- **Integration test** (opzionale, skip di default): test con LLM reale su query golden. Marcatore `@pytest.mark.llm` (vedi [92-roadmap-fase2.md §Step 11](92-roadmap-fase2.md)).

---

## Fasi di implementazione

- **F0 (Step 6-bis, Fase 1A)**: definire `LLMMetadata`, `LLMStrategy` Protocol, registry stub (solo `mock/` modelli), `llm_factory` in `AppContext`. `llm_factory` restituisce solo strategy mock. Nessuna dipendenza API.
- **F1 (Fase 1B)**: aggiungere provider `openai/` e `ollama/` al registry. Le strategy di pre-retrieval, HyDE e post-retrieval usano `llm_factory` dal contesto.
- **F2 (Fase 1C)**: aggiungere provider `anthropic/`, `google/`, `cohere/`, `vllm/`, `llamacpp/` on demand. GraphRAG entity extraction e text2cypher usano `llm_factory`.
- **F3 (Fase 3/4)**: streaming via `LLMStrategy.stream()`. LLM generatore per risposta all'utente. Completamento supporto provider API.

---

## Registry delle strategie (estensione)

Il registry di [80-retrieval.md §Registry](80-retrieval.md) va esteso per includere il campo `model` nelle voci che richiedono LLM:

```python
{
    "multi_query": {
        "type": "query_rewriter",
        "requires_llm": True,
        "params_schema": {
            "n_queries": int,
            "model": str,          # ← aggiunto
        },
    },
    "query_mode/hyde": {
        "type": "query_mode",
        "requires_llm": True,
        "params_schema": {
            "model": str,          # ← aggiunto
        },
    },
    "llm_chain_extract": {
        "type": "compressor",
        "requires_llm": True,
        "params_schema": {
            "model": str,          # ← aggiunto
        },
    },
}
```

---

*Ultimo aggiornamento: 22 luglio 2026*
