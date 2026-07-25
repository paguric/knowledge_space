# Deployment e imballaggio

> **Stato:** non iniziato | **Step:** 18 | **Fase:** 4 | **Aggiornato:** 22 luglio 2026

## Panoramica

Distribuzione di Knowledge Space come container Docker (backend REST) e come eseguibile Windows `.exe` (backend + frontend + webview). Le scelte concrete (base image, tool per `.exe`, strategia modelli locali) sono ancora **provvisorie**.

## Scelte

| Aspetto | Scelta |
|---------|--------|
| Docker base image | Da definire (`python:3.12-slim` candidato) |
| Modelli locali | Pre-bundled vs mount vs download (da decidere) |
| Windows tool | PyInstaller / Nuitka / Briefcase (da decidere) |
| Stato | **Provvisorio** — scelte concrete da definire |

## Dettagli

### Immagine Docker

**Opzioni base image:**

| Base | Pro | Contro |
|---|---|---|
| `python:3.12-slim` | Compatibilità larga | No CUDA |
| `python:3.12-alpine` | Più piccola | Build wheel lente |
| Base con CUDA | Embedding GPU | >2 GB |

**Persistenza:**
- `XDG_STATE_HOME`: Chroma, `state.json`, log
- Workspace utente: bind mount read-only o read-write

**Networking:**
- Porta REST (default 8000)
- MCP SSE: stessa porta o dedicata
- Neo4j: container separato o esterno

### Eseguibile Windows `.exe`

**Opzioni tool:**

| Tool | Pro | Contro |
|------|-----|--------|
| **PyInstaller** | Maturato | Antivirus false positive |
| **Nuitka** | Compilato in C | Build lenta |
| **Briefcase** | Cross-platform | Più orientato a mobile |

**Contenuto bundle:**
- Python runtime embedded
- Dipendenze `knowledge-base` + `knowledge-space`
- Frontend React compilato (static files)
- Chroma embedded
- Neo4j: embedded vs connessione esterna

### Fasi di implementazione

- [ ] Scegliere base image Docker
- [ ] Scegliere strategia modelli locali (pre-bundled vs download)
- [ ] Scegliere tool per `.exe`
- [ ] Dockerfile + docker-compose.yml
- [ ] PyInstaller spec
- [ ] CI/CD (opzionale)

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 15 (REST), Step 16 (Frontend) | Nessuno (fase finale) |
