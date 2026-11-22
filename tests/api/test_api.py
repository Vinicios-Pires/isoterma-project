import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from isoterma.api import ConfigApi, criar_app
from isoterma.api.app import Limitador
from isoterma.cli import app as cli
from isoterma.ia.provedores import ErroProvedor
from isoterma.ia.provedores.falso import Historico, ProvedorFalso
from isoterma.ia.tipos import ChamadaFerramenta, Parada, Turno

# A falha do CRAC-01 vai das 02:00 às 04:00 UTC do primeiro dia.
DURANTE_A_FALHA = "2026-11-01T03:50:00Z"


@pytest.fixture
def cliente(dados: Path) -> Iterator[TestClient]:
    aplicacao = criar_app(ConfigApi(dados, llm="falso"))
    with TestClient(aplicacao) as c:
        yield c
    aplicacao.state.catalogo.fechar()


def _eventos(resposta) -> list[tuple[str, dict]]:
    """Lê o corpo SSE como pares (evento, dados)."""
    eventos, nome = [], None
    for linha in resposta.text.splitlines():
        if linha.startswith("event:"):
            nome = linha.split(":", 1)[1].strip()
        elif linha.startswith("data:"):
            eventos.append((nome, json.loads(linha.split(":", 1)[1])))
    return eventos


# --- consultas -----------------------------------------------------------------------------


def test_saude_e_simulacoes(cliente: TestClient) -> None:
    saude = cliente.get("/api/saude").json()
    simulacoes = cliente.get("/api/simulacoes").json()

    assert saude == {"status": "ok", "versao": "0.1.0", "simulacoes": 1, "llm": "falso"}
    assert [s["nome"] for s in simulacoes] == ["hall"]  # "outra-coisa" não é simulação
    assert simulacoes[0]["racks"] == 10
    assert simulacoes[0]["camadas"] == ["leituras", "agregados_hora"]


def test_planta(cliente: TestClient) -> None:
    planta = cliente.get("/api/hall/planta").json()

    assert len(planta["racks"]) == 10 and len(planta["cracs"]) == 2
    assert planta["racks"][0]["rack_id"] == "A-01"
    assert planta["largura_m"] > 0 and planta["profundidade_m"] > 0


def test_resumo_com_e_sem_janela(cliente: TestClient) -> None:
    inteiro = cliente.get("/api/hall/resumo").json()
    janela = cliente.get(
        "/api/hall/resumo", params={"inicio": "2026-11-01T00:00Z", "fim": "2026-11-01T06:00Z"}
    ).json()

    assert inteiro["leituras"] == 1440 * 54
    assert janela["leituras"] == 360 * 54
    assert set(inteiro["por_tipo"]) >= {"temp_entrada", "temp_saida", "potencia_kw"}


def test_mapa_durante_a_falha(cliente: TestClient) -> None:
    mapa = cliente.get("/api/hall/mapa", params={"instante": DURANTE_A_FALHA}).json()

    acima = [r for r in mapa["racks"] if r["faixa"] == "acima"]
    assert mapa["tipo"] == "temp_entrada" and mapa["instante"] == "2026-11-01T03:50:00Z"
    assert acima and all(r["zona_crac"] == "CRAC-01" for r in acima)


def test_fora_da_faixa_e_serie(cliente: TestClient) -> None:
    fora = cliente.get("/api/hall/fora-da-faixa").json()
    serie = cliente.get("/api/hall/serie", params={"alvo": "CRAC-01", "pontos": 24}).json()

    assert any(r["minutos_acima"] > 0 for r in fora)  # a falha do CRAC-01
    assert any(r["minutos_abaixo"] > 0 for r in fora)  # a super-refrigeração do CRAC-02
    assert all(r["minutos_acima"] + r["minutos_abaixo"] > 0 for r in fora)
    assert serie["alvo"] == "CRAC-01"
    assert {p["sensor"] for p in serie["pontos"]} == {"CRAC-01/insuflamento", "CRAC-01/retorno"}


def test_gabarito(cliente: TestClient) -> None:
    incidentes = cliente.get("/api/hall/gabarito").json()

    assert len(incidentes) == 8
    assert {"tipo", "alvo", "inicio", "fim", "descricao"} <= set(incidentes[0])


@pytest.mark.parametrize(
    ("rota", "parametros", "codigo"),
    [
        ("/api/nada/resumo", {}, 404),
        ("/api/outra-coisa/resumo", {}, 404),
        ("/api/..%2F..%2Fetc/resumo", {}, 404),
        ("/api/hall/mapa", {"instante": "2030-01-01T00:00"}, 400),
        ("/api/hall/mapa", {"tipo": "umidade"}, 422),
        ("/api/hall/resumo", {"inicio": "2026-11-01T06:00Z", "fim": "2026-11-01T01:00Z"}, 400),
        ("/api/hall/serie", {"alvo": "Z-99"}, 400),
        ("/api/hall/serie", {"alvo": "A-01", "pontos": 1}, 422),
        ("/api/hall/serie", {}, 422),
    ],
)
def test_erros_viram_respostas_http(
    cliente: TestClient, rota: str, parametros: dict, codigo: int
) -> None:
    resposta = cliente.get(rota, params=parametros)

    assert resposta.status_code == codigo
    assert "detail" in resposta.json()


def test_mensagem_de_erro_de_dominio(cliente: TestClient) -> None:
    resposta = cliente.get("/api/hall/serie", params={"alvo": "Z-99"})

    assert "Z-99" in resposta.json()["detail"]


def test_cors_libera_o_vite_local(cliente: TestClient) -> None:
    resposta = cliente.get("/api/saude", headers={"Origin": "http://localhost:5173"})

    assert resposta.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_openapi_documenta_as_rotas(cliente: TestClient) -> None:
    esquema = cliente.get("/openapi.json").json()
    rotas, modelos = esquema["paths"], esquema["components"]["schemas"]

    assert "/api/{simulacao}/perguntar" in rotas
    assert "/api/{simulacao}/mapa" in rotas
    # Os eventos do streaming entram no esquema para o front gerar os tipos deles.
    assert {"EventoPasso", "EventoResposta", "EventoErro"} <= set(modelos)


# --- IA -------------------------------------------------------------------------------------


def test_perguntar_transmite_os_passos_e_a_resposta(cliente: TestClient) -> None:
    resposta = cliente.post("/api/hall/perguntar", json={"pergunta": "Como está o hall?"})

    eventos = _eventos(resposta)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/event-stream")
    assert [nome for nome, _ in eventos] == ["passo", "resposta"]
    assert eventos[0][1]["ferramenta"] == "resumo" and eventos[0][1]["erro"] is False
    assert "demonstração" in eventos[1][1]["texto"]
    assert eventos[1][1]["provedor"] == "falso"


def test_erro_do_provedor_no_meio_vira_evento(dados: Path) -> None:
    def roteiro(historico: Historico) -> Turno:
        if historico.turnos == 1:
            return Turno(
                "",
                (ChamadaFerramenta("1", "resumo", {"inicio": None, "fim": None}),),
                parada=Parada.FERRAMENTAS,
            )
        raise ErroProvedor("A chave da API foi recusada")

    aplicacao = criar_app(
        ConfigApi(dados, llm="roteiro"), fabrica_provedor=lambda _: ProvedorFalso(roteiro)
    )
    with TestClient(aplicacao) as c:
        eventos = _eventos(c.post("/api/hall/perguntar", json={"pergunta": "x"}))

    assert [nome for nome, _ in eventos] == ["passo", "erro"]
    assert "recusada" in eventos[1][1]["mensagem"]


def test_ia_desligada(dados: Path) -> None:
    with TestClient(criar_app(ConfigApi(dados))) as c:
        resposta = c.post("/api/hall/perguntar", json={"pergunta": "x"})

    assert resposta.status_code == 503
    assert "desligada" in resposta.json()["detail"]


def test_provedor_mal_configurado(dados: Path) -> None:
    with TestClient(criar_app(ConfigApi(dados, llm="openai"))) as c:
        resposta = c.post("/api/hall/perguntar", json={"pergunta": "x"})

    assert resposta.status_code == 503
    assert "openai:<modelo>" in resposta.json()["detail"]


def test_pergunta_vazia_e_rejeitada(cliente: TestClient) -> None:
    assert cliente.post("/api/hall/perguntar", json={"pergunta": ""}).status_code == 422


def test_limite_de_perguntas_por_ip(dados: Path) -> None:
    with TestClient(criar_app(ConfigApi(dados, llm="falso", perguntas_por_hora=2))) as c:
        codigos = [
            c.post("/api/hall/perguntar", json={"pergunta": "x"}).status_code for _ in range(3)
        ]

    assert codigos == [200, 200, 429]


def test_teto_de_gasto_diario(dados: Path) -> None:
    with TestClient(criar_app(ConfigApi(dados, llm="falso", teto_diario_usd=0))) as c:
        resposta = c.post("/api/hall/perguntar", json={"pergunta": "x"})

    assert resposta.status_code == 429
    assert "gasto diário" in resposta.json()["detail"]


def test_limitador_usa_o_ip_do_proxy_quando_configurado(dados: Path) -> None:
    config = ConfigApi(dados, llm="falso", perguntas_por_hora=1, confiar_proxy=True)
    with TestClient(criar_app(config)) as c:
        primeiro = c.post(
            "/api/hall/perguntar", json={"pergunta": "x"}, headers={"X-Forwarded-For": "1.1.1.1"}
        )
        outro_ip = c.post(
            "/api/hall/perguntar", json={"pergunta": "x"}, headers={"X-Forwarded-For": "2.2.2.2"}
        )
        repetido = c.post(
            "/api/hall/perguntar", json={"pergunta": "x"}, headers={"X-Forwarded-For": "1.1.1.1"}
        )

    assert (primeiro.status_code, outro_ip.status_code, repetido.status_code) == (200, 200, 429)


def test_limitador_libera_depois_de_uma_hora(monkeypatch: pytest.MonkeyPatch) -> None:
    relogio = [0.0]
    monkeypatch.setattr("isoterma.api.app.time.monotonic", lambda: relogio[0])
    limitador = Limitador(perguntas_por_hora=1, teto_diario_usd=10)

    assert limitador.reservar("ip") is None
    assert limitador.reservar("ip") is not None
    relogio[0] = 3601
    assert limitador.reservar("ip") is None


def test_limitador_soma_o_gasto() -> None:
    limitador = Limitador(perguntas_por_hora=100, teto_diario_usd=0.01)
    limitador.registrar_custo(0.02)

    assert "gasto diário" in (limitador.reservar("ip") or "")


# --- CLI ------------------------------------------------------------------------------------


def test_servir_monta_a_app_com_a_configuracao(
    dados: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[dict] = []
    monkeypatch.setattr(
        "uvicorn.run", lambda app, **kwargs: chamadas.append({"app": app, **kwargs})
    )
    monkeypatch.delenv("ISOTERMA_LLM", raising=False)

    resultado = CliRunner().invoke(
        cli,
        [
            "servir",
            str(dados),
            "--porta",
            "8123",
            "--llm",
            "falso",
            "--origem",
            "https://isoterma.dev",
        ],
    )

    assert resultado.exit_code == 0, resultado.output
    assert "Simulações: hall" in resultado.output
    assert chamadas[0]["port"] == 8123 and chamadas[0]["host"] == "127.0.0.1"
    with TestClient(chamadas[0]["app"]) as c:
        assert c.get("/api/saude").json()["llm"] == "falso"
        liberado = c.get("/api/saude", headers={"Origin": "https://isoterma.dev"})
        assert liberado.headers["access-control-allow-origin"] == "https://isoterma.dev"
