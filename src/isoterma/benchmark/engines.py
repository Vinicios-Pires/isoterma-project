"""As implementações de cada tarefa em cada engine.

Cada função recebe a entrada e devolve uma tabela Arrow com as colunas da tarefa (ver
``tarefas.ESQUEMA``); a normalização e a comparação acontecem depois, fora do tempo medido.
Todas processam os dados em fluxo: nenhuma carrega o bilhão de linhas na memória de uma vez.
"""

import mmap
import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa

from isoterma.benchmark.tarefas import FAIXA_C, Formato, Tarefa

TRECHO_BYTES = 64 * 1024 * 1024
LINHAS_POR_LOTE_PANDAS = 5_000_000


@dataclass(frozen=True)
class Entrada:
    diretorio: Path  # pasta da simulação
    txt: Path  # exportação no formato do 1BRC

    @property
    def leituras(self) -> list[Path]:
        return sorted((self.diretorio / "leituras").glob("*/*.parquet"))

    @property
    def glob_leituras(self) -> str:
        return (self.diretorio / "leituras" / "*" / "*.parquet").as_posix()

    @property
    def sensores(self) -> Path:
        return self.diretorio / "sensores.parquet"


# --- Python puro --------------------------------------------------------------------------
# A técnica dos vencedores do 1BRC, sem bibliotecas: o arquivo é mapeado em memória (mmap),
# dividido em trechos que terminam em fim de linha, e cada processo agrega os seus trechos.


def _trechos(caminho: Path, tamanho: int = TRECHO_BYTES) -> list[tuple[int, int]]:
    total = caminho.stat().st_size
    trechos: list[tuple[int, int]] = []
    with (
        caminho.open("rb") as arquivo,
        mmap.mmap(arquivo.fileno(), 0, access=mmap.ACCESS_READ) as mm,
    ):
        inicio = 0
        while inicio < total:
            fim = mm.find(b"\n", min(inicio + tamanho, total - 1))
            fim = total if fim == -1 else fim + 1
            trechos.append((inicio, fim))
            inicio = fim
    return trechos


def _agregar_trecho(caminho: str, inicio: int, fim: int) -> dict[bytes, list[float]]:
    with (
        open(caminho, "rb") as arquivo,
        mmap.mmap(arquivo.fileno(), 0, access=mmap.ACCESS_READ) as mm,
    ):
        dados = mm[inicio:fim]
    estatisticas: dict[bytes, list[float]] = {}
    for linha in dados.split(b"\n"):
        if not linha:
            continue
        nome, _, texto = linha.rpartition(b";")
        valor = float(texto)
        atual = estatisticas.get(nome)
        if atual is None:
            estatisticas[nome] = [valor, valor, valor, 1]
        else:
            if valor < atual[0]:
                atual[0] = valor
            if valor > atual[1]:
                atual[1] = valor
            atual[2] += valor
            atual[3] += 1
    return estatisticas


def python_1brc_txt(entrada: Entrada) -> pa.Table:
    trechos = _trechos(entrada.txt)
    total: dict[bytes, list[float]] = {}
    with ProcessPoolExecutor(os.cpu_count()) as executor:
        parciais = executor.map(
            _agregar_trecho,
            [str(entrada.txt)] * len(trechos),
            [t[0] for t in trechos],
            [t[1] for t in trechos],
        )
        for parcial in parciais:
            for nome, (minimo, maximo, soma, n) in parcial.items():
                atual = total.get(nome)
                if atual is None:
                    total[nome] = [minimo, maximo, soma, n]
                else:
                    atual[0] = min(atual[0], minimo)
                    atual[1] = max(atual[1], maximo)
                    atual[2] += soma
                    atual[3] += n
    nomes = sorted(total)
    return pa.table(
        {
            "codigo": [n.decode() for n in nomes],
            "minimo": [total[n][0] for n in nomes],
            "media": [total[n][2] / total[n][3] for n in nomes],
            "maximo": [total[n][1] for n in nomes],
        }
    )


# --- pandas -------------------------------------------------------------------------------
# Em lotes: cada lote vira estatísticas parciais (min, máx, soma, contagem), combinadas no fim.
# É a forma correta de fazer média em partes: soma e contagem, nunca média das médias.


def _combinar_pandas(parciais: list, chaves: list[str]):
    import pandas as pd

    juntos = pd.concat(parciais)
    return juntos.groupby(chaves, observed=True).agg(
        minimo=("minimo", "min"), maximo=("maximo", "max"), soma=("soma", "sum"), n=("n", "sum")
    )


def pandas_1brc_txt(entrada: Entrada) -> pa.Table:
    import pandas as pd

    parciais = []
    with pd.read_csv(
        entrada.txt,
        sep=";",
        header=None,
        names=["codigo", "valor"],
        dtype={"codigo": "category", "valor": "float64"},
        chunksize=LINHAS_POR_LOTE_PANDAS,
    ) as leitor:
        for lote in leitor:
            parciais.append(
                lote.groupby("codigo", observed=True)["valor"]
                .agg(minimo="min", maximo="max", soma="sum", n="count")
                .reset_index()
                .astype({"codigo": "string"})
            )
    total = _combinar_pandas(parciais, ["codigo"]).reset_index()
    total["media"] = total["soma"] / total["n"]
    return pa.Table.from_pandas(
        total[["codigo", "minimo", "media", "maximo"]], preserve_index=False
    )


def pandas_1brc_parquet(entrada: Entrada) -> pa.Table:
    import pandas as pd

    sensores = pd.read_parquet(entrada.sensores, columns=["sensor_id", "codigo", "unidade"])
    parciais = []
    for arquivo in entrada.leituras:
        lote = pd.read_parquet(arquivo, columns=["sensor_id", "valor"])
        parciais.append(
            lote.groupby("sensor_id")["valor"]
            .agg(minimo="min", maximo="max", soma="sum", n="count")
            .reset_index()
        )
    total = _combinar_pandas(parciais, ["sensor_id"]).reset_index()
    total = total.merge(sensores[sensores["unidade"] == "°C"], on="sensor_id")
    total = total[total["n"] > 0]
    total["media"] = total["soma"] / total["n"]
    return pa.Table.from_pandas(
        total[["codigo", "minimo", "media", "maximo"]], preserve_index=False
    )


def pandas_realista_parquet(entrada: Entrada) -> pa.Table:
    import pandas as pd

    sensores = pd.read_parquet(entrada.sensores, columns=["sensor_id", "rack_id", "tipo"])
    sensores = sensores[sensores["tipo"].isin(["temp_entrada", "temp_saida"])]
    minimo_c, maximo_c = FAIXA_C
    parciais = []
    for arquivo in entrada.leituras:
        lote = pd.read_parquet(arquivo).merge(sensores, on="sensor_id")
        lote["hora"] = lote["ts"].dt.floor("h")
        entrada_ = lote[lote["tipo"] == "temp_entrada"]
        fora = (entrada_["valor"] < minimo_c) | (entrada_["valor"] > maximo_c)
        por_hora = (
            entrada_.assign(fora=fora)
            .groupby(["rack_id", "hora"])
            .agg(soma=("valor", "sum"), n=("valor", "count"), fora=("fora", "sum"))
        )
        saida = (
            lote[lote["tipo"] == "temp_saida"]
            .groupby(["rack_id", "hora"])
            .agg(maximo_saida_c=("valor", "max"))
        )
        parciais.append(por_hora.join(saida, how="outer"))
    total = (
        pd.concat(parciais)
        .groupby(level=["rack_id", "hora"])
        .agg(
            soma=("soma", "sum"),
            n=("n", "sum"),
            fora=("fora", "sum"),
            maximo=("maximo_saida_c", "max"),
        )
        .reset_index()
    )
    return pa.table(
        {
            "rack_id": total["rack_id"],
            "hora": total["hora"],
            "media_entrada_c": total["soma"] / total["n"],
            "maximo_saida_c": total["maximo"],
            "leituras_fora": total["fora"].astype("int64"),
        }
    )


# --- Polars -------------------------------------------------------------------------------
# Lazy + streaming: a consulta inteira é planejada e executada em fluxo pelo Polars 2.


def polars_1brc_txt(entrada: Entrada) -> pa.Table:
    import polars as pl

    return (
        pl.scan_csv(
            entrada.txt,
            separator=";",
            has_header=False,
            schema={"codigo": pl.String, "valor": pl.Float64},
        )
        .group_by("codigo")
        .agg(
            minimo=pl.col("valor").min(),
            media=pl.col("valor").mean(),
            maximo=pl.col("valor").max(),
        )
        .collect(engine="streaming")
        .to_arrow()
    )


def polars_1brc_parquet(entrada: Entrada) -> pa.Table:
    import polars as pl

    sensores = pl.scan_parquet(entrada.sensores).filter(pl.col("unidade") == "°C")
    return (
        pl.scan_parquet(entrada.glob_leituras)
        .join(sensores.select("sensor_id", "codigo"), on="sensor_id")
        .group_by("codigo")
        .agg(
            minimo=pl.col("valor").min(),
            media=pl.col("valor").mean(),
            maximo=pl.col("valor").max(),
        )
        .collect(engine="streaming")
        .to_arrow()
    )


def polars_realista_parquet(entrada: Entrada) -> pa.Table:
    import polars as pl

    minimo_c, maximo_c = FAIXA_C
    sensores = pl.scan_parquet(entrada.sensores).select("sensor_id", "rack_id", "tipo")
    valor = pl.col("valor")
    na_entrada = pl.col("tipo") == "temp_entrada"
    return (
        pl.scan_parquet(entrada.glob_leituras)
        .join(sensores.filter(pl.col("tipo").is_in(["temp_entrada", "temp_saida"])), on="sensor_id")
        .with_columns(hora=pl.col("ts").dt.truncate("1h"))
        .group_by("rack_id", "hora")
        .agg(
            media_entrada_c=valor.filter(na_entrada).mean(),
            maximo_saida_c=valor.filter(pl.col("tipo") == "temp_saida").max(),
            leituras_fora=(na_entrada & ((valor < minimo_c) | (valor > maximo_c))).sum(),
        )
        .collect(engine="streaming")
        .to_arrow()
    )


# --- DuckDB -------------------------------------------------------------------------------


def _duckdb(sql: str) -> pa.Table:
    import duckdb

    with duckdb.connect(config={"TimeZone": "UTC"}) as conexao:
        conexao.execute("SET enable_progress_bar = false")
        return conexao.sql(sql).to_arrow_table()


def _texto(caminho: Path | str) -> str:
    return "'" + str(caminho).replace("\\", "/").replace("'", "''") + "'"


def duckdb_1brc_txt(entrada: Entrada) -> pa.Table:
    return _duckdb(
        f"""
        SELECT codigo, min(valor) AS minimo, avg(valor) AS media, max(valor) AS maximo
        FROM read_csv({_texto(entrada.txt)}, delim = ';', header = false,
                      columns = {{'codigo': 'VARCHAR', 'valor': 'DOUBLE'}})
        GROUP BY codigo
        """
    )


def duckdb_1brc_parquet(entrada: Entrada) -> pa.Table:
    return _duckdb(
        f"""
        SELECT s.codigo, min(l.valor) AS minimo, avg(l.valor) AS media, max(l.valor) AS maximo
        FROM read_parquet({_texto(entrada.glob_leituras)}) AS l
        JOIN read_parquet({_texto(entrada.sensores)}) AS s USING (sensor_id)
        WHERE s.unidade = '°C'
        GROUP BY s.codigo
        HAVING count(l.valor) > 0
        """
    )


def duckdb_realista_parquet(entrada: Entrada) -> pa.Table:
    minimo_c, maximo_c = FAIXA_C
    return _duckdb(
        f"""
        SELECT
            s.rack_id,
            time_bucket(INTERVAL 1 HOUR, l.ts) AS hora,
            avg(l.valor) FILTER (s.tipo = 'temp_entrada') AS media_entrada_c,
            max(l.valor) FILTER (s.tipo = 'temp_saida') AS maximo_saida_c,
            count(*) FILTER (
                s.tipo = 'temp_entrada' AND (l.valor < {minimo_c} OR l.valor > {maximo_c})
            ) AS leituras_fora
        FROM read_parquet({_texto(entrada.glob_leituras)}) AS l
        JOIN read_parquet({_texto(entrada.sensores)}) AS s USING (sensor_id)
        WHERE s.tipo IN ('temp_entrada', 'temp_saida')
        GROUP BY ALL
        """
    )


Implementacao = Callable[[Entrada], pa.Table]

ENGINES: tuple[str, ...] = ("python", "pandas", "polars", "duckdb")
IMPLEMENTACOES: dict[tuple[Tarefa, Formato, str], Implementacao] = {
    (Tarefa.BRC, Formato.TXT, "python"): python_1brc_txt,
    (Tarefa.BRC, Formato.TXT, "pandas"): pandas_1brc_txt,
    (Tarefa.BRC, Formato.TXT, "polars"): polars_1brc_txt,
    (Tarefa.BRC, Formato.TXT, "duckdb"): duckdb_1brc_txt,
    (Tarefa.BRC, Formato.PARQUET, "pandas"): pandas_1brc_parquet,
    (Tarefa.BRC, Formato.PARQUET, "polars"): polars_1brc_parquet,
    (Tarefa.BRC, Formato.PARQUET, "duckdb"): duckdb_1brc_parquet,
    (Tarefa.REALISTA, Formato.PARQUET, "pandas"): pandas_realista_parquet,
    (Tarefa.REALISTA, Formato.PARQUET, "polars"): polars_realista_parquet,
    (Tarefa.REALISTA, Formato.PARQUET, "duckdb"): duckdb_realista_parquet,
}
REFERENCIA: dict[Tarefa, tuple[Formato, str]] = {
    Tarefa.BRC: (Formato.PARQUET, "duckdb"),
    Tarefa.REALISTA: (Formato.PARQUET, "duckdb"),
}
