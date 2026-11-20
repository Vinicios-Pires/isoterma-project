"""Todas as engines precisam chegar ao mesmo resultado."""

import itertools
from pathlib import Path

import pyarrow as pa
import pytest

from isoterma.benchmark.engines import IMPLEMENTACOES, REFERENCIA, Entrada, _trechos
from isoterma.benchmark.tarefas import Formato, Tarefa, comparar, normalizar


@pytest.fixture(scope="module")
def referencias(entrada: Entrada) -> dict[Tarefa, pa.Table]:
    return {
        tarefa: normalizar(tarefa, IMPLEMENTACOES[(tarefa, *REFERENCIA[tarefa])](entrada))
        for tarefa in Tarefa
    }


@pytest.mark.parametrize(
    "chave", list(IMPLEMENTACOES), ids=["-".join(map(str, c)) for c in IMPLEMENTACOES]
)
def test_engine_confere_com_a_referencia(
    chave: tuple[Tarefa, Formato, str], entrada: Entrada, referencias: dict[Tarefa, pa.Table]
) -> None:
    tarefa = chave[0]

    resultado = normalizar(tarefa, IMPLEMENTACOES[chave](entrada))

    validacao = comparar(tarefa, resultado, referencias[tarefa])
    assert validacao.valido, validacao.motivo


def test_referencias_tem_o_tamanho_esperado(referencias: dict[Tarefa, pa.Table]) -> None:
    # 10 racks × 4 sensores de temperatura + 2 CRACs × 2; 10 racks × 24 horas.
    assert referencias[Tarefa.BRC].num_rows == 44
    assert referencias[Tarefa.REALISTA].num_rows == 240


def test_tarefa_realista_conta_leituras_fora_da_faixa(referencias: dict[Tarefa, pa.Table]) -> None:
    assert sum(referencias[Tarefa.REALISTA].column("leituras_fora").to_pylist()) > 0


def test_trechos_cobrem_o_arquivo_e_terminam_em_fim_de_linha(tmp_path: Path) -> None:
    arquivo = tmp_path / "linhas.txt"
    conteudo = b"".join(f"sensor-{i % 7};{i % 50}.5\n".encode() for i in range(5_000))
    arquivo.write_bytes(conteudo)

    trechos = _trechos(arquivo, tamanho=1_000)

    assert trechos[0][0] == 0
    assert trechos[-1][1] == len(conteudo)
    assert all(a[1] == b[0] for a, b in itertools.pairwise(trechos))
    assert all(conteudo[fim - 1 : fim] == b"\n" for _, fim in trechos)
