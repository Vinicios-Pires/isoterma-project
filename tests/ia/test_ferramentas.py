import pytest

from isoterma.ia.ferramentas import FERRAMENTAS, CaixaDeFerramentas, esquema_estrito
from isoterma.ia.tipos import ChamadaFerramenta
from isoterma.motor import Hall


def _chamar(hall: Hall, nome: str, **argumentos: object):
    return CaixaDeFerramentas(hall).executar(ChamadaFerramenta("id-1", nome, argumentos))


@pytest.mark.parametrize("ferramenta", FERRAMENTAS, ids=lambda f: f.nome)
def test_esquema_e_estrito(ferramenta) -> None:
    esquema = esquema_estrito(ferramenta.argumentos)

    assert esquema["type"] == "object"
    assert esquema["additionalProperties"] is False
    assert set(esquema["required"]) == set(esquema["properties"])
    assert "title" not in str(esquema)


def test_resumo(hall: Hall) -> None:
    resultado, execucao = _chamar(hall, "resumo", inicio=None, fim=None)

    assert not resultado.erro
    assert execucao is not None
    assert '"racks": 10' in resultado.conteudo


def test_fora_da_faixa_em_horario_local(hall: Hall) -> None:
    # A falha do CRAC-01 vai das 02:00 às 04:00 UTC, ou seja, 23:00 a 01:00 em Brasília.
    resultado, _ = _chamar(hall, "fora_da_faixa", inicio="2026-10-31T22:00", fim="2026-11-01T02:00")

    assert not resultado.erro
    assert "A-0" in resultado.conteudo
    assert "2026-10-31 23:" in resultado.conteudo  # horários devolvidos no fuso do hall


def test_mapa_e_serie(hall: Hall) -> None:
    mapa, _ = _chamar(hall, "mapa_termico", instante=None, tipo="potencia_kw", altura=None)
    serie, execucao = _chamar(hall, "serie", alvo="CRAC-01", inicio=None, fim=None, pontos=12)

    assert not mapa.erro and "rack_id" in mapa.conteudo
    assert not serie.erro
    assert execucao is not None and execucao.linhas == 2 * 12


def test_sql_registra_a_consulta(hall: Hall) -> None:
    resultado, execucao = _chamar(hall, "consultar_sql", sql="SELECT count(*) AS n FROM racks")

    assert resultado.conteudo == "n\n10"
    assert execucao is not None and execucao.sql == "SELECT count(*) AS n FROM racks"


def test_sql_avisa_quando_trunca(hall: Hall) -> None:
    resultado, _ = _chamar(hall, "consultar_sql", sql="SELECT * FROM leituras")

    assert "(mostrando 50 de mais de 50 linhas)" in resultado.conteudo


@pytest.mark.parametrize(
    ("nome", "argumentos", "mensagem"),
    [
        ("nao_existe", {}, "não existe"),
        ("resumo", {"inicio": None}, "fim: Field required"),
        ("resumo", {"inicio": None, "fim": None, "extra": 1}, "extra"),
        ("resumo", {"inicio": "ontem", "fim": None}, "Data inválida"),
        ("serie", {"alvo": "Z-99", "inicio": None, "fim": None, "pontos": None}, "Z-99"),
        ("consultar_sql", {"sql": "DROP VIEW racks"}, "Só consultas SELECT"),
    ],
)
def test_erros_viram_resultado_para_o_modelo(
    hall: Hall, nome: str, argumentos: dict, mensagem: str
) -> None:
    resultado, execucao = CaixaDeFerramentas(hall).executar(
        ChamadaFerramenta("x", nome, argumentos)
    )

    assert resultado.erro
    assert execucao is None
    assert mensagem in resultado.conteudo


def test_gabarito_fica_escondido_da_ia(hall: Hall) -> None:
    arquivo = (hall.diretorio / "incidentes.parquet").as_posix()

    pela_view, _ = _chamar(hall, "consultar_sql", sql="SELECT * FROM incidentes")
    pelo_arquivo, _ = _chamar(hall, "consultar_sql", sql=f"SELECT * FROM read_parquet('{arquivo}')")

    assert pela_view.erro and "incidentes" in pela_view.conteudo
    assert pelo_arquivo.erro and "Permission" in pelo_arquivo.conteudo
    assert "incidentes" not in hall.esquema()


def test_hall_comum_continua_vendo_o_gabarito(hall: Hall) -> None:
    with Hall(hall.diretorio) as completo:
        assert completo.consultar("SELECT count(*) AS n FROM incidentes").linhas()[0]["n"] > 0
