# Feature 013 — Registrazione immediata file in elaborazione + visualizzazione progresso

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media

## Obiettivo

Appena il watcher rileva un file, registrarlo immediatamente nella base con stato "in elaborazione". Il file non è ancora indicizzato ma compare nello stato. `ks status` e `ks info` mostrano i file in elaborazione con un indicatore. Utile per GUI futura (icona loading).

## Causa

Oggi il watcher chiama `base_manager.add_file()` in modo sincrono: fino a quando non finisce (30+ secondi per PDF grandi), il file non esiste in `kb.files`. Nessuna visibilità su cosa sta succedendo.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/models.py` — `FileEntry.status`
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — registrazione precoce + stato
- `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` — `add_file()` aggiorna stato
- `src/knowledge_space/cli/status.py` — visualizza stato elaborazione
- `src/knowledge_space/cli/info.py` o `file.py` — visualizza stato

## Fix (KISS)

1. **Aggiungere `status` a `FileEntry`**:
   ```python
   status: Literal["pending", "processing", "ready", "error"] = "ready"
   ```

2. **Registrare subito**: appena il watcher raccoglie `files_to_ingest`, creare `FileEntry(status="processing")` per ogni file, salvare stato.

3. **Aggiornare dopo ingest**: `add_file()` alla fine setta `status="ready"` e salva. Se eccezione: `status="error"`.

4. **Mostrare in status**:
   ```
   [⏳] Base: 1 file in elaborazione, 4 file pronti
   [⚠] Base: 1 errore, 3 file pronti
   ```
   Con `-a` (all flag): ogni file con la sua icona di stato.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/models.py` | Campo `status` in `FileEntry` |
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Registrazione precoce `FileEntry` + aggiornamento stato |
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | `add_file()` setta `status="ready"` a fine pipeline |
| `src/knowledge_space/cli/status.py` | Icone di stato per file in elaborazione |
| `src/knowledge_space/cli/file.py` | `ks file info` mostra stato |

### Verifica

```bash
# Aggiungi un PDF grosso in una base monitorata
cp ~/Documents/tesi.pdf ~/ws2/Base/
ks status -w ~/ws2 -a
# → [⏳] Base/tesi.pdf (in elaborazione...)
# Dopo 30s:
ks status -w ~/ws2 -a
# → [✓] Base/tesi.pdf (16 chunk)
```
