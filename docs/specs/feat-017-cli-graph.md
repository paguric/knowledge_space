# Feature 017 — CLI `ks graph` (init/sync/status/re-extract-schema)

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** alta (dopo feat-016)

## Obiettivo

Comandi CLI per costruire e interrogare il grafo di conoscenza, come documentato in `docs/85-cli.md` (oggi assenti).

## Causa

`docs/85-cli.md` documenta `ks graph init/sync/re-extract-schema/status` ma `src/knowledge_space/cli/` non contiene `graph.py`.

## Fix (KISS)

1. **`src/knowledge_space/cli/graph.py`** con:
   - `graph init [-w]` — `GraphManager.build_graph()` (full build).
   - `graph sync [-w] [--base <name>]` — `sync_base()` per base o tutte.
   - `graph status [-w]` — connessione Neo4j, basi, chunk nel grafo, entità/relazioni (query COUNT).
   - `graph re-extract-schema [-w]` — forza `SchemaFromTextExtractor` (LLM) e salva `schema.json`.
2. **Gating**: ogni comando controlla `graph.enabled`; se False → messaggio `"Grafo disabilitato: ks config set graph.enabled true"`.
3. **Errore connessione**: se Neo4j non raggiungibile → errore chiaro (`verify_connectivity`).
4. **`docs/85-cli.md`**: la sezione Graph esiste già — allinearla ai comandi reali.

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/graph.py` | **Nuovo**: 4 comandi |
| `src/knowledge_space/cli/__init__.py` | Registrare il gruppo |
| `docs/85-cli.md` | Allineare sezione Graph |

### Verifica

```bash
ks graph init -w ~/ws2
ks graph status -w ~/ws2
ks graph sync -w ~/ws2 --base "Metodo del simplesso"
ks graph re-extract-schema -w ~/ws2
```
