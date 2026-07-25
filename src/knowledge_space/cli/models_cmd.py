"""Comandi models.

``ks models list`` — elenca modelli embedding
``ks models info <name>`` — dettaglio modello
"""

from __future__ import annotations

from typing import Optional

import typer

from knowledge_base.strategies import embedding_registry

from knowledge_space.cli.common import output_json

app = typer.Typer(help="Gestione modelli di embedding.")


@app.command("list")
def list_models(
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Elenca i modelli di embedding disponibili."""
    models = []
    for name in embedding_registry.list_names():
        factory = embedding_registry.get(name)
        # Crea un'istanza temporanea per leggere i metadati
        try:
            instance = factory()
            md = instance.metadata
            models.append({
                "name": md.model_name,
                "languages": md.languages,
                "dim": md.dim,
                "max_context_tokens": md.max_context_tokens,
                "license": md.license,
                "requires_api": md.requires_api,
            })
        except Exception:
            models.append({"name": name, "error": "non istanziabile"})

    if json_output:
        output_json(models)
    else:
        if not models:
            typer.echo("Nessun modello registrato.")
            return
        typer.echo(f"Modelli disponibili ({len(models)}):\n")
        for m in models:
            if "error" in m:
                typer.echo(f"  {m['name']} — {m['error']}")
            else:
                langs = ", ".join(m["languages"])
                api = "API" if m["requires_api"] else "locale"
                typer.echo(
                    f"  {m['name']}\n"
                    f"    Lingue: {langs} | Dim: {m['dim']} | "
                    f"Max ctx: {m['max_context_tokens']} | {api}\n"
                    f"    Licenza: {m['license']}"
                )


@app.command()
def info(
    name: str = typer.Argument(help="Nome del modello."),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Output dettagliato."),
) -> None:
    """Mostra dettagli di un modello di embedding."""
    if not embedding_registry.contains(name):
        typer.echo(f"Modello non trovato: {name}", err=True)
        typer.echo(f"Modelli disponibili: {', '.join(embedding_registry.list_names())}")
        raise typer.Exit(1)

    factory = embedding_registry.get(name)
    try:
        instance = factory()
        md = instance.metadata
        model_info = {
            "name": md.model_name,
            "languages": md.languages,
            "dim": md.dim,
            "max_context_tokens": md.max_context_tokens,
            "license": md.license,
            "requires_api": md.requires_api,
        }
    except Exception as exc:
        typer.echo(f"Errore nel caricamento del modello: {exc}", err=True)
        raise typer.Exit(1)

    if json_output:
        output_json(model_info)
    else:
        typer.echo(f"Modello: {model_info['name']}")
        typer.echo(f"  Lingue: {', '.join(model_info['languages'])}")
        typer.echo(f"  Dimensione: {model_info['dim']}")
        typer.echo(f"  Max contesto: {model_info['max_context_tokens']} token")
        typer.echo(f"  Licenza: {model_info['license']}")
        typer.echo(f"  Tipo: {'API remota' if model_info['requires_api'] else 'Locale'}")
