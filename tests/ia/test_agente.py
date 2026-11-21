from pathlib import Path

import pytest

from isoterma.ia.agente import Agente, Passo
from isoterma.ia.provedores.falso import Historico, ProvedorFalso
from isoterma.ia.tipos import ChamadaFerramenta, Parada, Turno, Uso
from isoterma.motor import Hall


def _pede(*chamadas: tuple[str, dict], texto: str = "") -> Turno:
    return Turno(
        texto,
        tuple(ChamadaFerramenta(f"c{i}", nome, args) for i, (nome, args) in enumerate(chamadas)),
        Uso(entrada=100, saida=10),
        Parada.FERRAMENTAS,
    )


def test_agente_chama_ferramentas_e_responde(hall: Hall) -> None:
    provedor = ProvedorFalso(
        [
            _pede(("resumo", {"inicio": None, "fim": None}), texto="Vou olhar."),
            _pede(("consultar_sql", {"sql": "SELECT count(*) AS n FROM racks"})),
            Turno("São 10 racks.", uso=Uso(entrada=200, saida=20, cache_leitura=50)),
        ]
    )
    vistos: list[Passo] = []

    resposta = Agente(hall, provedor).perguntar("Quantos racks?", ao_passo=vistos.append)

    assert resposta.concluida
    assert resposta.texto == "São 10 racks."
    assert resposta.turnos == 3
    assert [p.chamada.nome for p in resposta.passos] == ["resumo", "consultar_sql"]
    assert vistos == resposta.passos
    assert resposta.passos[1].sql == "SELECT count(*) AS n FROM racks"
    assert resposta.uso == Uso(entrada=400, saida=40, cache_leitura=50)


def test_erro_de_ferramenta_volta_para_o_modelo(hall: Hall) -> None:
    provedor = ProvedorFalso(
        [_pede(("consultar_sql", {"sql": "SELECT nada FROM racks"})), Turno("Corrigi.")]
    )

    resposta = Agente(hall, provedor).perguntar("x")

    historico = provedor.conversas[0].historico
    assert historico.resultados[0].erro
    assert "nada" in historico.resultados[0].conteudo
    assert resposta.passos[0].resultado.erro


def test_varias_chamadas_no_mesmo_turno_voltam_juntas(hall: Hall) -> None:
    provedor = ProvedorFalso(
        [
            _pede(
                ("resumo", {"inicio": None, "fim": None}),
                ("mapa_termico", {"instante": None, "tipo": None, "altura": None}),
            ),
            Turno("ok"),
        ]
    )

    Agente(hall, provedor).perguntar("x")

    assert [r.nome for r in provedor.conversas[0].historico.resultados] == [
        "resumo",
        "mapa_termico",
    ]


def test_limite_de_turnos(hall: Hall) -> None:
    def sempre_pede(_: Historico) -> Turno:
        return _pede(("resumo", {"inicio": None, "fim": None}))

    resposta = Agente(hall, ProvedorFalso(sempre_pede), max_turnos=3).perguntar("x")

    assert resposta.parada is Parada.LIMITE
    assert resposta.turnos == 3
    assert "3 turnos" in resposta.detalhe


def test_recusa_e_repassada(hall: Hall) -> None:
    provedor = ProvedorFalso([Turno("", parada=Parada.RECUSA, detalhe="cyber")])

    resposta = Agente(hall, provedor).perguntar("x")

    assert resposta.parada is Parada.RECUSA
    assert resposta.detalhe == "cyber"
    assert not resposta.passos


def test_instrucoes_descrevem_o_hall_sem_o_gabarito(hall: Hall) -> None:
    provedor = ProvedorFalso([Turno("ok")])

    Agente(hall, provedor).perguntar("x", instrucao_extra="RESPOSTA: no fim")

    sistema = provedor.conversas[0].historico.sistema
    assert "10 racks em 2 fileiras (A a B)" in sistema
    assert "CRAC-01, CRAC-02" in sistema
    assert "America/Sao_Paulo" in sistema and "02:00 local = 05:00 UTC" in sistema
    assert "incidentes:" not in sistema
    assert sistema.endswith("RESPOSTA: no fim")
    assert len(provedor.conversas[0].historico.ferramentas) == 5


def test_agente_exige_hall_sem_gabarito(diretorio: Path) -> None:
    with Hall(diretorio) as completo, pytest.raises(ValueError, match="ocultar_gabarito"):
        Agente(completo, ProvedorFalso())


def test_custo_estimado_para_modelos_conhecidos(hall: Hall) -> None:
    provedor = ProvedorFalso(
        [Turno("ok", uso=Uso(entrada=1_000_000, saida=1_000_000))], modelo="claude-haiku-5-5"
    )

    resposta = Agente(hall, provedor).perguntar("x")

    assert resposta.custo_usd == pytest.approx(0.60)
    assert Agente(hall, ProvedorFalso([Turno("ok")])).perguntar("x").custo_usd is None
