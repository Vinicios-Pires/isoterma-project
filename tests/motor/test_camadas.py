from datetime import UTC, datetime
from pathlib import Path

import pytest

from isoterma.dados import conectar
from isoterma.motor import Hall, agregar
from isoterma.simulador import preset, simular


def test_gera_agregados_por_minuto_e_por_hora(diretorio: Path) -> None:
    db = conectar(diretorio)

    por_minuto = db.execute("SELECT count(*) FROM agregados_minuto").fetchone()
    por_hora = db.execute("SELECT count(*) FROM agregados_hora").fetchone()

    assert por_minuto == (1440 * 54,)
    assert por_hora == (24 * 54,)


def test_agregado_bate_com_as_leituras_brutas(diretorio: Path) -> None:
    db = conectar(diretorio)

    diferencas = db.execute(
        """
        WITH bruto AS (
            SELECT sensor_id, time_bucket(INTERVAL 1 HOUR, ts) AS inicio,
                   min(valor) AS minimo, max(valor) AS maximo, avg(valor) AS media,
                   count(valor) AS leituras
            FROM leituras GROUP BY ALL
        )
        SELECT count(*) FILTER (
            b.minimo != a.minimo OR b.maximo != a.maximo
            OR abs(b.media - a.media) > 1e-9 OR b.leituras != a.leituras
        )
        FROM bruto AS b JOIN agregados_hora AS a USING (sensor_id, inicio)
        """
    ).fetchone()

    assert diferencas == (0,)


def test_agregar_de_novo_substitui_os_agregados(diretorio: Path) -> None:
    assert agregar(diretorio, ["hora"]) == {"hora": 24 * 54}


def test_leituras_por_minuto_so_agregam_por_hora(tmp_path: Path) -> None:
    simular(preset("teste"), tmp_path / "hall", processos=1)

    assert agregar(tmp_path / "hall") == {"hora": 24 * 54}
    with pytest.raises(ValueError, match="não reduz nada"):
        agregar(tmp_path / "hall", ["minuto"])


def test_granularidade_desconhecida(diretorio: Path) -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        agregar(diretorio, ["semana"])


def test_hall_escolhe_a_camada_mais_grossa_que_cabe(hall: Hall) -> None:
    hora_cheia = datetime(2026, 11, 1, 3, tzinfo=UTC)
    minuto_cheio = datetime(2026, 11, 1, 3, 7, tzinfo=UTC)
    quebrado = datetime(2026, 11, 1, 3, 7, 30, tzinfo=UTC)
    fim = datetime(2026, 11, 1, 9, tzinfo=UTC)

    assert hall._camada(hora_cheia, fim, 3600).tabela == "agregados_hora"
    assert hall._camada(minuto_cheio, fim, 3600).tabela == "agregados_minuto"
    assert hall._camada(quebrado, fim, 3600).tabela == "leituras"
    assert hall._camada(hora_cheia, fim, 300).tabela == "agregados_minuto"
    assert hall._camada(hora_cheia, fim, 10).tabela == "leituras"
