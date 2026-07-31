# Feature 009 — Comandi activate/deactivate (workspace, base, domain, file, chunk)

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media

## Obiettivo

Implementare `activate`/`deactivate` per workspace, base, domain, file, chunk. Solo un workspace attivo per volta: se ne attivi un altro, chiedi conferma e disattiva il precedente.

## Causa

I modelli hanno già `active: bool`. Manca solo la CLI.

File coinvolti:
- `src/knowledge_space/cli/workspace.py` — nuovo comando `activate`/`deactivate`
- `src/knowledge_space/cli/base.py` — nuovo comando `activate`/`deactivate`
- `src/knowledge_space/cli/domain.py` — nuovo comando `activate`/`deactivate`
- `src/knowledge_space/cli/file.py` — nuovo comando `activate`/`deactivate`
- `src/knowledge_space/cli/chunk.py` — nuovo comando `activate`/`deactivate`
- `packages/knowledge-base/src/knowledge_base/models.py` — aggiungere `active` al `Workspace` se manca
- `packages/knowledge-base/src/knowledge_base/persistence.py` — tracciare workspace attivo nel `GlobalIndex`

## Fix (KISS)

1. **Workspace**: aggiungere campo `active: bool = False` a `Workspace`. `GlobalIndex` tiene traccia del workspace attivo. `activate` disattiva il precedente (con `typer.confirm` se era attivo). `deactivate` spegne solo.

2. **Base, Domain, File, Chunk**: comandi banali — `activate` setta `active=True`, `deactivate` setta `active=False`, salvano stato.

3. **Sub-comandi**: usare `app.command(name="activate")` e `app.command(name="deactivate")` dentro ogni file CLI, oppure fare un unico comando con sottocomandi:
   ```
   ks workspace activate [<path>]   # attiva workspace (default: cwd/last)
   ks workspace deactivate           # disattiva workspace attivo
   ks base activate <name>
   ks base deactivate <name>
   ks domain activate <name>
   ks domain deactivate <name>
   ks file activate <path>
   ks file deactivate <path>
   ks chunk activate <id>
   ks chunk deactivate <id>
   ```

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/models.py` | Campo `active` in `Workspace` |
| `packages/knowledge-base/src/knowledge_base/persistence.py` | Tracciamento workspace attivo |
| `src/knowledge_space/cli/workspace.py` | Comandi `activate`/`deactivate` |
| `src/knowledge_space/cli/base.py` | Comandi `activate`/`deactivate` |
| `src/knowledge_space/cli/domain.py` | Comandi `activate`/`deactivate` |
| `src/knowledge_space/cli/file.py` | Comandi `activate`/`deactivate` |
| `src/knowledge_space/cli/chunk.py` | Comandi `activate`/`deactivate` |

### Verifica

```bash
ks workspace activate ~/ws2
# → "Workspace attivato: /home/lapo225/ws2"
ks workspace activate ~/ws3
# → "⚠ Workspace /home/lapo225/ws2 è attivo. Disattivarlo? [y/N]"
ks workspace deactivate
# → "Workspace disattivato"
ks base deactivate "Paper Accademici"
ks search "query"
# → Paper Accademici escluso dai risultati
```
