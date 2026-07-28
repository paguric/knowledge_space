# Bug 001 — Test unitari di embedding remoti falliscono (`ModuleNotFoundError`)

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a sotto-agente
**Priorità:** media (suite rossa nel default env, ma i test sono unitari)

## Sintomo
`uv run pytest` → 8 failed:
- `packages/knowledge-base/tests/test_embedding.py::TestOpenAIEmbedding::*`
- `packages/knowledge-base/tests/test_embedding.py::TestCohereEmbedding::*`
- `packages/knowledge-base/tests/test_embedding.py::TestVoyageEmbedding::*`

Esempio di errore:
```
packages/knowledge-base/src/knowledge_base/strategies/embedding.py:208: in _get_client
    from openai import OpenAI
E   ModuleNotFoundError: No module named 'openai'
```
(Fonte: output `uv run pytest` della sessione; `packages/knowledge-base/tests/test_embedding.py:230`)

## Causa radice
- `strategies/embedding.py` fa **lazy-import** di `from openai import OpenAI` (e analoghi per
  cohere/voyage) dentro `_get_client()` (linea ~208). (Fonte: `strategies/embedding.py:208`)
- I pacchetti `openai`, `cohere`, `voyageai` sono dichiarati **solo** come extra opzionale
  `remote` in `packages/knowledge-base/pyproject.toml` e **non sono installati** nel default env.
  (Fonte: `packages/knowledge-base/pyproject.toml` → `[project.optional-dependencies].remote`;
  verifica: `uv run python -c "import importlib.util as u; print(u.find_spec('openai'))"` → `None`)
- I test sono **unitari** (mockano il client) e istanziano la strategy chiamando `embed()`,
  che triggera la lazy-import → `ModuleNotFoundError` invece dell'atteso `MissingAPIKeyError`.

## Fix atteso
1. Rendere i test di embedding remoti **gracefully skippabili** quando la dipendenza opzionale
   è assente. Usare `pytest.importorskip("openai")` (e `cohere`, `voyageai`) allo scope
   appropriato, oppure `pytestmark = [pytest.mark.skipif(missing, ...)]` a livello di modulo/classe.
   → verde di default, eseguibili quando l'extra `remote` è installato.
2. **Non indebolire le asserzioni**: quando il modulo È presente, i test devono ancora verificare
   `MissingAPIKeyError` e il wiring del client (`api_base`, env override, ecc.).
3. (Opzionale, documentativo) Assicurarsi che `docs/roadmap.md`/README specifichino che
   `uv sync --extra remote` installa i provider remoti; valutare un extra `test` che raggruppi
   `remote` + `rank_bm25`.

## File da toccare
- `packages/knowledge-base/tests/test_embedding.py` — aggiungere le guardie `importorskip`.
- `packages/knowledge-base/pyproject.toml` — solo se si aggiunge un extra `test` (opzionale).

## Verifica
- `uv run pytest packages/knowledge-base/tests/test_embedding.py -q` → 0 failed
  (skipped dove appropriato, eseguiti se `remote` installato).
- `uv run pytest` (suite intera) → quegli 8 test non falliscono più.

## Istruzioni per il sotto-agente
- Leggere `docs/00a-repo-context.md` e questo spec.
- Non modificare/committare i file `docs/*` del master.
- Branch: `fix/bug-001-remote-embedding-deps`.
- Al termine: riportare brevemente branch, file cambiati, comando+risultato test, dubbi.
