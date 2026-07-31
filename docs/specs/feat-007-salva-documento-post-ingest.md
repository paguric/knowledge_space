# Feature 007 — Salvare documento Markdown dopo ingestione

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media

## Obiettivo

Dopo l'ingestione, salvare il documento Markdown prodotto da docling (prima del chunking). Riutilizzarlo nei reindex che non richiedono riconversione.

## Causa

Oggi docling converte PDF/DOCX → Markdown, poi il Markdown viene chunkato e buttato via. Se cambio solo chunking strategy (`chunk_size=400`), devo rifare tutta l'ingestione da zero (PDF → Markdown → chunk), sprecando CPU.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — pipeline ingestione, `_persist_chunks`
- `packages/knowledge-base/src/knowledge_base/models.py` — `FileEntry`
- `packages/knowledge-base/src/knowledge_base/base_config.py` — `check_config_change_blocked`

## Fix (KISS)

1. **Salvare Markdown**: dopo `ingestion.convert()` e prima del chunking, scrivere il Markdown in `.knowledge-space/documents/{file_id}.md`. Aggiungere campo `doc_path` opzionale a `FileEntry`.

2. **Modificare trigger di reindex**:
   - `--ingestion-change`: come oggi → riconverte tutto (PDF → MD → chunk)
   - `--chunking-change`: NON riconverte → ri-legge MD salvato → ri-chunka soltanto
   - `--model-change`: come oggi → ri-embeddda solo (non tocca documenti)

3. **Pulizia**: `ks base remove` cancella anche `documents/`.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | Salvare MD dopo ingestione; ri-leggere MD nel reindex chunking |
| `packages/knowledge-base/src/knowledge_base/models.py` | Campo `doc_path` in `FileEntry` |
| `packages/knowledge-base/src/knowledge_base/base_config.py` | `check_config_change_blocked`: `--chunking-change` non richiede riconversione |

### Verifica

```bash
# Ingestisci un PDF
ks file add Base paper.pdf
# Verifica che esista il .md salvato
ls ws/Base/.knowledge-space/documents/
# → {file_id}.md
# Cambia chunk_size e reindicizza
ks config set -b Base chunking.chunk_size 400
ks reindex Base --chunking-change
# → non deve riprocessare il PDF (no docling, più veloce)
```
