# Feature 015 — Auto-generazione dominio quando una base ha sotto-basi

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media

## Obiettivo

Quando il watcher scopre una base che contiene sotto-basi (es. `Paper Accademici/` con dentro `papers1/`), crea automaticamente un dominio con lo stesso nome della base padre e assegna tutte le sotto-basi al dominio.

Caso "join": se la base padre è già in un dominio, le nuove sotto-basi ereditano quel dominio invece di crearne uno nuovo.

## Configurabile per workspace (default `false`)

L'auto-generazione è **disattivata di default** e va abilitata esplicitamente per workspace, con una chiave nel `defaults.toml` del workspace:

```toml
[domains]
auto_generate = false   # default: i domini restano manuali
```

- `false` (default): comportamento attuale — domini solo manuali (`domain new`, `domain auto-generate`, `domain add-base`).
- `true`: attiva l'auto-generazione descritta sotto a ogni discovery.

## Causa

Oggi i domini vanno creati manualmente con `domain auto-generate` o `domain new`. Il watcher scopre le basi ma non le raggruppa in domini.

File coinvolti:
- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` — `_discover_bases_recursive`
- `packages/knowledge-base/src/knowledge_base/domain_manager.py` — helper per auto-join

## Fix (KISS)

1. **Dopo `_discover_bases_recursive`**: iterare le basi scoperte. Per ogni base `B` che contiene almeno una sotto-base `B/sub`, se non esiste già un dominio chiamato `B`, crearlo e assegnare `B/sub` al dominio.

2. **Caso join**: se la base padre `B` è già in un dominio esistente `D`, aggiungere `B/sub` a `D.base_names` invece di creare un nuovo dominio.

3. **Solo al primo discovery**: non ri-applicare su basi già esistenti — solo quando una base è nuova (non in `workspace.bases`).

### File da toccare

| File | Modifica |
|------|----------|
| `packages/knowledge-base/src/knowledge_base/workspace_manager.py` | `sync_and_ingest`: auto-generazione dominio dopo discovery (solo se `[domains].auto_generate = true`) |
| `packages/knowledge-base/src/knowledge_base/domain_manager.py` | Eventuale helper `find_domain_for_base()` |
| `packages/knowledge-base/src/knowledge_base/base_config.py` | Sezione `[domains]` con `auto_generate = false` (default) |
| `docs/85-cli.md` | Nota su auto-generazione automatica |

### Verifica

```bash
# Crea struttura annidata
mkdir -p ~/ws2/Lezioni/lezione1
mkdir -p ~/ws2/Lezioni/lezione2
sleep 5
ks domain list -w ~/ws2
# → Lezioni: lezione1, lezione2 (auto-creato)
ks status -w ~/ws2
# → Lezioni: dominio attivo con 2 basi
```
