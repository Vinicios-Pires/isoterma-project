from pathlib import Path

from typer.testing import CliRunner

from isoterma import __version__
from isoterma.cli import app

runner = CliRunner()


def test_version_mostra_a_versao_do_pacote() -> None:
    resultado = runner.invoke(app, ["--version"])

    assert resultado.exit_code == 0
    assert resultado.output.strip() == f"isoterma {__version__}"


def test_info_lista_as_engines_de_dados() -> None:
    resultado = runner.invoke(app, ["info"])

    assert resultado.exit_code == 0
    for engine in ("duckdb", "polars", "pandas"):
        assert engine in resultado.output


def test_sem_argumentos_mostra_a_ajuda() -> None:
    resultado = runner.invoke(app, [])

    assert "Usage" in resultado.output


def test_simular_gera_e_resume_a_simulacao(tmp_path: Path) -> None:
    saida = tmp_path / "hall"

    resultado = runner.invoke(
        app, ["simular", "--preset", "teste", "--saida", str(saida), "--processos", "1"]
    )

    assert resultado.exit_code == 0, resultado.output
    assert "77.760" in resultado.output
    assert (saida / "manifesto.json").exists()


def test_simular_recusa_sobrescrever_sem_a_opcao(tmp_path: Path) -> None:
    argumentos = ["simular", "--saida", str(tmp_path / "hall"), "--processos", "1"]
    runner.invoke(app, argumentos)

    resultado = runner.invoke(app, argumentos)

    assert resultado.exit_code == 1
    assert "--sobrescrever" in resultado.output


def test_simular_com_config_invalida_explica_o_erro(tmp_path: Path) -> None:
    config = tmp_path / "hall.toml"
    config.write_text("[hall]\nfileiras = 0\n", encoding="utf-8")

    resultado = runner.invoke(app, ["simular", "--config", str(config), "--saida", str(tmp_path)])

    assert resultado.exit_code == 1
    assert "Configuração inválida" in resultado.output


def test_exportar_1brc(tmp_path: Path) -> None:
    saida = tmp_path / "hall"
    runner.invoke(app, ["simular", "--saida", str(saida), "--processos", "1"])
    destino = tmp_path / "medicoes.txt"

    resultado = runner.invoke(app, ["exportar-1brc", str(saida), "--destino", str(destino)])

    assert resultado.exit_code == 0, resultado.output
    assert destino.read_text(encoding="utf-8").count("\n") > 0
