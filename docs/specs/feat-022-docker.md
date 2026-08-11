# Feature 022 — Distribuzione via Docker

**Autore piano:** agente master · **Tipo:** feature · **Stato:** da assegnare a feature-lead
**Priorità:** media

## Obiettivo

Immagine Docker che esegue `ks serve --sse` con watcher attivo, volumi per stato/workspace/modelli, utente non-root. Sostituisce (o affianca) il systemd user service.

## Fix (KISS)

1. **Dockerfile multistage** (`Dockerfile` in repo root):
   - Stage build: `ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, `uv sync --frozen --no-dev`.
   - Stage runtime: `python:3.14-slim-bookworm`, copia `/app`, `useradd -u ${USER_UID:-1000} ks`, `USER ks`.
   - Entrypoint: `ks serve --sse --host 0.0.0.0 --port 8080`.
   - `.dockerignore`: `.venv`, `demo/`, `.git`, `__pycache__`.

2. **docker-compose.yml**: servizio `ks` con:
   - `build: .` + `-p 127.0.0.1:8080:8080` (esposizione solo su localhost).
   - Volumi: `<workspace>:/workspace` (o path assoluti), `~/.local/state/KnowledgeSpace`, `~/.config/KnowledgeSpace`, `~/.cache/huggingface` — montati **con gli stessi path assoluti dell'host** su Linux, così il `workspaces.json` (path assoluti) resta valido e il pruning stale non cancella nulla.
   - `restart: unless-stopped`.
   - Su Windows: documentare che i workspace vanno registrati col path *container* e usare `--poll-interval` (feat-021).

3. **Docs**: sezione Docker in `README.md` e `docs/12-deployment.md`: build, run, volumi, uid, nota sul pruning (i volumi workspace vanno SEMPRE montati), torch CPU (index override) come ottimizzazione taglia.

### File da toccare

| File | Modifica |
|------|----------|
| `Dockerfile` | **Nuovo** |
| `.dockerignore` | **Nuovo** |
| `docker-compose.yml` | **Nuovo** |
| `README.md` | Sezione Docker |
| `docs/12-deployment.md` | Sezione Docker |

### Verifica

```bash
docker build -t ks .
docker compose up -d
curl -N http://127.0.0.1:8080/sse   # endpoint MCP risponde
docker exec ks ks status -w <workspace>
# → basi/file/chunk visibili; copiare un file nella base → watcher la indicizza
```
