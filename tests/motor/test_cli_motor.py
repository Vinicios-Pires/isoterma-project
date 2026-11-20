from pathlib import Path

from typer.testing import CliRunner

from isoterma.cli import app

runner = CliRunner()


def test_agregar(diretorio: Path) -> None:
    resultado = runner.invoke(app, ["agregar", str(diretorio)])

    assert resultado.exit_code == 0, resultado.output
    assert "agregados por minuto: 77.760 linhas" in resultado.output
    assert "agregados por hora: 1.296 linhas" in resultado.output


def test_resumo(diretorio: Path) -> None:
    resultado = runner.invoke(app, ["resumo", str(diretorio)])

    assert resultado.exit_code == 0, resultado.output
    assert "10 racks, 2 CRACs, 54 sensores" in resultado.output
    assert "Faixa ASHRAE" in resultado.output


def test_mapa_durante_a_falha(diretorio: Path) -> None:
    # 00:50 em Brasília = 03:50 UTC, no meio da falha do CRAC-01.
    resultado = runner.invoke(app, ["mapa", str(diretorio), "--instante", "2026-11-01T00:50"])

    assert resultado.exit_code == 0, resultado.output
    assert "  A " in resultado.output
    assert "acima de 27 °C" in resultado.output
    assert "Mais quentes: A-" in resultado.output


def test_mapa_de_potencia(diretorio: Path) -> None:
    resultado = runner.invoke(app, ["mapa", str(diretorio), "--tipo", "potencia_kw"])

    assert resultado.exit_code == 0, resultado.output
    assert "kW" in resultado.output


def test_mapa_fora_do_periodo(diretorio: Path) -> None:
    resultado = runner.invoke(app, ["mapa", str(diretorio), "--instante", "2030-01-01"])

    assert resultado.exit_code == 1
    assert "fora da simulação" in resultado.output


def test_consultar(diretorio: Path) -> None:
    resultado = runner.invoke(
        app, ["consultar", str(diretorio), "SELECT crac_id FROM cracs ORDER BY 1"]
    )

    assert resultado.exit_code == 0, resultado.output
    assert "CRAC-01" in resultado.output
    assert "2 linhas" in resultado.output


def test_consultar_recusa_comandos_que_alteram(diretorio: Path) -> None:
    resultado = runner.invoke(app, ["consultar", str(diretorio), "DROP VIEW racks"])

    assert resultado.exit_code == 1
    assert "Só consultas SELECT" in resultado.output


def test_pasta_que_nao_e_simulacao(tmp_path: Path) -> None:
    resultado = runner.invoke(app, ["resumo", str(tmp_path)])

    assert resultado.exit_code == 1
    assert "não contém uma simulação" in resultado.output
