import shutil
from pathlib import Path

import duckdb
import pytest

from isoterma.anomalias import Limiares, avaliar, detectar, ler_gabarito
from isoterma.anomalias.detectores import _ilhas
from isoterma.motor import agregar
from isoterma.simulador import simular
from tests.simulador.conftest import config_com_incidentes


def test_detecta_um_incidente_de_cada_tipo_sem_alertas_falsos(diretorio: Path) -> None:
    resultado = detectar(diretorio)
    avaliacao = avaliar("hall", resultado, ler_gabarito(diretorio))

    assert {d.tipo for d in resultado.deteccoes} == {
        "falha_crac",
        "super_refrigeracao",
        "rack_sobrecarregado",
        "recirculacao",
        "sensor_congelado",
        "sensor_deriva",
        "sensor_picos",
        "sensor_sem_leitura",
    }
    assert avaliacao.perdidos == []
    assert avaliacao.falsos == []
    assert resultado.fonte == "leituras brutas"


def test_cada_alerta_explica_o_que_viu(diretorio: Path) -> None:
    por_tipo = {d.tipo: d for d in detectar(diretorio).deteccoes}

    assert "acima do normal" in por_tipo["falha_crac"].evidencia
    assert "zona subindo junto" in por_tipo["falha_crac"].evidencia
    assert por_tipo["sensor_deriva"].alvo == "B-05/entrada-topo"
    assert "Repetiu exatamente" in por_tipo["sensor_congelado"].evidencia


def test_hall_sem_incidentes_nao_gera_alertas(diretorio_normal: Path) -> None:
    assert detectar(diretorio_normal).deteccoes == []


def test_nao_precisa_do_gabarito(diretorio: Path, tmp_path: Path) -> None:
    copia = tmp_path / "sem-gabarito"
    shutil.copytree(diretorio, copia)
    (copia / "incidentes.parquet").unlink()

    assert len(detectar(copia).deteccoes) == 8


def test_limiares_mudam_o_que_conta_como_anomalia(diretorio: Path) -> None:
    exigente = Limiares(sobrecarga_razao=10.0, recirculacao_c=50.0)
    tipos = {d.tipo for d in detectar(diretorio, exigente).deteccoes}

    assert "rack_sobrecarregado" not in tipos
    assert "recirculacao" not in tipos


@pytest.mark.parametrize("com_agregados", [True, False])
def test_leituras_mais_frequentes_que_um_minuto(tmp_path: Path, com_agregados: bool) -> None:
    config = config_com_incidentes()
    config = config.model_copy(
        update={"periodo": config.periodo.model_copy(update={"intervalo_s": 20})}
    )
    destino = tmp_path / "hall"
    simular(config, destino, processos=1)
    if com_agregados:
        agregar(destino)

    resultado = detectar(destino)
    avaliacao = avaliar("hall", resultado, ler_gabarito(destino))

    esperado = "agregados por minuto" if com_agregados else "leituras agrupadas por minuto"
    assert resultado.fonte == esperado
    assert avaliacao.perdidos == []
    assert avaliacao.falsos == []


def _eventos(sql_sinais: str, **opcoes: int | float) -> list[tuple[str, str, str, int]]:
    consulta = _ilhas(sql_sinais, passo_s=60, **opcoes)  # type: ignore[arg-type]
    relacao = duckdb.sql(consulta)
    assert relacao is not None
    linhas = relacao.fetchall()
    return [(alvo, f"{i:%H:%M}", f"{f:%H:%M}", minutos) for alvo, i, f, _, minutos in linhas]


SINAIS = """
    SELECT 'x' AS alvo, TIMESTAMP '2026-01-01 00:00' + INTERVAL (m) MINUTE AS t, 1.0 AS v
    FROM unnest([0, 1, 2, 10, 11, 40]) AS u(m)
"""


def test_ilhas_juntam_minutos_proximos() -> None:
    assert _eventos(SINAIS, juntar_min=5, duracao_min=0) == [
        ("x", "00:00", "00:03", 3),
        ("x", "00:10", "00:12", 2),
        ("x", "00:40", "00:41", 1),
    ]
    assert _eventos(SINAIS, juntar_min=10, duracao_min=0)[0] == ("x", "00:00", "00:12", 5)


def test_ilhas_descartam_eventos_curtos_e_esparsos() -> None:
    assert _eventos(SINAIS, juntar_min=5, duracao_min=3) == [("x", "00:00", "00:03", 3)]
    # Juntando tudo, o evento tem 41 min, mas só 6 minutos marcados (15%).
    assert len(_eventos(SINAIS, juntar_min=60, duracao_min=0, cobertura=0.0)) == 1
    assert _eventos(SINAIS, juntar_min=60, duracao_min=0, cobertura=0.5) == []


def test_ilhas_recuam_o_inicio() -> None:
    assert _eventos(SINAIS, juntar_min=5, duracao_min=0, recuo_min=2)[0][1] == "23:58"
