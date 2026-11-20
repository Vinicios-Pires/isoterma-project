"""O comportamento térmico tem que ser plausível, com e sem incidentes."""

import duckdb

from isoterma.dados import conectar
from isoterma.simulador import ResultadoSimulacao
from isoterma.simulador.esquema import FAIXA_ASHRAE_C
from tests.simulador.conftest import escalar, janela


def test_operacao_normal_fica_na_faixa_ashrae(
    simulacao_sem_incidentes: ResultadoSimulacao,
) -> None:
    db = conectar(simulacao_sem_incidentes.diretorio)
    minimo, maximo = db.execute(
        """
        SELECT min(valor), max(valor)
        FROM leituras JOIN sensores USING (sensor_id)
        WHERE tipo = 'temp_entrada'
        """
    ).fetchone() or (None, None)

    assert minimo is not None and maximo is not None
    assert FAIXA_ASHRAE_C[0] <= minimo
    assert maximo <= FAIXA_ASHRAE_C[1]


def test_saida_e_mais_quente_que_a_entrada(
    simulacao_sem_incidentes: ResultadoSimulacao,
) -> None:
    db = conectar(simulacao_sem_incidentes.diretorio)
    delta = escalar(
        db,
        """
        SELECT avg(valor) FILTER (tipo = 'temp_saida') - avg(valor) FILTER (tipo = 'temp_entrada')
        FROM leituras JOIN sensores USING (sensor_id)
        """,
    )

    assert 8 < delta < 15


def test_topo_do_rack_e_mais_quente_que_a_base(
    simulacao_sem_incidentes: ResultadoSimulacao,
) -> None:
    db = conectar(simulacao_sem_incidentes.diretorio)
    diferenca = escalar(
        db,
        """
        SELECT avg(valor) FILTER (altura = 'topo') - avg(valor) FILTER (altura = 'base')
        FROM leituras JOIN sensores USING (sensor_id)
        WHERE tipo = 'temp_entrada'
        """,
    )

    assert diferenca > 0.5


def test_falha_de_crac_aquece_a_zona_acima_de_27(db: duckdb.DuckDBPyConnection) -> None:
    pico_na_zona = escalar(
        db,
        f"""
        SELECT max(l.valor)
        FROM leituras AS l JOIN sensores AS s USING (sensor_id) JOIN racks AS r USING (rack_id)
        WHERE s.tipo = 'temp_entrada' AND r.zona_crac = 'CRAC-01' AND {janela("CRAC-01")}
        """,
    )

    assert pico_na_zona > FAIXA_ASHRAE_C[1]


def test_super_refrigeracao_esfria_a_zona_abaixo_de_18(db: duckdb.DuckDBPyConnection) -> None:
    minimo_na_zona = escalar(
        db,
        f"""
        SELECT min(l.valor)
        FROM leituras AS l JOIN sensores AS s USING (sensor_id) JOIN racks AS r USING (rack_id)
        WHERE s.tipo = 'temp_entrada' AND r.zona_crac = 'CRAC-02' AND {janela("CRAC-02")}
        """,
    )

    assert minimo_na_zona < FAIXA_ASHRAE_C[0]


def test_recirculacao_esquenta_o_topo_do_rack(db: duckdb.DuckDBPyConnection) -> None:
    # Compara topo e base do mesmo rack: assim a falha do CRAC-01, que aquece a zona inteira,
    # não interfere na medida.
    aumento_da_diferenca = escalar(
        db,
        f"""
        WITH gap AS (
            SELECT {janela("A-03")} AS durante,
                   avg(l.valor) FILTER (s.altura = 'topo')
                       - avg(l.valor) FILTER (s.altura = 'base') AS topo_menos_base
            FROM leituras AS l JOIN sensores AS s USING (sensor_id)
            WHERE s.rack_id = 'A-03' AND s.tipo = 'temp_entrada'
            GROUP BY durante
        )
        SELECT max(topo_menos_base) FILTER (durante) - max(topo_menos_base) FILTER (NOT durante)
        FROM gap
        """,
    )

    assert aumento_da_diferenca > 3


def test_sobrecarga_aumenta_potencia_e_saida(db: duckdb.DuckDBPyConnection) -> None:
    potencia, saida = db.execute(
        f"""
        SELECT
            avg(l.valor) FILTER (s.tipo = 'potencia_kw' AND {janela("B-03")})
                / avg(l.valor) FILTER (s.tipo = 'potencia_kw' AND NOT {janela("B-03")}),
            avg(l.valor) FILTER (s.tipo = 'temp_saida' AND {janela("B-03")})
                - avg(l.valor) FILTER (s.tipo = 'temp_saida' AND NOT {janela("B-03")})
        FROM leituras AS l JOIN sensores AS s USING (sensor_id)
        WHERE s.rack_id = 'B-03'
        """
    ).fetchone() or (0, 0)

    assert potencia > 1.5
    assert saida > 5
