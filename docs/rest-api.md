# Backend REST per il frontend React

## Framework: FastAPI (consigliata)

Rispetto a Flask e Quart, FastAPI è lo standard per backend Python moderni:

- supporto nativo a Pydantic per la validazione;
- documentazione OpenAPI/Swagger generata automaticamente;
- supporto async nativo;
- integrazione semplice con Typer per la CLI.

## Struttura del pacchetto `knowledge-space`

```
packages/knowledge-space/src/knowledge_space/
├── __init__.py
├── cli.py               # Typer CLI
├── config.py            # AppConfig / RuntimePaths / UserSettings
├── logging.py           # setup logging
├── app.py               # factory FastAPI (create_app)
├── api/
│   ├── __init__.py
│   ├── deps.py          # dipendenze FastAPI
│   ├── routers/
│   │   ├── health.py
│   │   ├── workspaces.py
│   │   ├── bases.py
│   │   ├── files.py
│   │   ├── search.py
│   │   └── config.py
│   └── schemas.py       # Pydantic models per API
└── services/
    └── ...              # thin wrapper su knowledge-base
```

## API endpoints

Versioning: `/api/v1`.

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/workspaces` | Elenca workspace |
| POST | `/api/v1/workspaces` | Crea workspace da path |
| DELETE | `/api/v1/workspaces/{name}` | Rimuove workspace |
| GET | `/api/v1/workspaces/{ws}/bases` | Elenca knowledge base |
| POST | `/api/v1/workspaces/{ws}/bases` | Crea knowledge base |
| GET | `/api/v1/workspaces/{ws}/bases/{base}/files` | Elenca file indicizzati |
| POST | `/api/v1/workspaces/{ws}/bases/{base}/files` | Upload e indicizzazione file |
| DELETE | `/api/v1/workspaces/{ws}/bases/{base}/files/{path}` | Rimuove file |
| POST | `/api/v1/workspaces/{ws}/bases/{base}/search` | Ricerca semantica |
| POST | `/api/v1/search` | Ricerca globale |
| GET | `/api/v1/config` | Mostra configurazione runtime |
| PATCH | `/api/v1/config` | Aggiorna configurazione utente |

## CORS e frontend

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

In produzione le origini dovrebbero essere configurate tramite variabili d'ambiente o `config.json`.

## Sincrono vs asincrono

Le operazioni su `Chroma` e `TinyDB` sono sincrone. I watcher di `watchdog` girano su thread separati.

**Scelta consigliata**: endpoint sync per semplicità, usando `BackgroundTask` o `run_in_threadpool` solo per operazioni lunghe (upload, indexing). La ricerca semantica può essere esposta via `run_in_threadpool` per non bloccare l'event loop.
