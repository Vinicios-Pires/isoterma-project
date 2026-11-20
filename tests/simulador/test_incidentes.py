"""Defeitos de sensor e o gabarito dos incidentes."""

import duckdb
import numpy as np
import pytest

from isoterma.simulador import preset
from isoterma.simulador.config import ConfigIncidentes, IncidenteProgramado, TipoIncidente
from isoterma.simulador.incidentes import sortear_incidentes
from isoterma.simulador.layout import montar_layout
from tests.simulador.conftest import PROGRAMADOS, escalar, janela


def test_gabarito_lista_todos_os_incidentes(db: duckdb.DuckDBPyConnection) -> None:
    tipos = {linha[0] for linha in db.execute("SELECT tipo FROM incidentes").fetchall()}

    assert tipos == {tipo.value for tipo in TipoIncidente}
    assert escalar(db, "SELECT count(*) FROM incidentes") == len(PROGRAMADOS)


def test_sensor_congelado_repete_o_mesmo_valor(db: duckdb.DuckDBPyConnection) -> None:
    distintos = escalar(
        db,
        f"""
        SELECT count(DISTINCT l.valor)
        FROM leituras AS l JOIN sensores AS s USING (sensor_id)
        WHERE s.codigo = 'A-02/saida' AND {janela("A-02/saida")}
        """,
    )

    assert distintos == 1


def test_sensor_sem_leitura_grava_nulos(db: duckdb.DuckDBPyConnection) -> None:
    total, lidos = db.execute(
        f"""
        SELECT count(*), count(l.valor)
        FROM leituras AS l JOIN sensores AS s USING (sensor_id)
        WHERE s.codigo = 'A-04/saida' AND {janela("A-04/saida")}
        """
    ).fetchone() or (0, 0)

    assert total == 60
    assert lidos == 0


def test_sensor_com_picos_tem_valores_absurdos(db: duckdb.DuckDBPyConnection) -> None:
    amplitude = escalar(
        db,
        f"""
        SELECT max(l.valor) - min(l.valor)
        FROM leituras AS l JOIN sensores AS s USING (sensor_id)
        WHERE s.codigo = 'B-04/saida' AND {janela("B-04/saida")}
        """,
    )

    assert amplitude > 15


def test_sensor_com_deriva_sobe_com_o_tempo(db: duckdb.DuckDBPyConnection) -> None:
    inclinacao_por_hora = escalar(
        db,
        f"""
        SELECT regr_slope(l.valor, epoch(l.ts)) * 3600
        FROM leituras AS l JOIN sensores AS s USING (sensor_id)
        WHERE s.codigo = 'B-05/entrada-topo' AND {janela("B-05/entrada-topo")}
        """,
    )

    assert inclinacao_por_hora == pytest.approx(1.0, abs=0.3)


def test_sorteio_respeita_as_taxas() -> None:
    config = preset("teste").model_copy(
        update={
            "incidentes": ConfigIncidentes(taxas_por_dia={TipoIncidente.FALHA_CRAC: 20}),
        }
    )
    layout = montar_layout(config, np.random.default_rng(0))

    incidentes = sortear_incidentes(config, layout, np.random.default_rng(0))

    assert 5 < len(incidentes) < 40
    assert all(inc.alvo in layout.crac_ids for inc in incidentes)
    assert all(0 <= inc.inicio_s < inc.fim_s <= config.periodo.duracao_s for inc in incidentes)


def test_alvo_inexistente_e_rejeitado() -> None:
    config = preset("teste").model_copy(
        update={
            "incidentes": ConfigIncidentes(
                programados=[
                    IncidenteProgramado(
                        tipo=TipoIncidente.RECIRCULACAO, inicio_h=1, duracao_min=10, alvo="Z-99"
                    )
                ]
            )
        }
    )
    layout = montar_layout(config, np.random.default_rng(0))

    with pytest.raises(ValueError, match="Z-99"):
        sortear_incidentes(config, layout, np.random.default_rng(0))
