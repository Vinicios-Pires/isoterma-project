"""Execução de SQL vindo de fora (de uma pessoa ou de uma IA) com segurança.

Três barreiras, da mais barata para a mais forte:

1. o comando precisa ser um único SELECT, checado pelo parser do próprio DuckDB;
2. a conexão é aberta em modo seguro (só lê a pasta da simulação, sem rede, configuração travada);
3. cada consulta tem teto de linhas e de tempo.
"""

import threading
import time
from dataclasses import dataclass
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.compute as pc


class ConsultaRecusada(ValueError):
    """O SQL não é permitido (não é um único SELECT)."""


class ConsultaInvalida(ValueError):
    """O DuckDB não conseguiu executar o SQL. A mensagem diz o porquê."""


class ConsultaExpirou(TimeoutError):
    """A consulta passou do tempo máximo e foi cancelada."""


@dataclass(frozen=True)
class ResultadoConsulta:
    sql: str
    tabela: pa.Table
    truncado: bool
    segundos: float

    @property
    def colunas(self) -> list[str]:
        return self.tabela.column_names

    def linhas(self) -> list[dict[str, Any]]:
        return self.tabela.to_pylist()


def validar(sql: str) -> str:
    """Devolve o SQL se for exatamente um SELECT; senão, levanta ConsultaRecusada."""
    try:
        comandos = duckdb.extract_statements(sql)
    except duckdb.Error as erro:
        raise ConsultaInvalida(str(erro)) from erro
    if len(comandos) != 1:
        raise ConsultaRecusada(f"Envie exatamente um comando SQL (recebidos: {len(comandos)})")
    tipo = comandos[0].type
    if tipo != duckdb.StatementType.SELECT:
        raise ConsultaRecusada(f"Só consultas SELECT são permitidas (recebido: {tipo.name})")
    return sql


def arredondar_float32(tabela: pa.Table, casas: int = 2) -> pa.Table:
    """Converte colunas float32 para float64 arredondado.

    As leituras são float32, e 20,8 vira 20,799999237… quando passa para o Python.
    Duas casas bastam: as temperaturas têm uma e a potência tem duas.
    """
    for i, campo in enumerate(tabela.schema):
        if pa.types.is_float32(campo.type):
            em_double = pc.cast(tabela.column(i), pa.float64())
            coluna = pc.round(em_double, casas)  # pyright: ignore[reportAttributeAccessIssue]
            tabela = tabela.set_column(i, campo.name, coluna)
    return tabela


def executar(
    conexao: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    limite: int = 1_000,
    tempo_max_s: float = 30.0,
) -> ResultadoConsulta:
    """Executa um SELECT validado, com teto de linhas e de tempo.

    ``conexao`` deve ter sido aberta com ``conectar(..., seguro=True)``.
    """
    validar(sql)
    cursor = conexao.cursor()
    cronometro = threading.Timer(tempo_max_s, cursor.interrupt)
    relogio = time.perf_counter()
    cronometro.start()
    try:
        tabela = cursor.sql(sql).limit(limite + 1).to_arrow_table()
    except duckdb.InterruptException as erro:
        raise ConsultaExpirou(f"A consulta passou de {tempo_max_s:g} s e foi cancelada") from erro
    except duckdb.Error as erro:
        raise ConsultaInvalida(str(erro)) from erro
    finally:
        cronometro.cancel()
        cursor.close()
    segundos = time.perf_counter() - relogio

    truncado = tabela.num_rows > limite
    return ResultadoConsulta(
        sql=sql,
        tabela=arredondar_float32(tabela.slice(0, limite)),
        truncado=truncado,
        segundos=segundos,
    )
