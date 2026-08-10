# Feature 018 — Propagazione automatica dal watcher al grafo

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media (dopo feat-016/017)

## Obiettivo

Quando `graph.enabled == true`, ogni cambiamento filesystem rilevato dal watcher si propaga al grafo Neo4j, come da trigger 1-5 di `docs/40-graph.md`.

## Causa

Oggi il grafo è statico: va costruito a mano e non segue i cambiamenti del workspace.

## Fix (KISS)

1. **Hook in `workspace_manager.sync_and_ingest()`**: dopo l'ingest dei file, se la base ha `graph.enabled`:
   - File nuovi/modificati (content change, trigger 1) → `GraphManager.sync_base(base_name)` con `on_chunk_change == "eager"` → re-estrazione LLM mirata solo sui chunk cambiati; `"lazy"` → solo Chroma, grafo allineato al prossimo `ks graph sync`.
   - Base rimossa (trigger delete) → `GraphManager.remove_base(base_name)`.
   - Move/rename (trigger 2) → `writer.update_chunk_file_name(file_id, nuovo)` property-only.
2. **Gating**: nessun costo se `graph.enabled == false` (check veloce prima di costruire il manager).
3. **Errori non fatali**: se Neo4j non è raggiungibile → WARNING nel log, il workspace continua a funzionare; il grafo si riallinea al prossimo sync.

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | Hook post-ingest in `sync_and_ingest` |
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | Esporre evento di rename (o callback) |

### Verifica

```bash
# Con grafo abilitato e Neo4j attivo
cp nuovo.pdf ~/ws2/Base/
sleep 8
ks graph status -w ~/ws2
# → conteggio chunk nel grafo aumentato (eager: entità nuove presenti)
rm ~/ws2/Base/nuovo.pdf
sleep 8
# → chunk e entità rimossi dal grafo
```
