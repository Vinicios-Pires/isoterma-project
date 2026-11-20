from collections.abc import Iterator
from pathlib import Path

import pytest

from isoterma.motor import Hall, agregar
from isoterma.simulador import preset, simular
from isoterma.simulador.config import ConfigIncidentes, IncidenteProgramado, TipoIncidente

# Falha de CRAC-01 das 02:00 às 04:00 UTC do primeiro dia.
FALHA = IncidenteProgramado(
    tipo=TipoIncidente.FALHA_CRAC, inicio_h=2, duracao_min=120, alvo="CRAC-01", intensidade=1.0
)


@pytest.fixture(scope="session")
def diretorio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Simulação de 1 dia com leituras a cada 10 s, já agregada por minuto e por hora."""
    base = preset("teste")
    config = base.model_copy(
        update={
            "periodo": base.periodo.model_copy(update={"intervalo_s": 10}),
            "incidentes": ConfigIncidentes(programados=[FALHA]),
        }
    )
    destino = tmp_path_factory.mktemp("motor") / "hall"
    simular(config, destino, processos=1)
    agregar(destino)
    return destino


@pytest.fixture
def hall(diretorio: Path) -> Iterator[Hall]:
    with Hall(diretorio) as aberto:
        yield aberto
