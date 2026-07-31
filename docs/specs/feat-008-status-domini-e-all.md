# Feature 008 — `ks status` mostra domini e opzione `-a` per dettaglio file/chunk

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** bassa

## Obiettivo

`ks status` mostra i domini con le loro basi (default). Con `-a` mostra anche file e chunk per ogni base.

## Causa

Oggi `ks status` elenca solo le basi. I domini sono menzionati solo come conteggio (`Domini: 1`) senza mostrare quali basi appartengono a quale dominio. Per vedere i file serve `ks file list`, per i chunk `ks chunk list`.

File coinvolti:
- `src/knowledge_space/cli/status.py`

## Fix (KISS)

1. **Default**: sotto le statistiche, mostrare i domini con le basi associate:
   ```
     Domini:
       Paper Accademici: papers1, papers2, paper3
     Basi standalone:
       Progetto di Tesi
   ```

2. **Flag `-a`/`--all`**: mostra file e chunk nidificati:
   ```
     Progetto di Tesi:
       descrizione_progtes.pdf: 16 chunk
         [0] attivo, hash=abc123
         [1] attivo, hash=def456
   ```

### File da toccare

| File | Modifica |
|------|----------|
| `src/knowledge_space/cli/status.py` | Aggiungere sezione domini, flag `-a`, output file/chunk |

### Verifica

```bash
ks status
# → mostra domini con basi
ks status -a
# → mostra anche file e chunk per ogni base
```
