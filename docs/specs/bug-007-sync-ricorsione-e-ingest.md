# Bug 007 — `sync()` non ricerca sottocartelle né ingestisce i file

**Autore piano:** agente master · **Tipo:** bug · **Stato:** da assegnare a sotto-agente
**Priorità:** alta (esperienza utente: cartelle aggiunte non hanno file né sottocartelle)

## Riproduzione

```bash
# 1. Creare una cartella con sottocartelle e file
mkdir -p ~/ws/Paper\ Accademici/Papers/2024
echo "doc1" > ~/ws/Paper\ Accademici/Papers/doc1.txt
echo "doc2" > ~/ws/Paper\ Accademici/Papers/2024/doc2.txt

# 2. Il watcher la rileva (base creata)
# 3. Problema 1: Papers/2024 NON viene registrata come base
# 4. Problema 2: i file doc1.txt e doc2.txt NON vengono indicizzati
```

## Causa radice

In `packages/knowledge-base/src/knowledge_base/workspace_manager.py`, il metodo `sync()`:

```python
for entry in ws_path.iterdir():  # solo il primo livello
    if entry.is_dir():
        workspace.bases[name] = KnowledgeBase(path=entry)  # base vuota
```

1. Non ricorre nelle sottocartelle — `Papers/2024` non viene mai scoperta.
2. Crea `KnowledgeBase` vuote senza chiamare `ingest()` — i file non sono indicizzati.

## Fix atteso

### 1. Ricorsione: scoperta di tutte le sottocartelle come basi

Modificare `sync()` (o aggiungere `_discover_subdirectories(ws_path, base_path)`) per
riconoscere strutture nidificate:

```
ws/
└── Papers/
    └── 2024/
```

Devono risultare due basi: `Papers` e `Papers/2024` (o con nomi relativi: `Papers`, `Papers/2024`).

Scegliere una convenzione per i nomi delle basi nidificate:
- Opzione A: solo il primo livello è una base (comportamento attuale, cambia spec)
- Opzione B: ogni sottocartella è una base con path relativo (es. `Papers`, `Papers/2024`)

**Raccomandazione:** Opzione B — ogni cartella è una base. `sync()` ricorre in tutte le sottocartelle.

### 2. Ingest automatica dei file nella nuova base

Dopo aver creato/aggiornato le basi, chiamare `KnowledgeBaseManager.ingest()` per
indicizzare i file.

Attenzione: `KnowledgeBaseManager` ha bisogno di un `EmbeddingModel`. Usare il modello
configurato per la base (da `base.toml`) o il default. Se nessun modello è configurato,
saltare l'ingest con WARNING.

Aggiungere un metodo `sync_and_ingest(workspace)` che:
1. Chiama `sync()` (scopre basi).
2. Per ogni base nuova o con file nuovi (check mtime), chiama `KnowledgeBaseManager.ingest()`.
3. Log: INFO per ogni file indicizzato, WARNING se modello non configurato.

### 3. Il watcher deve chiamare `sync_and_ingest`

In `WorkspaceWatcher`, cambiare `_do_sync`:
```python
def _do_sync(self) -> None:
    logger.info("Debounce scaduto, esecuzione sync_and_ingest() su %s", ...)
    manager_ref._manager.sync_and_ingest(manager_ref._workspace)
```

## File da toccare

- `packages/knowledge-base/src/knowledge_base/workspace_manager.py` —
  - `sync()` diventa ricorsivo (o nuovo metodo privato `_discover_bases_recursive`).
  - Nuovo metodo `sync_and_ingest(workspace)` che chiama `sync()` + `ingest()` per basi nuove.
  - Modificare `_do_sync` nel watcher per chiamare `sync_and_ingest`.
- `tests/test_workspace_manager.py` — aggiungere test:
  - `test_sync_discovers_nested_subdirectories`
  - `test_sync_and_ingest_indexes_files`
  - `test_sync_and_ingest_skips_when_no_model`

## Dipendenze

`KnowledgeBaseManager.ingest()` richiede un `EmbeddingModel`. Verificare che il manager
abbia accesso al modello configurato. Potrebbe servire passare un `BaseConfigLoader`
o il modello direttamente a `sync_and_ingest`.

## Verifica

```bash
# Setup
mkdir -p /tmp/ws_test/Papers/2024
echo "doc1" > /tmp/ws_test/Papers/doc1.txt
echo "doc2" > /tmp/ws_test/Papers/2024/doc2.txt
ks workspace add /tmp/ws_test

# Test
ks serve &
sleep 3
mkdir -p /tmp/ws_test/NewPapers/2023
echo "doc3" > /tmp/ws_test/NewPapers/doc3.txt
sleep 3

# Verifica
ks status --workspace /tmp/ws_test
# Deve mostrare: NewPapers e NewPapers/2023 come basi
# Deve mostrare doc3.txt indicizzato
kill %1
```

- `uv run pytest packages/knowledge-base/tests/test_workspace_manager.py -q` → verde.
- `uv run pytest -q` → nessun nuovo fallimento.

## Istruzioni per il sotto-agente

- Leggere `docs/00a-repo-context.md`, `AGENTS.md` e questo spec.
- Lavorare sul branch `dev`.
- Usa l'italiano per commenti, docstring e messaggi di commit.
- Non modificare/committare file sotto `docs/` o `AGENTS.md`.
- Al termine: riportare branch, file cambiati, risultato test, eventuali dubbi.
