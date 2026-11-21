from collections.abc import Iterator
from pathlib import Path

import pytest

from isoterma.motor import Hall
from isoterma.simulador import simular
from tests.simulador.conftest import config_com_incidentes


@pytest.fixture(scope="session")
def diretorio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Um dia de hall com um incidente de cada tipo (inclui a falha do CRAC-01 às 2h UTC)."""
    destino = tmp_path_factory.mktemp("ia") / "hall"
    simular(config_com_incidentes(), destino, processos=1)
    return destino


@pytest.fixture
def hall(diretorio: Path) -> Iterator[Hall]:
    with Hall(diretorio, ocultar_gabarito=True) as aberto:
        yield aberto
