# Feature 001 — Step 6-bis residual: fallback `identity` + wiring `llm_factory`

**Autore piano:** agente master · **Tipo:** feature (completamento Step 6-bis) · **Stato:** da assegnare
**Priorità:** media (funzionalità incompleta, non blocca i test)

## Obiettivo
Completare i residui dell'astrazione LLM elencati in `docs/roadmap.md` §6-bis ("Mancano").

## Scope (da `docs/roadmap.md` §6-bis)
1. **Fallback `identity` + warning** per stage con `requires_llm=True` ma senza modello configurato.
   Quando uno stadio di retrieval/post-retrieval/pre-retrieval richiede un LLM ma non ha `model`
   impostato, la pipeline deve cadere back a `identity` ed emettere un `logger.warning`
   (non sollevare). (Fonte: `docs/roadmap.md` §3 — "Se un metodo richiede LLM ma non è configurato
   → fallback automatico a identity con warning"; §6-bis)
2. **Wiring di `llm_factory` in `AppContext`**: verificare che `llm_factory` sia effettivamente
   costruito e iniettato in `build_app_context()` (`knowledge_space/bootstrap.py`); il campo esiste
   in `AppContext` (`knowledge_space/context.py`) per la roadmap §2 Step 8-ter, ma va confermato
   che sia popolato e usato dalla pipeline. (Fonte: `docs/roadmap.md` §2 Step 8-ter, §6-bis)
3. **Campo `model` nel `params_schema` del registry retrieval** così lo stadio LLM per-stage può
   essere dichiarato nel TOML (es. `stages[{method="multi_query", model="..."}]`). (Fonte: `docs/roadmap.md` §6-bis)

## Indagine richiesta (il sotto-agente DEVE leggere e verificare lo stato attuale)
- `docs/75-llm.md`, `docs/80-retrieval.md`, `docs/roadmap.md` §6-bis.
- `knowledge_space/context.py`, `knowledge_space/bootstrap.py`.
- `packages/knowledge-base/src/knowledge_base/strategies/llm.py`, `search_service.py`,
  `strategies/retrieval.py`, `strategies/post_retrieval.py`, `strategies/pre_retrieval.py`.
- **Alcuni punti potrebbero essere già implementati**: implementare SOLO ciò che manca,
  senza duplicare codice esistente. Il fallback `identity` per LLM non configurato è il pezzo
  più probabile ancora assente.

## Deliverables
- Fallback `identity` + warning funzionante quando uno stadio richiede LLM senza modello.
- `llm_factory` correttamente wired in `AppContext`/`build_app_context()` (se non lo era).
- `params_schema` del registry retrieval espone il campo `model` (se non presente).
- **Test unitari** per il path di fallback (es. stadio `requires_llm=True` senza modello →
  `identity` + warning catturato via `caplog`).

## Verifica
- `uv run pytest packages/knowledge-base/tests/ -q` e `uv run pytest tests/ -q` → verde.
- Nuovi test coprono il fallback (non regressione su `TestSparseRetrieval`/`TestHybridRetrieval`
  già fixati da bug-002).

## Istruzioni per il sotto-agente
- Leggere `docs/00a-repo-context.md` e questo spec.
- Non modificare/committare i file `docs/*` del master.
- Branch: `feat/llm-fallback-wiring`.
- Al termine: riportare brevemente branch, file cambiati, comando+risultato test, dubbi.
