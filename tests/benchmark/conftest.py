import pytest

from isoterma.benchmark.engines import Entrada
from isoterma.dados import exportar_1brc
from isoterma.simulador import simular
from tests.simulador.conftest import config_com_incidentes


@pytest.fixture(scope="session")
def entrada(tmp_path_factory: pytest.TempPathFactory) -> Entrada:
    """Simulação pequena com todos os incidentes (inclui leituras nulas e fora da faixa)."""
    diretorio = tmp_path_factory.mktemp("bench") / "hall"
    simular(config_com_incidentes(), diretorio, processos=1)
    txt = diretorio / "benchmark" / "medicoes.txt"
    txt.parent.mkdir()
    exportar_1brc(diretorio, txt)
    return Entrada(diretorio.resolve(), txt.resolve())
