# Bug 002 — Retrieval `sparse`/`hybrid` fallisce: `rank_bm25` non è una dipendenza

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a sotto-agente
**Priorità:** alta (strategy built-in non utilizzabile nel default env)

## Sintomo
`uv run pytest` → 5 failed:
- `packages/knowledge-base/tests/test_retrieval.py::TestSparseRetrieval::*`
- `packages/knowledge-base/tests/test_retrieval.py::TestHybridRetrieval::*`

Errore:
```
packages/knowledge-base/src/knowledge_base/strategies/retrieval.py:194: in __init__
    from rank_bm25 import BM25Okapi
E   ModuleNotFoundError: No module named 'rank_bm25'
```
(Fonte: output `uv run pytest` della sessione)

## Causa radice
- `strategies/retrieval.py:192` fa lazy-import di `from rank_bm25 import BM25Okapi` e solleva
  `ImportError` se assente. (Fonte: `strategies/retrieval.py:192`)
- `rank_bm25` **non è dichiarato** né come dipendenza core né come extra in
  `packages/knowledge-base/pyproject.toml`. (Fonte: `packages/knowledge-base/pyproject.toml`)
- La roadmap (§3) elenca `sparse` come strategy di retrieval **built-in** con "fallback
  automatico a `rank_bm25` se il modello non espone `embed_sparse`", il che implica che debba
  essere disponibile out-of-the-box. (Fonte: `docs/roadmap.md` §3; `strategies/retrieval.py:8,166,172`)

## Fix atteso
1. Dichiarare `rank_bm25` come dipendenza così la strategy `sparse` funziona subito. Poiché
   `sparse` è una strategy core di retrieval, aggiungerla alle **core dependencies** di
   `knowledge-base` (in alternativa un extra `sparse`, ma core è più coerente con la roadmap).
   Poi eseguire `uv sync` per installarla nell'ambiente.
2. Come difesa, aggiungere `pytest.importorskip("rank_bm25")` nei test di retrieval interessati,
   così skip (non error) se la dipendenza mancasse per qualunque ragione.
3. Verificare che la strategy `sparse` si istanzi ed esegua su un corpus minuscolo
   (es. lista di frasi di test) senza `ImportError`.

## File da toccare
- `packages/knowledge-base/pyproject.toml` — aggiungere `rank_bm25` (core o extra).
- `packages/knowledge-base/tests/test_retrieval.py` — guardia `importorskip`.
- `packages/knowledge-base/src/knowledge_base/strategies/retrieval.py` — solo se serve migliorare
  il messaggio d'errore; altrimenti nessun cambiamento necessario una volta aggiunta la dipendenza.

## Verifica
- `uv sync` eseguito; `uv run python -c "import importlib.util as u; print(u.find_spec('rank_bm25'))"`
  → non `None`.
- `uv run pytest packages/knowledge-base/tests/test_retrieval.py -q` → 0 failed.
- `uv run pytest` (suite intera) → quei 5 test non falliscono più.

## Istruzioni per il sotto-agente
- Leggere `docs/00a-repo-context.md` e questo spec.
- Non modificare/committare i file `docs/*` del master.
- Branch: `fix/bug-002-sparse-rank-bm25-dep`.
- Al termine: riportare brevemente branch, file cambiati, comando+risultato test, dubbi.
