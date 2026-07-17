# CLI standalone

Il backend deve poter funzionare autonomamente da riga di comando, senza frontend.

## Libreria: Typer (consigliata)

Rispetto a Click e argparse, Typer offre:

- type hints come contratto per i comandi;
- help automatico;
- comandi nidificati semplici;
- buona integrazione con FastAPI.

## Comandi proposti

| Comando | Descrizione |
|---------|-------------|
| `knowledge-space serve` | Avvia il server REST |
| `knowledge-space serve --host 0.0.0.0 --port 8000` | Configura host/port |
| `knowledge-space mcp` | Avvia il server MCP in modalità stdio |
| `knowledge-space mcp --sse --port 8001` | Avvia MCP in modalità SSE |
| `knowledge-space workspace add /path/to/ws` | Aggiunge un workspace |
| `knowledge-space workspace list` | Elenca workspace |
| `knowledge-space workspace remove NAME` | Rimuove workspace |
| `knowledge-space config show` | Mostra configurazione |
| `knowledge-space config set hf_key TOKEN` | Imposta chiave HuggingFace |

## Esempio

```python
import typer
from knowledge_space.api.app import create_app
from knowledge_space.config import AppConfig

app = typer.Typer()

@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, config: str = None):
    cfg = AppConfig.load(config_path=config)
    api = create_app(cfg)
    import uvicorn
    uvicorn.run(api, host=host, port=port)

@app.command()
def mcp(sse: bool = False, port: int = 8001):
    from mcp_server.server import run
    run(transport="sse" if sse else "stdio", port=port)

@app.command()
def workspace_add(path: str):
    cfg = AppConfig.load()
    service = cfg.workspace_service()
    service.add(path)
    typer.echo(f"Workspace aggiunto: {path}")

if __name__ == "__main__":
    app()
```
