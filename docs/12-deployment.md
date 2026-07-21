# 12 — Deployment e imballaggio

Dettagli operativi per la distribuzione di Knowledge Space: immagine Docker del backend REST ed eseguibile Windows `.exe` con bundle GUI.

> **Stato: provvisorio.** Le scelte tecnologiche concrete sono da definire. Questo documento è un segnaposto che accompagna lo [Step 18 della roadmap Fase 4](94-roadmap-fase4.md). Il bundle GUI (pywebview/Tauri/Electron) è trattato in [11-app-lifecycle.md §Packaging](11-app-lifecycle.md#packaging) ed è ortogonale alle modalità di distribuzione qui descritte.

---

## 1. Obiettivi

- **Docker**: distribuire il backend REST (`ks serve`) come container riproducibile, per deployment server / Linux / dev environment.
- **Windows `.exe`**: distribuire un bundle desktop monoutente (backend + frontend React + webview) per utenti finali senza pre-requisiti Python.

## 2. Immagine Docker

### 2.1 Base image

Da definire. Opzioni:

| Base | Pro | Contro |
|---|---|---|
| `python:3.12-slim` | Compatibilità larga, driver CPU | Immagine ~150MB, no CUDA |
| `python:3.12-alpine` | Più piccola | Build wheel lente, compatibilità multiplo |
| Base con CUDA | Embedding GPU | Immagine >2GB, solo per chi ha NVIDIA |

### 2.2 Modelli locali sentence-transformers

- **Pre-bundled**: modelli copiati in `/opt/ks-models/` durante la build → immagine grande, avvio immediato.
- **Mount esterno**: `docker volume` montato, modelli scaricati fuori dal container → immagine piccola, richiede pre-download.
- **Download all'avvio**: primo run scarica i modelli nella cache → immagine piccola, primo avvio lento, richiede rete.

### 2.3 Secrets (API keys)

- **Env vars**: `OPENAI_API_KEY`, `COHERE_API_KEY`, `VOYAGE_API_KEY`, `NEO4J_PASSWORD` (semplice, visibile in `docker inspect`).
- **Docker secrets** (Swarm/Compose): file montati in `/run/secrets/`, più sicuri.
- **Mount di `~/.config/KnowledgeSpace/config.json`**: coerente col CLI desktop.

### 2.4 Persistenza

Volumi da esporre:

- `XDG_STATE_HOME` (default `~/.local/state/KnowledgeSpace/`): Chroma, `state.json`, log.
- Workspace utente: path delle basi (può essere bind mount read-only o read-write).

### 2.5 Networking

- Porta REST (default 8000).
- Opzionale: MCP SSE sulla stessa porta o porta dedicata.
- Neo4j: container separato o esterno (stringa di connessione via env).

### 2.6 Dockerfile (bozza)

```dockerfile
# TODO: da definire
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN uv sync --frozen --extra remote
EXPOSE 8000
CMD ["uv", "run", "ks", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

### 2.7 docker-compose.yml (bozza)

```yaml
# TODO: da definire
services:
  ks:
    build: .
    ports: ["8000:8000"]
    volumes:
      - ks-state:/state
      - ./workspace:/workspace:ro
    env_file: .env
  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
volumes:
  ks-state:
```

## 3. Eseguibile Windows `.exe`

### 3.1 Tool di build

Da definire. Opzioni:

| Tool | Pro | Contro |
|---|---|---|
| **PyInstaller** | Maturato, ampiamente usato | Antivirus false positive, binary grande |
| **Nuitka** | Compila in C, più veloce | Build lenta, richiede compiler |
| **pyoxidizer** | Binary singolo, riproducibile | Meno diffuso, debug complesso |
| **Briefcase** (BeeWare) | Cross-platform, native | Più orientato a mobile |

### 3.2 Contenuto del bundle

- Python runtime embedded.
- Dipendenze `knowledge-base` + `knowledge-space` + `remote` extras.
- Frontend React compilato (static files serviti dal backend).
- (Opzionale) Chroma embedded — già incluso come dipendenza.
- (Opzionale) Neo4j embedded vs richiesta di connessione esterna.

### 3.3 Modelli locali

- **Inclusi nel `.exe`**: binary grande (>500MB con modelli multilingua),零 dipendenze post-install.
- **Scaricamento al primo avvio**: binary piccolo, primo run richiede rete.

### 3.4 Distribuzione

- Binario singolo + cartella `data/` (consigliato per dev).
- Installer NSIS o Inno Setup (consigliato per utenti finali).
- Code signing (opzionale per tesi).

### 3.5 PyInstaller spec (bozza)

```python
# KnowledgeSpace.spec — TODO: da definire
a = Analysis(
    ['src/knowledge_space/__main__.py'],
    datas=[('frontend/dist', 'frontend')],
    hiddenimports=['knowledge_base.strategies'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='KnowledgeSpace')
```

## 4. CI/CD (opzionale)

- GitHub Actions su tag `v*`:
  - Job `docker`: build & push immagine a GHCR.
  - Job `windows-exe`: build su `windows-latest`, upload artifact.
- Cache delle dipendenze `uv` per velocizzare.

## 5. Refusi e decisioni aperte

- [ ] Base image Docker definitiva.
- [ ] Strategia modelli locali (pre-bundled vs download).
- [ ] Tool per `.exe` definitivo.
- [ ] Installer vs binario portabile.
- [ ] Neo4j embedded vs esterno nel bundle desktop.
- [ ] Firma del binario Windows.

---

*Ultimo aggiornamento: 21 luglio 2026*
