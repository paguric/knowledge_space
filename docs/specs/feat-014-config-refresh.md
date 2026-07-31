# Feature 014 — `ks config refresh`: ricarica e valida configurazione manuale

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** bassa

## Obiettivo

Comando `ks config refresh` che ricarica i file TOML di configurazione dal disco dopo modifiche manuali. Mostra errore se la configurazione non è valida.

## Causa

I file di configurazione (`defaults.toml`, `base.toml`) sono dentro `.knowledge-space/`, che il watcher ignora. Se l'utente modifica un `.toml` a mano, il sistema non se ne accorge finché non arriva un nuovo file da indicizzare.

File coinvolti:
- `src/knowledge_space/cli/config.py` — nuovo sottocomando `refresh`
- `packages/knowledge-base/src/knowledge_base/base_config.py` — reload della config

## Fix (KISS)

1. **`ks config refresh`**: ricarica `BaseConfig` dal file TOML della base corrente (o di tutte le basi con `--all`).
2. **Validazione**: se il TOML è malformato o contiene chiavi sconosciute → errore immediato.
3. **Trigger reindex**: dopo il reload, confronta la nuova config con quella registrata in `kb.(embedding_model,chunking_method,ingestion_library)`. Se differiscono, chiama `check_config_change()` e attiva il reindex automatico come già avviene in `add_file()` (o blocca con errore se cambio distruttivo).
4. **Messaggio successo**: `"Configurazione ricaricata: modello=sentence-transformers/..., library=docling. Reindex richiesto."`

```python
@app.command(name="refresh")
def refresh_config(
    base: Optional[str] = typer.Option(None, "-b", "--base"),
    all_bases: bool = typer.Option(False, "--all"),
):
    """Ricarica e valida la configurazione TOML dal disco."""
```

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/config.py` | Comando `refresh` con trigger reindex |
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | `reload_and_check_config()` helper |
| `docs/85-cli.md` | Aggiungere `config refresh` alla tabella comandi |

### Verifica

```bash
# Modifica un base.toml a mano (cambia modello embedding)
vim ~/ws2/Base/.knowledge-space/base.toml
ks config refresh -b Base
# → "Configurazione ricaricata: modello=sentence-transformers/all-MiniLM-L6-v2. Reindex richiesto."
# Il sistema confronta col vecchio modello e avvia il reindex
```
