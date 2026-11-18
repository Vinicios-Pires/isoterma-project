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
