from datetime import UTC, datetime, timedelta

import pytest

from isoterma.motor import Hall
from isoterma.motor.hall import escolher_bucket

DURANTE_A_FALHA = datetime(2026, 11, 1, 3, 50, tzinfo=UTC)
OPERACAO_NORMAL = datetime(2026, 11, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("janela_s", "max_pontos", "intervalo_s", "esperado"),
    [
        (3600, 1000, 10, 10),
        (86_400, 500, 10, 300),
        (86_400, 24, 60, 3600),
        (30 * 86_400, 10, 60, 3 * 86_400),
        (600, 1000, 60, 60),
    ],
)
def test_escolher_bucket(janela_s: int, max_pontos: int, intervalo_s: int, esperado: int) -> None:
    assert escolher_bucket(janela_s, max_pontos, intervalo_s) == esperado


def test_serie_de_um_sensor(hall: Hall) -> None:
    serie = hall.serie("A-01/saida", max_pontos=24)

    assert serie.num_rows == 24
    assert set(serie.column("sensor").to_pylist()) == {"A-01/saida"}
    assert all(n == 360 for n in serie.column("leituras").to_pylist())


def test_serie_de_um_rack_traz_os_cinco_sensores(hall: Hall) -> None:
    serie = hall.serie("B-02", max_pontos=10)

    assert len(set(serie.column("sensor").to_pylist())) == 5


def test_serie_igual_vinda_do_agregado_ou_do_bruto(hall: Hall) -> None:
    inicio = datetime(2026, 11, 1, 2, tzinfo=UTC)
    do_agregado = hall.serie(
        "CRAC-01/insuflamento", inicio, inicio + timedelta(hours=6), max_pontos=6
    )
    do_bruto = hall.serie(
        "CRAC-01/insuflamento",
        inicio + timedelta(seconds=10),  # desalinhado: obriga a usar as leituras brutas
        inicio + timedelta(hours=6),
        max_pontos=6,
    )

    assert do_agregado.column("maximo").to_pylist()[1:] == do_bruto.column("maximo").to_pylist()[1:]


def test_serie_de_alvo_inexistente(hall: Hall) -> None:
    with pytest.raises(ValueError, match="Z-99"):
        hall.serie("Z-99")


def test_mapa_durante_a_falha_mostra_a_zona_quente(hall: Hall) -> None:
    mapa = hall.mapa_termico(DURANTE_A_FALHA).to_pylist()

    acima = {r["rack_id"] for r in mapa if r["faixa"] == "acima"}
    assert acima
    assert all(r["zona_crac"] == "CRAC-01" for r in mapa if r["rack_id"] in acima)


def test_mapa_em_operacao_normal_fica_na_faixa(hall: Hall) -> None:
    mapa = hall.mapa_termico(OPERACAO_NORMAL).to_pylist()

    assert len(mapa) == 10
    assert {r["faixa"] for r in mapa} == {"ok"}


def test_mapa_de_potencia_nao_avalia_faixa(hall: Hall) -> None:
    mapa = hall.mapa_termico(OPERACAO_NORMAL, tipo="potencia_kw").to_pylist()

    assert {r["faixa"] for r in mapa} == {None}
    assert all(r["valor"] > 0 for r in mapa)


def test_data_sem_fuso_usa_o_horario_local_do_hall(hall: Hall) -> None:
    local = DURANTE_A_FALHA.astimezone(hall.fuso).replace(tzinfo=None)

    assert hall.mapa_termico(local) == hall.mapa_termico(DURANTE_A_FALHA)


@pytest.mark.parametrize(
    ("argumentos", "mensagem"),
    [
        ({"tipo": "umidade"}, "tipo deve ser"),
        ({"tipo": "temp_saida", "altura": "topo"}, "altura só vale"),
        ({"altura": "teto"}, "altura só vale"),
        ({"instante": datetime(2030, 1, 1, tzinfo=UTC)}, "fora da simulação"),
    ],
)
def test_mapa_com_argumentos_invalidos(hall: Hall, argumentos: dict, mensagem: str) -> None:
    with pytest.raises(ValueError, match=mensagem):
        hall.mapa_termico(**argumentos)


def test_fora_da_faixa_encontra_a_falha(hall: Hall) -> None:
    fora = hall.fora_da_faixa().to_pylist()

    assert fora
    assert all(r["zona_crac"] == "CRAC-01" for r in fora)
    assert all(r["minutos_acima"] > 0 for r in fora)
    assert min(r["primeira_vez"] for r in fora) >= datetime(2026, 11, 1, 2, tzinfo=UTC)
    assert max(r["ultima_vez"] for r in fora) <= datetime(2026, 11, 1, 4, 30, tzinfo=UTC)


def test_fora_da_faixa_vazio_numa_janela_tranquila(hall: Hall) -> None:
    inicio = datetime(2026, 11, 1, 10, tzinfo=UTC)

    assert hall.fora_da_faixa(inicio, inicio + timedelta(hours=4)).num_rows == 0


def test_resumo_do_periodo_inteiro(hall: Hall) -> None:
    resumo = hall.resumo()

    assert resumo["fonte"] == "agregados_hora"
    assert resumo["leituras"] == 8640 * 54
    assert resumo["racks_acima_da_faixa"] >= 1
    assert 19 < resumo["por_tipo"]["temp_entrada"]["media"] < 23
    assert resumo["potencia_media_total_kw"] > 0


def test_janela_invertida(hall: Hall) -> None:
    with pytest.raises(ValueError, match="anterior ao fim"):
        hall.resumo(OPERACAO_NORMAL, DURANTE_A_FALHA)


def test_esquema_inclui_os_agregados(hall: Hall) -> None:
    assert {"leituras", "agregados_minuto", "agregados_hora"} <= set(hall.esquema())
