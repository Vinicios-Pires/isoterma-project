from pathlib import Path

import pytest

from isoterma.simulador import preset, simular
from tests.simulador.conftest import config_com_incidentes


@pytest.fixture(scope="session")
def diretorio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Um dia de hall com um incidente de cada tipo, sem sobreposição."""
    destino = tmp_path_factory.mktemp("anomalias") / "hall"
    simular(config_com_incidentes(), destino, processos=1)
    return destino


@pytest.fixture(scope="session")
def diretorio_normal(tmp_path_factory: pytest.TempPathFactory) -> Path:
    destino = tmp_path_factory.mktemp("anomalias") / "normal"
    simular(preset("teste"), destino, processos=1)
    return destino
