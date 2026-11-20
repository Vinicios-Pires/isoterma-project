"""Interface de linha de comando do Isoterma."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, NoReturn

import typer

from isoterma import __version__
from isoterma.simulador.config import Preset
from isoterma.terminal import numero, tamanho

if TYPE_CHECKING:
    from isoterma.motor import Hall

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
        f"Simulando '{cfg.nome}': {numero(cfg.total_linhas)} leituras de "
        f"{numero(cfg.total_sensores)} sensores (seed {cfg.seed})"
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
    typer.echo(f"  linhas      {numero(resultado.linhas)}")
    typer.echo(
        f"  sensores    {numero(resultado.sensores)} "
        f"({resultado.racks} racks, {resultado.cracs} CRACs)"
    )
    typer.echo(f"  incidentes  {resultado.incidentes} (gabarito em incidentes.parquet)")
    typer.echo(f"  em disco    {tamanho(resultado.bytes_em_disco)}")
    typer.echo(
        f"  tempo       {numero(resultado.segundos, 1)} s "
        f"({numero(milhoes_por_s, 1)} milhões de linhas/s, "
        f"{resultado.processos} processo{'s' if resultado.processos > 1 else ''})"
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
    typer.echo(f"{numero(linhas)} linhas exportadas para {destino}")


# --- motor ----------------------------------------------------------------------------------

FORMATOS_DATA = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
AJUDA_DATA = "Horário local do hall, ex.: 2026-11-07T02:30."
DiretorioSimulacao = Annotated[
    Path, typer.Argument(help="Pasta de uma simulação.", exists=True, file_okay=False)
]
Data = Annotated[datetime | None, typer.Option(formats=FORMATOS_DATA, help=AJUDA_DATA)]


class TipoMapa(StrEnum):
    TEMP_ENTRADA = "temp_entrada"
    TEMP_SAIDA = "temp_saida"
    POTENCIA_KW = "potencia_kw"


class Altura(StrEnum):
    BASE = "base"
    MEIO = "meio"
    TOPO = "topo"


def _abrir(diretorio: Path) -> Hall:
    from isoterma.motor import Hall

    try:
        return Hall(diretorio)
    except FileNotFoundError as erro:
        typer.echo(str(erro), err=True)
        raise typer.Exit(1) from erro


def _falhar(erro: Exception) -> NoReturn:
    typer.echo(str(erro), err=True)
    raise typer.Exit(1) from erro


@app.command()
def agregar(
    diretorio: DiretorioSimulacao,
    granularidade: Annotated[
        list[str] | None,
        typer.Option(help="minuto e/ou hora. Padrão: todas as que reduzem os dados."),
    ] = None,
) -> None:
    """Gera os agregados por minuto e por hora (a camada ouro)."""
    from isoterma.motor import agregar as gerar_agregados

    try:
        linhas = gerar_agregados(diretorio, granularidade)
    except (FileNotFoundError, ValueError) as erro:
        _falhar(erro)
    if not linhas:
        typer.echo("Nada a agregar: as leituras já são de hora em hora ou mais espaçadas.")
    for nome, quantidade in linhas.items():
        typer.echo(f"agregados por {nome}: {numero(quantidade)} linhas")


@app.command()
def resumo(diretorio: DiretorioSimulacao, inicio: Data = None, fim: Data = None) -> None:
    """Visão geral do hall: volume de dados, temperaturas, potência e alertas."""
    with _abrir(diretorio) as hall:
        try:
            r = hall.resumo(inicio, fim)
        except ValueError as erro:
            _falhar(erro)
        local = hall.fuso
    typer.echo(
        f"Período     {r['inicio'].astimezone(local):%Y-%m-%d %H:%M} a "
        f"{r['fim'].astimezone(local):%Y-%m-%d %H:%M} ({local.key})"
    )
    typer.echo(
        f"Hall        {r['racks']} racks, {r['cracs']} CRACs, {numero(r['sensores'])} sensores"
    )
    typer.echo(
        f"Leituras    {numero(r['leituras'])} ({numero(r['leituras_nulas'])} ausentes)"
        f", fonte: {r['fonte']}"
    )
    if r["potencia_media_total_kw"] is not None:
        typer.echo(f"Potência    {numero(r['potencia_media_total_kw'], 1)} kW em média")
    for tipo, valores in r["por_tipo"].items():
        if tipo == "potencia_kw":
            continue
        typer.echo(
            f"{tipo:<20} mín {numero(valores['minimo'], 1):>6}  "
            f"média {numero(valores['media'], 1):>6}  máx {numero(valores['maximo'], 1):>6}"
        )
    typer.echo(
        f"Faixa ASHRAE  {r['racks_acima_da_faixa']} racks passaram de 27 °C, "
        f"{r['racks_abaixo_da_faixa']} ficaram abaixo de 18 °C"
    )


@app.command()
def mapa(
    diretorio: DiretorioSimulacao,
    instante: Data = None,
    tipo: Annotated[TipoMapa, typer.Option(help="O que desenhar.")] = TipoMapa.TEMP_ENTRADA,
    altura: Annotated[
        Altura | None, typer.Option(help="Só para temp_entrada. Padrão: a mais quente.")
    ] = None,
) -> None:
    """Desenha o mapa térmico do hall num instante (padrão: o fim da simulação)."""
    from isoterma.terminal import mapa_termico

    with _abrir(diretorio) as hall:
        try:
            tabela = hall.mapa_termico(instante, tipo=tipo.value, altura=altura)
        except ValueError as erro:
            _falhar(erro)
        momento = hall.em_utc(instante, hall.fim).astimezone(hall.fuso)
    typer.echo(f"{tipo.value} em {momento:%Y-%m-%d %H:%M} ({momento.tzname()})\n")
    for linha in mapa_termico(tabela, tipo.value):
        typer.echo(linha)
    if tipo is TipoMapa.TEMP_ENTRADA:
        racks = tabela.to_pylist()
        acima = sorted((r for r in racks if r["faixa"] == "acima"), key=lambda r: -r["valor"])
        abaixo = [r for r in racks if r["faixa"] == "abaixo"]
        typer.echo(f"\n{len(acima)} racks acima de 27 °C, {len(abaixo)} abaixo de 18 °C")
        if acima:
            destaque = ", ".join(f"{r['rack_id']} ({numero(r['valor'], 1)} °C)" for r in acima[:5])
            typer.echo(f"Mais quentes: {destaque}")


@app.command()
def consultar(
    diretorio: DiretorioSimulacao,
    sql: Annotated[str, typer.Argument(help="Um único SELECT.")],
    limite: Annotated[int, typer.Option(help="Máximo de linhas.", min=1)] = 50,
) -> None:
    """Executa um SELECT na simulação, em modo seguro (só leitura, com limites)."""
    from isoterma.motor import ConsultaExpirou, ConsultaInvalida, ConsultaRecusada
    from isoterma.terminal import tabela_texto

    with _abrir(diretorio) as hall:
        try:
            resultado = hall.consultar(sql, limite=limite)
        except (ConsultaRecusada, ConsultaInvalida, ConsultaExpirou) as erro:
            _falhar(erro)
        fuso = hall.fuso
    for linha in tabela_texto(resultado.tabela, fuso):
        typer.echo(linha)
    aviso = f" (limitado a {limite}; use --limite)" if resultado.truncado else ""
    typer.echo(
        f"\n{numero(resultado.tabela.num_rows)} linhas em {numero(resultado.segundos, 2)} s{aviso}"
    )
