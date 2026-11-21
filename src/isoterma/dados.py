"""Acesso às simulações gravadas em disco, via DuckDB."""

import json
from pathlib import Path
from typing import Any

import duckdb

MANIFESTO = "manifesto.json"
TABELAS_DIMENSAO = ("sensores", "racks", "cracs", "incidentes")
# Camada ouro: agregados por sensor, com a granularidade em segundos.
GRANULARIDADES: dict[str, int] = {"minuto": 60, "hora": 3600}


def _literal(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


def _caminho(caminho: Path) -> str:
    return _literal(caminho.as_posix())


def pasta_agregados(diretorio: Path, granularidade: str) -> Path:
    return diretorio / "agregados" / granularidade


def ler_manifesto(diretorio: Path) -> dict[str, Any]:
    arquivo = diretorio / MANIFESTO
    if not arquivo.exists():
        raise FileNotFoundError(f"{diretorio} não contém uma simulação (falta {MANIFESTO})")
    return json.loads(arquivo.read_text(encoding="utf-8"))


def conectar(
    diretorio: Path, *, seguro: bool = False, com_gabarito: bool = True
) -> duckdb.DuckDBPyConnection:
    """Abre uma conexão em memória com uma view para cada tabela da simulação.

    Os horários são tratados em UTC. Com ``seguro=True``, a conexão só enxerga os arquivos
    desta simulação: outros arquivos, a rede e mudanças de configuração ficam bloqueados.
    Com ``com_gabarito=False``, a tabela ``incidentes`` não existe e o arquivo dela fica
    inacessível (em modo seguro, nem um ``read_parquet`` direto o alcança).
    """
    diretorio = diretorio.resolve()
    if not (diretorio / "leituras").is_dir():
        raise FileNotFoundError(f"{diretorio} não contém uma simulação (falta leituras/)")

    # O fuso vai na configuração do banco para valer também nos cursores, que não herdam
    # configurações de sessão (e já nascem sem barra de progresso).
    conexao = duckdb.connect(config={"TimeZone": "UTC"})
    conexao.execute("SET enable_progress_bar = false")

    def view(nome: str, arquivos: Path) -> None:
        conexao.execute(
            f"CREATE VIEW {nome} AS "
            f"SELECT * FROM read_parquet({_caminho(arquivos)}, hive_partitioning = false)"
        )

    view("leituras", diretorio / "leituras" / "*" / "*.parquet")
    tabelas = [t for t in TABELAS_DIMENSAO if com_gabarito or t != "incidentes"]
    for tabela in tabelas:
        view(tabela, diretorio / f"{tabela}.parquet")
    for granularidade in GRANULARIDADES:
        pasta = pasta_agregados(diretorio, granularidade)
        if pasta.is_dir():
            view(f"agregados_{granularidade}", pasta / "*" / "*.parquet")

    if seguro:
        if com_gabarito:
            pastas = [diretorio.as_posix() + "/"]
            arquivos: list[str] = []
        else:
            # Libera só o que as views usam: a pasta da simulação inteira incluiria o gabarito.
            pastas = [f"{diretorio.as_posix()}/{p}/" for p in ("leituras", "agregados")]
            arquivos = [(diretorio / f"{t}.parquet").as_posix() for t in tabelas]
        conexao.execute(f"SET allowed_directories = [{', '.join(map(_literal, pastas))}]")
        if arquivos:
            conexao.execute(f"SET allowed_paths = [{', '.join(map(_literal, arquivos))}]")
        conexao.execute("SET enable_external_access = false")
        conexao.execute("SET lock_configuration = true")
    return conexao


def exportar_1brc(diretorio: Path, destino: Path) -> int:
    """Exporta as temperaturas no formato do desafio original: ``codigo;valor`` por linha."""
    conexao = conectar(diretorio)
    consulta = """
        SELECT s.codigo, l.valor
        FROM leituras AS l
        JOIN sensores AS s USING (sensor_id)
        WHERE s.unidade = '°C' AND l.valor IS NOT NULL
    """
    linhas = conexao.execute(f"SELECT count(*) FROM ({consulta})").fetchone()
    conexao.execute(
        f"COPY ({consulta}) TO {_caminho(destino)} (FORMAT csv, DELIMITER ';', HEADER false)"
    )
    return int(linhas[0]) if linhas else 0
