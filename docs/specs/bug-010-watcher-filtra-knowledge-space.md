# Bug 010 — Watcher triggera sync per eventi dentro `.knowledge-space` (loop infinito)

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a bug-lead
**Priorità:** critica (loop infinito: ingest → chunk creati → watcher → ingest → ...)

## Riproduzione

```bash
mkdir -p ~/My\ Workspace\ 1/TestBase
cp paper.pdf ~/My\ Workspace\ 1/TestBase/
# ks serve avviato → ingest di paper.pdf
# → crea 100+ file chunk in .knowledge-space/chunks/
# → ogni chunk triggera on_created
# → sync_and_ingest → re-ingest → altri chunk → ...
# → CPU 300%, RAM 7+ GB
```

## Causa radice

In `workspace_manager.py`, il `WorkspaceWatcher._Handler` non filtra gli eventi FS. Le callback `on_created`, `on_deleted`, `on_moved` chiamano `_schedule_sync()` per **qualsiasi** evento nel workspace, incluse le cartelle `.knowledge-space/`.

Durante l'ingest di un PDF, il pipeline docling scrive 100+ file chunk in `.knowledge-space/chunks/<uuid>/` — ognuno genera un evento FS che triggera una nuova `sync_and_ingest()`.

## Fix

Aggiungere un filtro nelle callback del watcher. Se il path dell'evento contiene `.knowledge-space`, ignorarlo:

```python
def on_created(self_inner, event):
    src = getattr(event, "src_path", "")
    if ".knowledge-space" in src:
        return
    logger.info("Evento FS on_created: %s", src)
    watcher_ref._schedule_sync()
```

Stesso filtro per `on_deleted` e `on_moved`. Per `on_moved`, controllare sia `src_path` che `dest_path`.

## File da toccare

- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — aggiungere filtro in `_Handler.on_created/on_deleted/on_moved`

## Verifica

- `uv run pytest packages/knowledge-base/tests/test_workspace_manager.py -q` → verde
- `uv run pytest -q` → nessun nuovo fallimento
- Test manuale: aggiungere un PDF, verificare che non ci siano ri-ingestioni

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec
- Lavorare sul branch `dev`
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare branch, file cambiati, risultato test, eventuali dubbi.
