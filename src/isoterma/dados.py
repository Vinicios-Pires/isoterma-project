"""Acesso às simulações gravadas em disco, via DuckDB."""

from pathlib import Path

import duckdb

TABELAS_DIMENSAO = ("sensores", "racks", "cracs", "incidentes")


def _literal(caminho: Path) -> str:
    return "'" + caminho.as_posix().replace("'", "''") + "'"


def conectar(diretorio: Path) -> duckdb.DuckDBPyConnection:
    """Abre uma conexão em memória com uma view para cada tabela da simulação."""
    if not (diretorio / "leituras").is_dir():
        raise FileNotFoundError(f"{diretorio} não contém uma simulação (falta leituras/)")
    conexao = duckdb.connect()
    conexao.execute("SET enable_progress_bar = false")
    leituras = _literal(diretorio / "leituras" / "*" / "*.parquet")
    conexao.execute(f"CREATE VIEW leituras AS SELECT * FROM read_parquet({leituras})")
    for tabela in TABELAS_DIMENSAO:
        arquivo = _literal(diretorio / f"{tabela}.parquet")
        conexao.execute(f"CREATE VIEW {tabela} AS SELECT * FROM read_parquet({arquivo})")
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
        f"COPY ({consulta}) TO {_literal(destino)} (FORMAT csv, DELIMITER ';', HEADER false)"
    )
    return int(linhas[0]) if linhas else 0
