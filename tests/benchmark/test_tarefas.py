from datetime import UTC, datetime

import pyarrow as pa
import pytest

from isoterma.benchmark.tarefas import Tarefa, comparar, normalizar


def _brc(medias: list[float], codigos: tuple[str, ...] = ("B", "A")) -> pa.Table:
    return pa.table(
        {
            "codigo": list(codigos),
            "minimo": pa.array([18.04, 19.0], pa.float32()),
            "media": medias,
            "maximo": [25.0, 26.0],
        }
    )


def test_normalizar_ordena_e_arredonda() -> None:
    tabela = normalizar(Tarefa.BRC, _brc([21.2345, 22.0]))

    assert tabela.column("codigo").to_pylist() == ["A", "B"]
    assert tabela.column("minimo").to_pylist() == [19.0, 18.0]
    assert tabela.column("media").to_pylist() == [22.0, 21.2]


def test_normalizar_converte_horas_para_segundos_utc() -> None:
    tabela = pa.table(
        {
            "rack_id": ["A-01"],
            "hora": pa.array([datetime(2026, 11, 1, 3, tzinfo=UTC)], pa.timestamp("us", "UTC")),
            "media_entrada_c": [20.123],
            "maximo_saida_c": [31.0],
            "leituras_fora": pa.array([2], pa.int32()),
        }
    )

    normalizada = normalizar(Tarefa.REALISTA, tabela)

    assert normalizada.column("hora").to_pylist() == [
        int(datetime(2026, 11, 1, 3, tzinfo=UTC).timestamp())
    ]
    assert normalizada.column("leituras_fora").type == pa.int64()


def test_comparar_aceita_diferenca_de_arredondamento_na_media() -> None:
    referencia = normalizar(Tarefa.BRC, _brc([21.2, 22.0]))
    resultado = normalizar(Tarefa.BRC, _brc([21.3, 22.0]))

    assert comparar(Tarefa.BRC, resultado, referencia).valido


@pytest.mark.parametrize(
    ("resultado", "motivo"),
    [
        (_brc([21.5, 22.0]), "media de B"),
        (_brc([21.2, 22.0], ("B", "C")), "codigo"),
        (_brc([21.2, 22.0]).slice(0, 1), "1 linhas, esperado 2"),
    ],
)
def test_comparar_aponta_a_diferenca(resultado: pa.Table, motivo: str) -> None:
    referencia = normalizar(Tarefa.BRC, _brc([21.2, 22.0]))

    validacao = comparar(Tarefa.BRC, normalizar(Tarefa.BRC, resultado), referencia)

    assert not validacao.valido
    assert motivo in validacao.motivo
