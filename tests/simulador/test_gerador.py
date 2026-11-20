"""Saída em disco, reprodutibilidade e paralelismo."""

import itertools
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from isoterma.dados import conectar, exportar_1brc
from isoterma.simulador import ResultadoSimulacao, simular
from isoterma.simulador.gerador import MANIFESTO, planejar_blocos
from tests.simulador.conftest import config_com_incidentes, escalar


def _leituras(diretorio: Path) -> list[tuple[object, ...]]:
    conexao = conectar(diretorio)
    return conexao.execute(
        "SELECT epoch_ms(ts), sensor_id, valor FROM leituras ORDER BY ts, sensor_id"
    ).fetchall()


def test_numero_de_linhas_bate_com_a_configuracao(simulacao: ResultadoSimulacao) -> None:
    db = conectar(simulacao.diretorio)

    assert simulacao.linhas == config_com_incidentes().total_linhas
    assert escalar(db, "SELECT count(*) FROM leituras") == simulacao.linhas


def test_cada_sensor_tem_uma_leitura_por_passo(simulacao: ResultadoSimulacao) -> None:
    db = conectar(simulacao.diretorio)

    contagens = db.execute("SELECT count(*) FROM leituras GROUP BY sensor_id").fetchall()

    assert {c for (c,) in contagens} == {1440}


def test_mesma_seed_gera_os_mesmos_dados_com_qualquer_numero_de_processos(
    simulacao: ResultadoSimulacao, tmp_path: Path
) -> None:
    paralela = simular(config_com_incidentes(), tmp_path / "paralela", processos=2)

    assert paralela.processos == 2
    assert _leituras(paralela.diretorio) == _leituras(simulacao.diretorio)


def test_seed_diferente_gera_dados_diferentes(
    simulacao: ResultadoSimulacao, tmp_path: Path
) -> None:
    outra = simular(config_com_incidentes(seed=7), tmp_path / "outra", processos=1)

    assert _leituras(outra.diretorio) != _leituras(simulacao.diretorio)


def test_blocos_nao_atravessam_a_meia_noite() -> None:
    config = config_com_incidentes().model_copy(
        update={"periodo": config_com_incidentes().periodo.model_copy(update={"dias": 2.5})}
    )

    blocos = planejar_blocos(config)

    assert {b.dia for b in blocos} == {"2026-11-01", "2026-11-02", "2026-11-03"}
    assert blocos[0].passo_inicio == 0
    assert blocos[-1].passo_fim == config.periodo.passos
    assert all(a.passo_fim == b.passo_inicio for a, b in itertools.pairwise(blocos))


def test_leituras_sao_particionadas_por_dia(simulacao: ResultadoSimulacao) -> None:
    particoes = sorted(p.name for p in (simulacao.diretorio / "leituras").iterdir())

    assert particoes == ["data=2026-11-01"]


def test_esquema_das_leituras(simulacao: ResultadoSimulacao) -> None:
    arquivo = next((simulacao.diretorio / "leituras").rglob("*.parquet"))

    esquema = pq.read_schema(arquivo)

    assert [str(t) for t in esquema.types] == ["timestamp[ms, tz=UTC]", "int32", "float"]
    assert esquema.names == ["ts", "sensor_id", "valor"]


def test_manifesto_registra_config_contagens_e_esquema(simulacao: ResultadoSimulacao) -> None:
    manifesto = json.loads((simulacao.diretorio / MANIFESTO).read_text(encoding="utf-8"))

    assert manifesto["contagens"]["linhas"] == simulacao.linhas
    assert manifesto["config"]["seed"] == 42
    assert set(manifesto["esquema"]) == {"leituras", "sensores", "racks", "cracs", "incidentes"}


def test_nao_sobrescreve_sem_pedir(simulacao: ResultadoSimulacao) -> None:
    with pytest.raises(FileExistsError, match="--sobrescrever"):
        simular(config_com_incidentes(), simulacao.diretorio)


def test_nao_apaga_pasta_que_nao_e_simulacao(tmp_path: Path) -> None:
    (tmp_path / "importante.txt").write_text("não apague", encoding="utf-8")

    with pytest.raises(FileExistsError, match="nada foi apagado"):
        simular(config_com_incidentes(), tmp_path, sobrescrever=True)

    assert (tmp_path / "importante.txt").exists()


def test_exporta_no_formato_1brc(simulacao: ResultadoSimulacao, tmp_path: Path) -> None:
    destino = tmp_path / "medicoes.txt"

    linhas = exportar_1brc(simulacao.diretorio, destino)

    primeira = destino.read_text(encoding="utf-8").splitlines()[0]
    codigo, valor = primeira.split(";")
    assert linhas > 0
    assert "/" in codigo
    assert float(valor) == pytest.approx(float(valor), abs=0.05)
