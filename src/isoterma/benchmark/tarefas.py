"""As tarefas do benchmark, o formato canônico dos resultados e a validação cruzada."""

from dataclasses import dataclass
from enum import StrEnum

import pyarrow as pa
import pyarrow.compute as pc


class Tarefa(StrEnum):
    BRC = "1brc"
    """O desafio original: mínimo, média e máximo de cada sensor de temperatura."""

    REALISTA = "realista"
    """Por rack e por hora: média da entrada, máximo da saída e leituras fora da faixa ASHRAE.

    Exige junção com o cadastro de sensores e janela de tempo, então só roda sobre Parquet.
    """


class Formato(StrEnum):
    TXT = "txt"
    """O formato do 1BRC: ``codigo;valor`` por linha, só temperaturas."""

    PARQUET = "parquet"
    """As leituras gravadas pelo simulador."""


DESCRICAO: dict[Tarefa, str] = {
    Tarefa.BRC: "mínimo, média e máximo de cada sensor de temperatura",
    Tarefa.REALISTA: (
        "por rack e por hora: média da entrada, máximo da saída e leituras fora de 18–27 °C"
    ),
}


@dataclass(frozen=True)
class Coluna:
    nome: str
    casas: int | None = None  # arredondamento; None para chaves e contagens
    tolerancia: float = 0.0  # diferença aceita na comparação com a referência


ESQUEMA: dict[Tarefa, tuple[Coluna, ...]] = {
    Tarefa.BRC: (
        Coluna("codigo"),
        Coluna("minimo", casas=1),
        # Somas em ordens diferentes podem mudar o arredondamento de uma média como x,x5.
        Coluna("media", casas=1, tolerancia=0.1 + 1e-9),
        Coluna("maximo", casas=1),
    ),
    Tarefa.REALISTA: (
        Coluna("rack_id"),
        Coluna("hora"),
        Coluna("media_entrada_c", casas=2, tolerancia=0.01 + 1e-9),
        Coluna("maximo_saida_c", casas=1),
        Coluna("leituras_fora"),
    ),
}
CHAVES: dict[Tarefa, tuple[str, ...]] = {
    Tarefa.BRC: ("codigo",),
    Tarefa.REALISTA: ("rack_id", "hora"),
}
FAIXA_C = (18.0, 27.0)


def normalizar(tarefa: Tarefa, tabela: pa.Table) -> pa.Table:
    """Coloca o resultado de qualquer engine no mesmo formato: tipos, arredondamento e ordem."""
    colunas: dict[str, pa.Array | pa.ChunkedArray] = {}
    for coluna in ESQUEMA[tarefa]:
        valores = tabela.column(coluna.nome)
        if pa.types.is_timestamp(valores.type):
            # Compara instantes como segundos desde 1970, sem depender de fuso.
            valores = pc.cast(pc.cast(valores, pa.timestamp("s", "UTC")), pa.int64())
        elif coluna.casas is not None:
            em_double = pc.cast(valores, pa.float64())
            valores = pc.round(em_double, coluna.casas)  # pyright: ignore[reportAttributeAccessIssue]
        elif pa.types.is_integer(valores.type):
            valores = pc.cast(valores, pa.int64())
        else:
            valores = pc.cast(valores, pa.string())
        colunas[coluna.nome] = valores
    normalizada = pa.table(colunas)
    return normalizada.sort_by([(chave, "ascending") for chave in CHAVES[tarefa]])


@dataclass(frozen=True)
class Validacao:
    valido: bool
    motivo: str = ""


def comparar(tarefa: Tarefa, resultado: pa.Table, referencia: pa.Table) -> Validacao:
    """Confere um resultado normalizado contra a referência, coluna a coluna."""
    if resultado.num_rows != referencia.num_rows:
        return Validacao(False, f"{resultado.num_rows} linhas, esperado {referencia.num_rows}")
    for coluna in ESQUEMA[tarefa]:
        obtido = resultado.column(coluna.nome).to_pylist()
        esperado = referencia.column(coluna.nome).to_pylist()
        for i, (a, b) in enumerate(zip(obtido, esperado, strict=True)):
            if a == b:
                continue
            # A tolerância vem primeiro: colunas sem ela (chaves de texto) nunca são subtraídas.
            if coluna.tolerancia and None not in (a, b) and abs(a - b) <= coluna.tolerancia:
                continue
            chave = ", ".join(str(referencia.column(c)[i].as_py()) for c in CHAVES[tarefa])
            return Validacao(False, f"{coluna.nome} de {chave}: {a!r}, esperado {b!r}")
    return Validacao(True)
