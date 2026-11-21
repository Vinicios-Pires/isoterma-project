from pathlib import Path

import pytest
from typer.testing import CliRunner

from isoterma.cli import app
from isoterma.ia.avaliacao import (
    Questao,
    ResultadoAvaliacao,
    avaliar,
    corrigir,
    extrair_resposta,
    gerar_questoes,
    gerar_relatorio,
)
from isoterma.ia.provedores.falso import Historico, ProvedorFalso
from isoterma.ia.tipos import Turno, Uso

DESCOBERTA = Questao(
    "d",
    "descoberta",
    "",
    "",
    "incidentes",
    [
        {"categoria": "falha_crac", "alvos": ["CRAC-02"]},
        {"categoria": "defeito_sensor", "alvos": ["G-07/entrada-topo", "G-07"]},
    ],
    0.7,
)


@pytest.fixture(scope="module")
def questoes(diretorio: Path) -> list[Questao]:
    return gerar_questoes(diretorio)


def test_v2_tem_as_quatro_categorias(questoes: list[Questao]) -> None:
    categorias = {q.categoria for q in questoes}
    por_id = {q.id: q for q in questoes}

    assert categorias == {"fatos", "investigacao", "diagnostico", "descoberta"}
    assert por_id["racks"].esperado == 10
    assert por_id["diagnostico_falha_crac"].esperado == "falha_crac"
    assert por_id["diagnostico_sensor_congelado"].esperado == "defeito_sensor"
    assert sum(q.esperado == "normal" for q in questoes) == 3


def test_v2_pergunta_sempre_pelo_rack_sem_entregar_a_causa(questoes: list[Questao]) -> None:
    diagnosticos = [q for q in questoes if q.categoria == "diagnostico"]

    assert all(q.pergunta.startswith("Houve algo anormal no rack ") for q in diagnosticos)
    assert not any("sensor" in q.pergunta or "CRAC" in q.pergunta for q in diagnosticos)


def test_v2_falha_de_crac_pergunta_pelo_rack_da_zona(questoes: list[Questao]) -> None:
    falha = next(q for q in questoes if q.id == "diagnostico_falha_crac")

    # A falha programada é do CRAC-01, que fica de frente para a fileira A.
    assert "rack A-" in falha.pergunta


def test_v2_descoberta_lista_os_incidentes_de_um_dia(questoes: list[Questao]) -> None:
    descoberta = next(q for q in questoes if q.id == "descoberta")

    assert descoberta.tipo == "incidentes"
    assert 2 <= len(descoberta.esperado) <= 8
    assert all({"categoria", "alvos"} == set(i) for i in descoberta.esperado)


def test_v1_continua_disponivel(diretorio: Path) -> None:
    v1 = gerar_questoes(diretorio, versao="v1")

    assert {q.categoria for q in v1} == {"fatos", "investigacao", "diagnostico"}
    assert any(q.pergunta.startswith("O que aconteceu com o sensor") for q in v1)


def test_racks_quentes_vem_da_zona_do_crac_que_falhou(questoes: list[Questao]) -> None:
    quentes = next(q for q in questoes if q.id == "racks_quentes")

    assert quentes.esperado
    assert all(rack.startswith("A-") for rack in quentes.esperado)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Tudo certo.\nRESPOSTA: 42", "42"),
        ("**RESPOSTA:** CRAC-02", "CRAC-02"),
        ("resposta: a\nRESPOSTA: b", "b"),
        ("sem a linha", None),
    ],
)
def test_extrair_resposta(texto: str, esperado: str | None) -> None:
    assert extrair_resposta(texto) == esperado


@pytest.mark.parametrize(
    ("questao", "resposta", "acerta"),
    [
        (Questao("n", "fatos", "", "", "numero", 1020.0, 10), "RESPOSTA: 1.020,4 kW", True),
        (Questao("n", "fatos", "", "", "numero", 1020.0, 10), "RESPOSTA: 1020", True),
        (Questao("n", "fatos", "", "", "numero", 20.21, 0.15), "RESPOSTA: 20,3", True),
        (Questao("n", "fatos", "", "", "numero", 20.21, 0.15), "RESPOSTA: 21", False),
        (Questao("t", "fatos", "", "", "texto", "CRAC-04", 0), "RESPOSTA: `crac-04`.", True),
        (
            Questao("o", "diagnostico", "", "", "opcao", "defeito_sensor", 0),
            "RESPOSTA: defeito sensor",
            True,
        ),
        (Questao("o", "diagnostico", "", "", "opcao", "normal", 0), "RESPOSTA: falha_crac", False),
        (
            Questao("c", "investigacao", "", "", "conjunto", ["A-01", "A-02"], 1.0),
            "RESPOSTA: A-02, A-01",
            True,
        ),
        (
            Questao("c", "investigacao", "", "", "conjunto", ["A-01", "A-02"], 1.0),
            "RESPOSTA: A-01",
            False,
        ),
        (
            Questao(
                "c", "investigacao", "", "", "conjunto", [f"A-{i:02d}" for i in range(1, 8)], 0.85
            ),
            "RESPOSTA: A-01, A-02, A-03, A-04, A-05, A-06 e A-07",
            True,
        ),
        (Questao("h", "investigacao", "", "", "horario", "02:11", 3), "RESPOSTA: 02h13", True),
        (Questao("h", "investigacao", "", "", "horario", "02:11", 3), "RESPOSTA: 02:20", False),
        (Questao("x", "fatos", "", "", "numero", 1, 0), "Não sei.", False),
        (DESCOBERTA, "RESPOSTA: falha_crac:CRAC-02; defeito_sensor:G-07", True),
        (DESCOBERTA, "RESPOSTA: defeito sensor:G-07/entrada-topo; falha_crac:crac-02", True),
        (DESCOBERTA, "RESPOSTA: falha_crac:CRAC-02", False),  # F1 0,67
        (DESCOBERTA, "RESPOSTA: falha_crac:CRAC-01; defeito_sensor:G-07", False),
        (DESCOBERTA, "RESPOSTA: nenhum", False),
        (
            Questao("d", "descoberta", "", "", "incidentes", [], 0.7),
            "RESPOSTA: nenhum",
            True,
        ),
    ],
)
def test_corrigir(questao: Questao, resposta: str, acerta: bool) -> None:
    assert corrigir(questao, resposta)[0] is acerta


def _oraculo(questoes: list[Questao], certo: bool) -> ProvedorFalso:
    """Responde de primeira, com a resposta esperada (ou uma errada), sem chamar ferramentas."""
    por_pergunta = {q.pergunta: q for q in questoes}

    def responder(historico: Historico) -> Turno:
        questao = por_pergunta[historico.perguntas[-1]]
        valor = questao.esperado
        if questao.tipo == "incidentes":
            valor = "; ".join(f"{i['categoria']}:{i['alvos'][0]}" for i in valor)
        elif isinstance(valor, list):
            valor = ", ".join(valor)
        return Turno(
            f"Resposta.\nRESPOSTA: {valor if certo else 'nao sei'}", uso=Uso(entrada=10, saida=5)
        )

    return ProvedorFalso(responder, modelo="claude-haiku-5-5" if certo else "errado")


def test_avaliacao_mede_acertos_e_gera_relatorio(
    diretorio: Path, questoes: list[Questao], tmp_path: Path
) -> None:
    resultado = avaliar(
        diretorio, [_oraculo(questoes, True), _oraculo(questoes, False)], questoes=questoes
    )
    arquivo = tmp_path / "r.json"
    resultado.salvar(arquivo)
    carregado = ResultadoAvaliacao.carregar(arquivo)

    certos = [t for t in carregado.tentativas if t.modelo == "claude-haiku-5-5"]
    errados = [t for t in carregado.tentativas if t.modelo == "errado"]
    assert all(t.acertou for t in certos)
    assert not any(t.acertou for t in errados)
    assert all(t.custo_usd is not None for t in certos)

    relatorio = gerar_relatorio(carregado)
    assert f"**{len(questoes)}/{len(questoes)}**" in relatorio
    assert "não estimado" in relatorio  # o modelo "errado" não tem preço conhecido
    assert "| Descoberta |" in relatorio


def test_relatorio_mostra_as_duas_versoes_com_a_mais_nova_primeiro(diretorio: Path) -> None:
    resultados = []
    for versao in ("v1", "v2"):
        questoes = gerar_questoes(diretorio, versao=versao)[:2]
        resultados.append(
            avaliar(diretorio, [_oraculo(questoes, True)], versao=versao, questoes=questoes)
        )

    relatorio = gerar_relatorio(resultados)

    assert relatorio.index("## Versão 2") < relatorio.index("## Versão 1")
    assert "mantida como registro" in relatorio


def test_resultado_antigo_sem_versao_e_lido_como_v1(tmp_path: Path) -> None:
    arquivo = tmp_path / "antigo.json"
    arquivo.write_text(
        '{"simulacao": "demo", "gerado_em": "2026-11-21T00:00:00+00:00", "isoterma": "0.1.0", '
        '"questoes": [], "tentativas": []}',
        encoding="utf-8",
    )

    assert ResultadoAvaliacao.carregar(arquivo).versao == "v1"


def test_cli_perguntar_e_avaliar_com_o_provedor_falso(diretorio: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    json_saida = tmp_path / "avaliacao.json"

    pergunta = runner.invoke(
        app, ["perguntar", str(diretorio), "Como está o hall?", "--llm", "falso"]
    )
    avaliacao = runner.invoke(
        app,
        [
            "avaliar-ia",
            str(diretorio),
            "--llm",
            "falso",
            "--amostra",
            "2",
            "--resultado",
            str(json_saida),
        ],
    )
    relatorio = runner.invoke(
        app, ["relatorio-ia", str(json_saida), "--saida", str(tmp_path / "A.md")]
    )

    assert pergunta.exit_code == 0, pergunta.output
    assert "→ resumo()" in pergunta.output
    assert "provedor de demonstração" in pergunta.output
    assert avaliacao.exit_code == 0, avaliacao.output
    assert "2 perguntas (v2) × 1 provedores" in avaliacao.output
    assert relatorio.exit_code == 0, relatorio.output
    assert (tmp_path / "A.md").exists()


def test_cli_explica_configuracao_errada(diretorio: Path) -> None:
    resultado = CliRunner().invoke(app, ["perguntar", str(diretorio), "x", "--llm", "openai"])

    assert resultado.exit_code == 1
    assert "openai:<modelo>" in resultado.output
