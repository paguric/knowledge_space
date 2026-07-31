# Feature 010 — Rilevamento lingua documento vs. modello embedding

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media

## Obiettivo

Se un documento è in italiano e il modello embedding configurato supporta solo inglese, mostrare warning e saltare l'indicizzazione.

## Causa

`EmbeddingMetadata` ha già `languages: List[str]` (es. `["en"]`, `["it", "en", "fr"]`). Ma l'ingestione non controlla se la lingua del documento è supportata. Un PDF in italiano embeddato con modello English-only produce embedding di bassa qualità.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/strategies/__init__.py` — `EmbeddingMetadata.languages`
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — pipeline ingestione
- `packages/knowledge-base/src/knowledge_base/strategies/embedding.py` — metadati modelli

## Fix (KISS)

1. **Rilevare lingua** del Markdown prodotto da docling (prima del chunking). Usare `langdetect` (leggero, no modello esterno) sui primi 500 caratteri.

2. **Confrontare** con `embedding_strategy.metadata.languages`. Se il modello supporta `"*"` (multilingue) o contiene la lingua rilevata → procedi. Altrimenti → warning + skip.

3. **Warning**: `"Documento in '{lang}' ma il modello '{model}' supporta solo {supported}. skipping."`

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | Controllo lingua dopo conversione docling |
| `packages/knowledge-base/pyproject.toml` | Dipendenza `langdetect` |
| `tests/test_embedding.py` | Test: doc in italiano + modello English-only → saltato |

### Verifica

```bash
# Configura modello English-only
ks config set -b Base embedding.model "sentence-transformers/all-MiniLM-L6-v2"
# Prova a indicizzare un PDF in italiano
ks file add Base documento_ita.pdf
# → Warning: "Documento in 'it' ma il modello 'all-MiniLM-L6-v2' supporta solo ['en']. Skipping."
```
