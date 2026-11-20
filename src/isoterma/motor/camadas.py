"""Camada ouro: agregados de cada sensor por minuto e por hora.

Os agregados guardam mínimo, máximo, média e contagem de cada sensor em cada intervalo. Eles
deixam as consultas de janelas longas centenas de vezes menores, e são os dados que a demo no
navegador vai baixar.
"""

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from isoterma.dados import GRANULARIDADES, _caminho, conectar, ler_manifesto, pasta_agregados


@dataclass(frozen=True)
class Camada:
    """Uma fonte de leituras: a tabela bruta ou um dos agregados."""

    tabela: str
    granularidade_s: int
    coluna_ts: str
    minimo: str
    maximo: str
    media: str
    leituras: str
    total: str
    nulos: str

    @property
    def bruta(self) -> bool:
        return self.tabela == "leituras"


def camada_bruta(intervalo_s: int) -> Camada:
    return Camada(
        tabela="leituras",
        granularidade_s=intervalo_s,
        coluna_ts="ts",
        minimo="min(f.valor)",
        maximo="max(f.valor)",
        media="avg(f.valor)",
        leituras="count(f.valor)",
        total="count(*)",
        nulos="count(*) - count(f.valor)",
    )


def camada_agregada(granularidade: str) -> Camada:
    return Camada(
        tabela=f"agregados_{granularidade}",
        granularidade_s=GRANULARIDADES[granularidade],
        coluna_ts="inicio",
        minimo="min(f.minimo)",
        maximo="max(f.maximo)",
        # Média ponderada pelo número de leituras: média das médias estaria errada.
        media="sum(f.media * f.leituras) / nullif(sum(f.leituras), 0)",
        leituras="sum(f.leituras)",
        total="sum(f.leituras + f.nulos)",
        nulos="sum(f.nulos)",
    )


ESQUEMA_AGREGADOS: dict[str, str] = {
    "_descricao": (
        "Agregados de cada sensor por intervalo de tempo. Use para janelas longas: são muito "
        "menores que leituras. Para médias de vários intervalos, pondere por leituras."
    ),
    "sensor_id": "Sensor agregado (chave para sensores.sensor_id)",
    "inicio": "Início do intervalo, em UTC",
    "minimo": "Menor leitura do intervalo",
    "maximo": "Maior leitura do intervalo",
    "media": "Média das leituras do intervalo",
    "leituras": "Quantidade de leituras válidas",
    "nulos": "Quantidade de leituras ausentes",
}


def granularidades_possiveis(intervalo_s: int) -> list[str]:
    """Só faz sentido agregar em intervalos maiores que o das leituras."""
    return [nome for nome, segundos in GRANULARIDADES.items() if segundos > intervalo_s]


def agregar(diretorio: Path, granularidades: Iterable[str] | None = None) -> dict[str, int]:
    """Gera (ou refaz) os agregados e devolve quantas linhas cada um ficou."""
    intervalo = ler_manifesto(diretorio)["periodo"]["intervalo_s"]
    possiveis = granularidades_possiveis(intervalo)
    escolhidas = possiveis if granularidades is None else list(granularidades)
    for nome in escolhidas:
        if nome not in GRANULARIDADES:
            raise ValueError(
                f"Granularidade {nome!r} desconhecida. Use: {', '.join(GRANULARIDADES)}"
            )
        if nome not in possiveis:
            raise ValueError(
                f"As leituras já são a cada {intervalo} s; agregar por {nome} não reduz nada"
            )

    conexao = conectar(diretorio)
    linhas: dict[str, int] = {}
    # Da mais fina para a mais grossa: cada agregado sai do anterior, que é muito menor que as
    # leituras (a hora sai dos minutos, 60 vezes menos linhas).
    fonte = "leituras AS f", camada_bruta(intervalo)
    for nome in sorted(escolhidas, key=GRANULARIDADES.__getitem__):
        pasta = pasta_agregados(diretorio, nome)
        if pasta.exists():
            shutil.rmtree(pasta)
        pasta.mkdir(parents=True)
        tabela, camada = fonte
        # A data da partição sai do resultado agrupado: calcular o bucket de novo dentro do
        # GROUP BY, linha a linha, deixava a agregação de 1 bilhão de leituras 2x mais lenta.
        consulta = f"""
            SELECT *, strftime(inicio, '%Y-%m-%d') AS data
            FROM (
                SELECT
                    f.sensor_id,
                    time_bucket(
                        INTERVAL '{GRANULARIDADES[nome]} seconds', f.{camada.coluna_ts}
                    ) AS inicio,
                    {camada.minimo} AS minimo,
                    {camada.maximo} AS maximo,
                    {camada.media} AS media,
                    ({camada.leituras})::INTEGER AS leituras,
                    ({camada.nulos})::INTEGER AS nulos
                FROM {tabela}
                GROUP BY ALL
            )
        """
        conexao.execute(
            f"COPY ({consulta}) TO {_caminho(pasta)} "
            "(FORMAT parquet, COMPRESSION zstd, PARTITION_BY (data), OVERWRITE_OR_IGNORE)"
        )
        arquivos = _caminho(pasta / "*" / "*.parquet")
        resultado = conexao.execute(f"SELECT count(*) FROM read_parquet({arquivos})").fetchone()
        linhas[nome] = int(resultado[0]) if resultado else 0
        fonte = f"read_parquet({arquivos}, hive_partitioning = false) AS f", camada_agregada(nome)
    return linhas
