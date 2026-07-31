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
3. **Messaggio successo**: `"Configurazione ricaricata: modello=sentence-transformers/..., library=docling"`.

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
| `src/knowledge_space/cli/config.py` | Comando `refresh` |
| `packages/knowledge-base/src/knowledge_base/base_config.py` | Eventuale helper `reload()` |

### Verifica

```bash
# Modifica un base.toml a mano
vim ~/ws2/Base/.knowledge-space/base.toml
# Corrompilo
echo "invalid toml" >> ~/ws2/Base/.knowledge-space/base.toml
ks config refresh -b Base
# → Errore: "TOML non valido in .../base.toml: ..."
```
