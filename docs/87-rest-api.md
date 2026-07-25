# Backend REST

> **Stato:** non iniziato | **Step:** 15 | **Fase:** 4 | **Aggiornato:** 22 luglio 2026

## Decisioni chiave

| Aspetto | Scelta |
|---------|--------|
| Framework | FastAPI + Pydantic + uvicorn |
| Versioning API | `/api/v1` |
| CORS | Configurabile via env/config |
| Sync vs Async | Endpoint sync, `run_in_threadpool` per operazioni lunghe |
| Frontend | Static files serviti dal backend (stessa porta) |

## Obiettivo

Thin layer REST sopra i manager già testati, per il frontend React e la CLI client.

## Struttura pacchetto

```
packages/knowledge-space/src/knowledge_space/
├── cli.py               # Typer CLI
├── context.py           # AppContext
├── bootstrap.py         # build_app_context
├── logging.py           # setup logging
├── app.py               # factory FastAPI (create_app)
├── api/
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

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/workspaces` | Elenca workspace |
| POST | `/api/v1/workspaces` | Crea workspace |
| DELETE | `/api/v1/workspaces/{name}` | Rimuove workspace |
| GET | `/api/v1/workspaces/{ws}/bases` | Elenca basi |
| POST | `/api/v1/workspaces/{ws}/bases` | Crea base |
| GET | `/api/v1/workspaces/{ws}/bases/{base}/files` | Elenca file |
| POST | `/api/v1/workspaces/{ws}/bases/{base}/files` | Upload + indicizzazione |
| DELETE | `/api/v1/workspaces/{ws}/bases/{base}/files/{path}` | Rimuove file |
| POST | `/api/v1/workspaces/{ws}/bases/{base}/search` | Ricerca semantica |
| POST | `/api/v1/search` | Ricerca globale |
| GET | `/api/v1/config` | Config runtime |
| PATCH | `/api/v1/config` | Aggiorna config utente |
| GET | `/api/v1/models/embeddings` | Modelli embedding registrati |

## CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Fasi di implementazione

- [ ] Aggiungere `fastapi` e `uvicorn` alle dipendenze
- [ ] Creare `knowledge_space/api/app.py` con `create_app`
- [ ] Implementare router `health`, `workspaces`, `bases`, `files`, `search`, `config`
- [ ] Aggiungere CORS
- [ ] Endpoint `/api/v1/models/embeddings`
- [ ] Test

## Dipendenze

- **Dipende da:** Step 13 (CLI)
- **Usato da:** Step 16 (Frontend), Step 18 (packaging)

---

*Ultimo aggiornamento: 22 luglio 2026*
