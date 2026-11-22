import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from isoterma.anomalias import Deteccao, Limiares, Resultado, avaliar, ler_gabarito
from isoterma.anomalias.avaliacao import Incidente
from isoterma.anomalias.relatorio import avaliar_conjunto, gerar_relatorio
from isoterma.cli import app

T0 = datetime(2026, 11, 1, tzinfo=UTC)


def h(horas: float) -> datetime:
    return T0 + timedelta(hours=horas)


def incidente(tipo: str, alvo: str, inicio: float, fim: float, visivel: bool = True) -> Incidente:
    return Incidente(tipo, alvo, h(inicio), h(fim), 1.0, "", visivel)


def deteccao(tipo: str, alvo: str, inicio: float, fim: float) -> Deteccao:
    return Deteccao(tipo, alvo, h(inicio), h(fim), "evidência", 1.0)


def resultado(*deteccoes: Deteccao) -> Resultado:
    return Resultado(list(deteccoes), Limiares(), 1.0, "teste")


def test_acerto_exige_tipo_alvo_e_periodo() -> None:
    gabarito = [incidente("falha_crac", "CRAC-01", 2, 4)]
    a = avaliar(
        "s",
        resultado(
            deteccao("falha_crac", "CRAC-01", 2.1, 4),  # certo
            deteccao("falha_crac", "CRAC-02", 2, 4),  # alvo errado
            deteccao("falha_crac", "CRAC-01", 10, 11),  # fora do período
        ),
        gabarito,
    )

    placar = a.por_tipo["falha_crac"]
    assert (placar.detectados, placar.incidentes) == (1, 1)
    assert (placar.corretas, placar.deteccoes) == (1, 3)
    assert placar.precisao == 1 / 3
    assert placar.atrasos_min == [6.0]
    assert [d.alvo for d in a.falsos] == ["CRAC-02", "CRAC-01"]


def test_folga_nas_bordas_do_periodo() -> None:
    gabarito = [incidente("recirculacao", "A-01", 2, 4)]

    # Começou 20 min depois do fim: dentro da folga de 30 min.
    assert avaliar("s", resultado(deteccao("recirculacao", "A-01", 4.33, 5)), gabarito).falsos == []
    # Uma hora depois: já não encosta.
    assert (
        len(avaliar("s", resultado(deteccao("recirculacao", "A-01", 5, 6)), gabarito).falsos) == 1
    )


def test_tipo_errado_no_lugar_certo_vira_confusao() -> None:
    gabarito = [incidente("sensor_deriva", "A-01/entrada-topo", 2, 8)]
    a = avaliar("s", resultado(deteccao("recirculacao", "A-01", 3, 8)), gabarito)

    assert a.perdidos == gabarito
    assert len(a.confusoes) == 1
    assert a.confusoes[0][1].tipo == "sensor_deriva"


def test_incidente_invisivel_fica_fora_do_recall() -> None:
    gabarito = [
        incidente("sensor_picos", "A-01/saida", 2, 3, visivel=False),
        incidente("sensor_picos", "A-02/saida", 2, 3),
    ]
    a = avaliar("s", resultado(deteccao("sensor_picos", "A-02/saida", 2, 3)), gabarito)

    placar = a.por_tipo["sensor_picos"]
    assert (placar.incidentes, placar.invisiveis, placar.recall) == (1, 1, 1.0)
    assert a.perdidos == []
    assert [i.alvo for i in a.invisiveis] == ["A-01/saida"]


def test_gabarito_marca_defeitos_que_nao_afetaram_leituras(diretorio: Path) -> None:
    gabarito = ler_gabarito(diretorio)

    assert len(gabarito) == 8
    assert all(i.visivel for i in gabarito)
    assert all(i.inicio.tzinfo is not None for i in gabarito)


def test_conjunto_e_relatorio(diretorio: Path) -> None:
    conjunto = avaliar_conjunto([diretorio], "teste")
    texto = gerar_relatorio([conjunto])

    assert conjunto["total"]["recall"] == 1.0
    assert conjunto["simulacoes"][0]["parametros_ajustados"]["alcance_retorno_m"] > 0
    assert "## Teste: rodadas uma única vez" in texto
    assert "| Falha de CRAC | 1 | 1 | 1 de 1 | 100% | 100% | 100% |" in texto
    assert "Nenhum incidente perdido e nenhum alerta falso." in texto


def test_cli_detectar_avaliar_e_relatorio(diretorio: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    deteccoes = tmp_path / "deteccoes.json"
    resultado_json = tmp_path / "teste.json"
    relatorio = tmp_path / "DETECCAO.md"

    saida = runner.invoke(app, ["detectar", str(diretorio), "--json", str(deteccoes)])
    assert saida.exit_code == 0, saida.output
    assert "falha_crac" in saida.output
    assert "8 detecções" in saida.output
    assert len(json.loads(deteccoes.read_text(encoding="utf-8"))["deteccoes"]) == 8

    saida = runner.invoke(app, ["detectar", str(diretorio), "--tipo", "sensor_picos"])
    assert "1 detecções" in saida.output

    saida = runner.invoke(
        app, ["avaliar-deteccao", str(diretorio), "--resultado", str(resultado_json)]
    )
    assert saida.exit_code == 0, saida.output
    assert "8/8 incidentes detectados" in saida.output

    saida = runner.invoke(
        app, ["relatorio-deteccao", str(resultado_json), "--saida", str(relatorio)]
    )
    assert saida.exit_code == 0, saida.output
    assert relatorio.read_text(encoding="utf-8").startswith("# Detecção de anomalias")
