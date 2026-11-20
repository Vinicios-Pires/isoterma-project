from pathlib import Path

import pytest

from isoterma.motor import ConsultaExpirou, ConsultaInvalida, ConsultaRecusada, Hall
from isoterma.motor.sql_seguro import validar


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select * from leituras limit 3",
        "WITH x AS (SELECT 1 AS a) SELECT * FROM x",
        "FROM racks",
        "SELECT 1;",
    ],
)
def test_aceita_consultas_de_leitura(sql: str) -> None:
    assert validar(sql) == sql


@pytest.mark.parametrize(
    ("sql", "motivo"),
    [
        ("DROP VIEW leituras", "DROP"),
        ("INSERT INTO racks VALUES (1)", "INSERT"),
        ("COPY (SELECT 1) TO 'x.csv'", "COPY"),
        ("ATTACH 'outro.db'", "ATTACH"),
        ("SET enable_external_access = true", "SET"),
        ("PRAGMA database_list", "PRAGMA"),
        ("SELECT 1; DROP VIEW leituras", "exatamente um"),
        ("", "exatamente um"),
    ],
)
def test_recusa_o_que_nao_e_um_unico_select(sql: str, motivo: str) -> None:
    with pytest.raises(ConsultaRecusada, match=motivo):
        validar(sql)


def test_sql_malformado_e_invalido() -> None:
    with pytest.raises(ConsultaInvalida):
        validar("SELEC * FORM racks")


def test_limite_de_linhas(hall: Hall) -> None:
    resultado = hall.consultar("SELECT * FROM leituras", limite=7)

    assert resultado.tabela.num_rows == 7
    assert resultado.truncado


def test_resultado_pequeno_nao_e_truncado(hall: Hall) -> None:
    resultado = hall.consultar("SELECT rack_id FROM racks ORDER BY rack_id DESC")

    assert not resultado.truncado
    assert resultado.linhas()[0] == {"rack_id": "B-05"}


def test_nao_le_arquivos_fora_da_simulacao(hall: Hall, tmp_path: Path) -> None:
    segredo = tmp_path / "segredo.csv"
    segredo.write_text("senha\n123\n", encoding="utf-8")

    with pytest.raises(ConsultaInvalida, match="Permission"):
        hall.consultar(f"SELECT * FROM read_csv('{segredo.as_posix()}')")


def test_nao_acessa_a_rede(hall: Hall) -> None:
    with pytest.raises(ConsultaInvalida, match="Permission"):
        hall.consultar("SELECT * FROM read_parquet('https://example.com/dados.parquet')")


def test_erro_de_sql_explica_o_problema(hall: Hall) -> None:
    with pytest.raises(ConsultaInvalida, match="coluna_que_nao_existe"):
        hall.consultar("SELECT coluna_que_nao_existe FROM racks")


def test_consulta_demorada_e_cancelada(hall: Hall) -> None:
    with pytest.raises(ConsultaExpirou, match="cancelada"):
        hall.consultar("SELECT count(*) FROM range(100000000000)", tempo_max_s=0.2)


def test_valores_float32_saem_arredondados(hall: Hall) -> None:
    valores = hall.consultar("SELECT valor FROM leituras WHERE valor IS NOT NULL LIMIT 100")

    assert all(v == round(v, 2) for (v,) in [tuple(r.values()) for r in valores.linhas()])
