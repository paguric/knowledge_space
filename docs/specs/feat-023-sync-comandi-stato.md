# Feature 023 — Sync nei comandi che mostrano lo stato

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media (coerenza con bug-019)

## Obiettivo

Tutti i comandi di **visualizzazione** eseguono `sync()` prima di mostrare lo stato: `domain list`, `base list`, `file list`, `chunk list` (oggi mostrano un modello potenzialmente stantio — es. basi cancellate da disco che restano elencate nei domini finché non passa `status`/`tree`).

## Causa

Il bug-019 ha introdotto `sync=True` solo per `status`, `tree`, `workspace info`. I comandi `list` usano `get_workspace(ctx, workspace)` senza sync: l'utente vede dati non allineati al filesystem.

## Fix (KISS)

1. **`sync=True` nei comandi di sola lettura**: `domain list`, `base list`, `file list`, `chunk list` → `get_workspace(ctx, workspace, sync=True)`.
2. **Mai nei comandi che modificano** (add/remove/activate/deactivate): il sync lì è superfluo (operano su ciò che esiste) o pericoloso (rimozione di basi stantie prima di un'operazione mirata).
3. Regola da documentare in `docs/85-cli.md`: *i comandi di sola lettura fanno sync implicito*.

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/domain.py` | `list_domains`: `sync=True` |
| `src/knowledge_space/cli/base.py` | `list_bases` (+ `info`): `sync=True` |
| `src/knowledge_space/cli/file.py` | `list_files`: `sync=True` |
| `src/knowledge_space/cli/chunk.py` | `list_chunks`: `sync=True` |
| `docs/85-cli.md` | Regola: comandi di sola lettura fanno sync |

### Verifica

```bash
rm -rf ~/ws2/BaseInDomain
ks domain list -w ~/ws2
# → la base non compare più (senza dover passare da ks status)
ks base list -w ~/ws2
# → base rimossa
```
