"""Interface de linha de comando do Isoterma."""

from typing import Annotated

import typer

from isoterma import __version__

app = typer.Typer(
    name="isoterma",
    help="Inteligência térmica para data centers: veja, entenda e pergunte.",
    no_args_is_help=True,
)


def _mostrar_versao(valor: bool) -> None:
    if valor:
        typer.echo(f"isoterma {__version__}")
        raise typer.Exit


@app.callback()
def principal(
    versao: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Mostra a versão e sai.",
            callback=_mostrar_versao,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Inteligência térmica para data centers: veja, entenda e pergunte."""


@app.command()
def info() -> None:
    """Mostra as versões do Isoterma e das engines de dados instaladas."""
    import duckdb
    import pandas
    import polars

    typer.echo(f"isoterma {__version__}")
    typer.echo(f"duckdb   {duckdb.__version__}")
    typer.echo(f"polars   {polars.__version__}")
    typer.echo(f"pandas   {pandas.__version__}")
