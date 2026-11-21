from pathlib import Path

import pytest

from isoterma.motor import agregar
from isoterma.simulador import simular
from tests.simulador.conftest import config_com_incidentes


@pytest.fixture(scope="session")
def dados(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Pasta de dados com uma simulação ("hall") e uma pasta qualquer que não é simulação."""
    raiz = tmp_path_factory.mktemp("api")
    simular(config_com_incidentes(), raiz / "hall", processos=1)
    agregar(raiz / "hall")
    (raiz / "outra-coisa").mkdir()
    return raiz
