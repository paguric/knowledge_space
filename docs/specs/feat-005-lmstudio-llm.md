# Feature 005 — Connessione a LM Studio per LLM locale

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** alta (sblocca pre-retrieval, post-retrieval, graph extraction)

## Contesto

Attualmente i provider LLM locali (ollama, llamacpp, vllm) sono registrati solo come metadati — la factory solleva `ProviderNotImplementedError`. Non esiste alcuna implementazione concreta.

## Obiettivo

Permettere all'utente di usare un LLM locale installato via [LM Studio](https://lmstudio.ai/). L'utente specifica il modello nel TOML di configurazione; il programma si connette all'API OpenAI-compatibile esposta da LM Studio (`http://localhost:1234/v1`).

L'approccio è **general-purpose**: l'utente scrive il nome del modello nel TOML, il programma prova a connettersi. Se LM Studio non è in esecuzione o il modello non è caricato, errore chiaro.

## Specifiche tecniche

### LM Studio API

LM Studio espone un server HTTP OpenAI-compatibile:

```
Base URL: http://localhost:1234/v1
Endpoints:
  POST /v1/chat/completions   → generazione
  GET  /v1/models             → elenco modelli caricati
```

### Configurazione TOML

L'utente configura il modello in `defaults.toml` o `base.toml`:

```toml
[pre_retrieval]
stages = [{ method = "multi_query", model = "lm-studio/Qwen2.5-7B-Instruct" }]

[post_retrieval]
reranker = { method = "llm", model = "lm-studio/Qwen2.5-7B-Instruct" }
```

Il prefisso `lm-studio/` identifica il provider. Il nome dopo `/` è l'ID del modello come appare in LM Studio (es. `Qwen2.5-7B-Instruct`, `llama-3.2-3b-instruct`).

In alternativa, per il grafo:

```toml
[graph]
model = "lm-studio/Qwen2.5-7B-Instruct"
```

### Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LMSTUDIO_BASE_URL` | `http://localhost:1234/v1` | Base URL dell'API |

### Implementazione

#### 1. Nuova classe `LMStudioLLM` in `strategies/llm.py`

```python
class LMStudioLLM(BaseLLM):
    """LLM via LM Studio (OpenAI-compatible API)."""

    name = "lm-studio"
    requires_api = False  # nessuna API key

    def __init__(self, model_id: str, base_url: str | None = None, **params):
        super().__init__(**params)
        self.model_id = model_id
        self.base_url = base_url or os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
        self._client = None  # lazy init

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key="lm-studio")

    def generate(self, messages, *, max_tokens=1024, temperature=0.0, **kwargs) -> str:
        self._ensure_client()
        response = self._client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content

    def stream(self, messages, *, max_tokens=1024, temperature=0.0, **kwargs) -> Iterator[str]:
        self._ensure_client()
        stream = self._client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

#### 2. Modifiche alla factory `llm_factory()`

Riconoscere il prefisso `lm-studio/` ed estrarre il model ID:

```python
def llm_factory(model_name: str) -> LLMStrategy:
    resolved = _ABBREVIATIONS.get(model_name, model_name)

    if resolved in _LLM_CACHE:
        return _LLM_CACHE[resolved]

    # Nuovo: provider lm-studio
    if resolved.startswith("lm-studio/"):
        model_id = resolved.split("/", 1)[1]
        instance = LMStudioLLM(model_id=model_id)
        _LLM_CACHE[resolved] = instance
        return instance

    # ... resto invariato (mock, remote non implementati)
```

#### 3. Gestione errori

- **Connessione rifiutata**: LM Studio non in esecuzione → `ConnectionError` con messaggio chiaro
- **Modello non trovato**: il nome non matcha nessun modello caricato → `ValueError` con l'elenco dei modelli disponibili
- **Timeout**: attendere max 5 secondi per la connessione

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/strategies/llm.py` | Nuova classe `LMStudioLLM`, modifica `llm_factory()` |
| `packages/knowledge-base/tests/test_llm.py` | Nuovi test con mock del client OpenAI |
| `docs/75-llm.md` | Aggiornare con LM Studio |

### Test

```python
class TestLMStudioLLM:
    def test_generate_returns_content(self):
        with patch("openai.OpenAI") as mock:
            mock.return_value.chat.completions.create.return_value = ...
            llm = LMStudioLLM(model_id="test-model")
            result = llm.generate([{"role": "user", "content": "ciao"}])
            assert isinstance(result, str)

    def test_stream_yields_tokens(self):
        ...

    def test_connection_refused_raises_clear_error(self):
        ...

    def test_model_not_found_raises_with_available_models(self):
        ...

    def test_custom_base_url_from_env(self):
        ...
```

### Cosa NON fare

- **Non** registrare modelli specifici in un registry hard-coded. L'utente scrive il nome del modello nel TOML: se LM Studio lo ha caricato, funziona.
- **Non** implementare ollama, llamacpp, vllm. Solo LM Studio per ora.
- **Non** modificare il sistema di configurazione TOML (già supporta `model = "..."` nei vari step).

## Istruzioni per feature-lead

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec
- Lavorare sul branch `dev`
- Usare l'italiano per commenti, docstring e messaggi di commit
- Non modificare/committare file sotto `docs/` o `AGENTS.md`
- Al termine: riportare branch, file cambiati, risultato test, eventuali dubbi
