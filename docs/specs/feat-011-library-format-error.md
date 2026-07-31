# Feature 011 — Errore esplicito se library incompatibile col formato file

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** bassa

## Obiettivo

Se una base usa `pymupdf4llm` (solo PDF) e arriva un `.docx`, mostrare errore chiaro con nome library e interrompere l'elaborazione di quel file. Stesso per `markitdown` con formati non supportati.

## Causa

`UnsupportedFormatError` esiste già e viene loggato come WARNING. Ma il messaggio non menziona il nome della library configurata, solo le estensioni. L'utente potrebbe non capire perché un `.docx` non viene processato se la base è configurata con `pymupdf4llm`.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/strategies/ingestion.py` — `UnsupportedFormatError`
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — catch e log dell'errore

## Fix (KISS)

1. **Arricchire `UnsupportedFormatError`**: aggiungere il nome della library (es. `"pymupdf4llm"`) nel messaggio:
   ```
   Formato '.docx' non supportato da pymupdf4llm. Estensioni ammesse: .pdf.
   ```
2. **Cambiare log level** da WARNING a ERROR per rendere evidente il problema.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/strategies/ingestion.py` | `UnsupportedFormatError`: aggiungere nome library al messaggio |
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | `logger.error` invece di `logger.warning` |

### Verifica

```bash
ks config set -b Base ingestion.library pymupdf4llm
ks file add Base documento.docx 2>&1
# → ERROR: "Formato '.docx' non supportato da pymupdf4llm. Estensioni ammesse: .pdf."
```
