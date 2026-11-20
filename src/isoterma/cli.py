"""Interface de linha de comando do Isoterma."""

from pathlib import Path
from typing import Annotated

import typer

from isoterma import __version__
from isoterma.simulador.config import Preset

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


def _numero(n: float, casas: int = 0) -> str:
    """Formata no padrão brasileiro: 1.234.567,8."""
    return f"{n:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _tamanho(n_bytes: int) -> str:
    valor = float(n_bytes)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{_numero(valor, 1)} {unidade}"
        valor /= 1024
    raise AssertionError("inalcançável")


@app.command()
def simular(
    escala: Annotated[
        Preset, typer.Option("--preset", "-p", help="Escala pronta da simulação.")
    ] = Preset.TESTE,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Arquivo TOML com um hall próprio. Substitui o preset.",
            exists=True,
            dir_okay=False,
        ),
    ] = None,
    seed: Annotated[int | None, typer.Option(help="Semente aleatória.", min=0)] = None,
    saida: Annotated[
        Path | None, typer.Option("--saida", "-o", help="Pasta de destino (padrão: data/<nome>).")
    ] = None,
    processos: Annotated[
        int | None, typer.Option(help="Processos em paralelo (padrão: todos os núcleos).", min=1)
    ] = None,
    sobrescrever: Annotated[
        bool, typer.Option(help="Apaga uma simulação anterior na mesma pasta.")
    ] = False,
) -> None:
    """Gera a telemetria de um data hall simulado, com incidentes injetados."""
    from pydantic import ValidationError

    from isoterma import simulador

    try:
        cfg = simulador.carregar_config(config) if config else simulador.preset(escala)
    except ValidationError as erro:
        typer.echo(f"Configuração inválida:\n{erro}", err=True)
        raise typer.Exit(1) from erro
    if seed is not None:
        cfg = cfg.model_copy(update={"seed": seed})
    destino = saida or Path("data") / cfg.nome

    typer.echo(
        f"Simulando '{cfg.nome}': {_numero(cfg.total_linhas)} leituras de "
        f"{_numero(cfg.total_sensores)} sensores (seed {cfg.seed})"
    )
    try:
        with typer.progressbar(length=cfg.total_linhas, label="Gerando") as barra:
            resultado = simulador.simular(
                cfg, destino, processos=processos, sobrescrever=sobrescrever, progresso=barra.update
            )
    except (FileExistsError, ValueError) as erro:
        typer.echo(str(erro), err=True)
        raise typer.Exit(1) from erro

    milhoes_por_s = resultado.linhas_por_segundo / 1e6
    typer.echo(f"\nSimulação gravada em {resultado.diretorio}")
    typer.echo(f"  linhas      {_numero(resultado.linhas)}")
    typer.echo(
        f"  sensores    {_numero(resultado.sensores)} "
        f"({resultado.racks} racks, {resultado.cracs} CRACs)"
    )
    typer.echo(f"  incidentes  {resultado.incidentes} (gabarito em incidentes.parquet)")
    typer.echo(f"  em disco    {_tamanho(resultado.bytes_em_disco)}")
    typer.echo(
        f"  tempo       {_numero(resultado.segundos, 1)} s "
        f"({_numero(milhoes_por_s, 1)} milhões de linhas/s, {resultado.processos} processos)"
    )


@app.command("exportar-1brc")
def exportar_1brc(
    diretorio: Annotated[
        Path, typer.Argument(help="Pasta de uma simulação.", exists=True, file_okay=False)
    ],
    destino: Annotated[Path, typer.Option("--destino", "-d", help="Arquivo de saída.")] = Path(
        "medicoes.txt"
    ),
) -> None:
    """Exporta as temperaturas no formato do 1BRC original (codigo;valor)."""
    from isoterma.dados import exportar_1brc as exportar

    linhas = exportar(diretorio, destino)
    typer.echo(f"{_numero(linhas)} linhas exportadas para {destino}")
