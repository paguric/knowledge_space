# Feature 005 — Connessione a LM Studio per LLM locale

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** alta

## Obiettivo

Usare LM Studio come LLM locale. Utente scrive `model = "lm-studio/Qwen2.5-7B-Instruct"` nel TOML. Il programma chiama l'API OpenAI-compatibile su `http://localhost:1234/v1`.

## Causa

Provider locali (ollama, llamacpp, vllm) solo metadati — `ProviderNotImplementedError`. Nessuna implementazione concreta.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/strategies/llm.py` — registry, factory, classi LLM

## Fix (KISS)

1. **Nuova classe `LMStudioLLM`** in `strategies/llm.py`. Wrappa `openai.OpenAI` con `base_url=http://localhost:1234/v1`, `api_key="lm-studio"`. Metodi `generate()` e `stream()`. Lazy init del client.

2. **Modifica `llm_factory()`**: riconosci prefisso `lm-studio/`, estrai model ID, istanzia `LMStudioLLM`.

3. **Pulizia**: rimuovi `_LOCAL_MODELS`, `_register_local()`, url/env per ollama/llamacpp/vllm. Tieni remoti (OpenAI/Anthropic/Google/Cohere) come stub. Tieni mock e abbreviazioni.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/strategies/llm.py` | `LMStudioLLM`, factory, rimuovi locali |
| `packages/knowledge-base/tests/test_llm.py` | Test `LMStudioLLM` con mock `openai.OpenAI` |

### Verifica

```bash
uv run pytest packages/knowledge-base/tests/test_llm.py -v
```
