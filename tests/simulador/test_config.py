from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from isoterma.simulador import Preset, carregar_config, preset
from isoterma.simulador.config import Periodo, TipoIncidente


@pytest.mark.parametrize("nome", list(Preset))
def test_presets_sao_validos(nome: Preset) -> None:
    config = preset(nome)

    assert config.nome == nome.value
    assert config.total_linhas > 0


def test_preset_bilhao_passa_de_um_bilhao_de_linhas() -> None:
    linhas = preset("bilhao").total_linhas

    assert 1_000_000_000 <= linhas < 1_000_010_000


def test_contagem_de_sensores_e_linhas_do_preset_teste() -> None:
    config = preset("teste")

    assert config.total_sensores == 10 * 5 + 2 * 2
    assert config.total_linhas == 1440 * 54


def test_inicio_sem_fuso_e_tratado_como_utc() -> None:
    periodo = Periodo(inicio=datetime(2026, 1, 1, 12))

    assert periodo.inicio == datetime(2026, 1, 1, 12, tzinfo=UTC)


def test_intervalo_que_nao_divide_o_dia_e_rejeitado() -> None:
    with pytest.raises(ValidationError, match="86400"):
        Periodo(intervalo_s=7)


def test_campo_desconhecido_e_rejeitado() -> None:
    with pytest.raises(ValidationError):
        preset("teste").model_validate({"hall": {"fileras": 3}})


def test_carrega_config_em_toml(tmp_path: Path) -> None:
    arquivo = tmp_path / "Meu Hall.toml"
    arquivo.write_text(
        """
seed = 7

[hall]
fileiras = 3
racks_por_fileira = 4
cracs = 2

[periodo]
inicio = 2026-12-01T00:00:00Z
dias = 2
intervalo_s = 300

[incidentes.taxas_por_dia]
falha_crac = 0.5

[[incidentes.programados]]
tipo = "recirculacao"
inicio_h = 3
duracao_min = 90
alvo = "B-02"
""",
        encoding="utf-8",
    )

    config = carregar_config(arquivo)

    assert config.nome == "meu-hall"
    assert config.seed == 7
    assert config.hall.total_racks == 12
    assert config.periodo.passos == 2 * 86400 // 300
    assert config.incidentes.taxas_por_dia == {TipoIncidente.FALHA_CRAC: 0.5}
    assert config.incidentes.programados[0].alvo == "B-02"
