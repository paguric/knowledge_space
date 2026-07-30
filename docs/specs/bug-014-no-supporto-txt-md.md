# Bug 014 — Ingestione non supporta file `.txt` e `.md`

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** media

## Causa

`strategies/ingestion.py` accetta solo `.pdf`, `.docx`, `.pptx`, `.html`, `.xhtml`. File `.txt` e `.md` (comunissimi) vengono rifiutati con `ValueError`. File rifiutati non compaiono né in stato né in log come file registrati.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/strategies/ingestion.py` — lista estensioni

## Come riprodurre

```bash
echo "test content" > /path/to/base/file.txt
# Aspetta ingest
ks status -w /path
# → file.txt non appare
journalctl --user -u ks-serve --since "30 sec ago" | grep "non supportato"
# → Formato '.txt' non supportato
```

## Fix atteso

Aggiungere supporto per `.txt` e `.md` con strategia `text` (lettura raw del contenuto, nessuna conversione). Sono i formati più semplici da supportare.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/strategies/ingestion.py` | Nuova strategia `text` per .txt/.md |

### Verifica

```bash
echo "cercami: retrieval augmented generation" > /path/to/base/test.txt
sleep 10
ks search -w /path "retrieval augmented generation"
# → deve trovare il file
```
