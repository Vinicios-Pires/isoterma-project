import duckdb
import pytest

from isoterma.dados import conectar
from isoterma.simulador import ResultadoSimulacao, preset, simular
from isoterma.simulador.config import ConfigIncidentes, ConfigSimulacao, IncidenteProgramado
from isoterma.simulador.config import TipoIncidente as T

# Um incidente de cada tipo, em horários que não se sobrepõem no mesmo alvo.
PROGRAMADOS = [
    IncidenteProgramado(
        tipo=T.FALHA_CRAC, inicio_h=2, duracao_min=120, alvo="CRAC-01", intensidade=1.0
    ),
    IncidenteProgramado(
        tipo=T.SUPER_REFRIGERACAO, inicio_h=8, duracao_min=120, alvo="CRAC-02", intensidade=4.0
    ),
    IncidenteProgramado(
        tipo=T.RECIRCULACAO, inicio_h=12, duracao_min=120, alvo="A-03", intensidade=4.0
    ),
    IncidenteProgramado(
        tipo=T.RACK_SOBRECARREGADO, inicio_h=12, duracao_min=120, alvo="B-03", intensidade=0.8
    ),
    IncidenteProgramado(tipo=T.SENSOR_CONGELADO, inicio_h=16, duracao_min=60, alvo="A-02/saida"),
    IncidenteProgramado(
        tipo=T.SENSOR_SEM_LEITURA, inicio_h=16, duracao_min=60, alvo="A-04/saida", intensidade=1.0
    ),
    IncidenteProgramado(
        tipo=T.SENSOR_PICOS, inicio_h=16, duracao_min=120, alvo="B-04/saida", intensidade=0.2
    ),
    IncidenteProgramado(
        tipo=T.SENSOR_DERIVA,
        inicio_h=16,
        duracao_min=240,
        alvo="B-05/entrada-topo",
        intensidade=1.0,
    ),
]


def config_com_incidentes(**mudancas: object) -> ConfigSimulacao:
    base = preset("teste").model_copy(
        update={"incidentes": ConfigIncidentes(programados=PROGRAMADOS), "linhas_por_bloco": 10_000}
    )
    return base.model_copy(update=mudancas)


@pytest.fixture(scope="session")
def simulacao(tmp_path_factory: pytest.TempPathFactory) -> ResultadoSimulacao:
    return simular(config_com_incidentes(), tmp_path_factory.mktemp("sim") / "teste", processos=1)


@pytest.fixture(scope="session")
def simulacao_sem_incidentes(tmp_path_factory: pytest.TempPathFactory) -> ResultadoSimulacao:
    return simular(preset("teste"), tmp_path_factory.mktemp("sim") / "normal", processos=1)


@pytest.fixture
def db(simulacao: ResultadoSimulacao) -> duckdb.DuckDBPyConnection:
    return conectar(simulacao.diretorio)


def escalar(conexao: duckdb.DuckDBPyConnection, sql: str) -> float:
    linha = conexao.execute(sql).fetchone()
    assert linha is not None
    return linha[0]


def janela(incidente_alvo: str) -> str:
    """Condição SQL: leituras dentro do período do incidente com esse alvo."""
    return (
        f"l.ts >= (SELECT inicio FROM incidentes WHERE alvo = '{incidente_alvo}') "
        f"AND l.ts < (SELECT fim FROM incidentes WHERE alvo = '{incidente_alvo}')"
    )
