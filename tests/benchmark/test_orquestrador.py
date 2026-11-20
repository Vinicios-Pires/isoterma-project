import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from isoterma.benchmark.engines import Entrada
from isoterma.benchmark.orquestrador import (
    ResultadoBenchmark,
    descrever_maquina,
    executar_benchmark,
    medir,
    planejar,
)
from isoterma.benchmark.relatorio import gerar_markdown
from isoterma.benchmark.tarefas import Formato, Tarefa
from isoterma.cli import app


@pytest.fixture(scope="module")
def resultado(entrada: Entrada) -> ResultadoBenchmark:
    return executar_benchmark(
        entrada.diretorio,
        tarefas=[Tarefa.BRC],
        engines=["polars"],
        repeticoes=2,
        aquecimento=False,
    )


def test_plano_poe_a_referencia_primeiro_e_respeita_os_filtros() -> None:
    plano = planejar([Tarefa.BRC, Tarefa.REALISTA], [Formato.PARQUET], ["pandas"])

    assert plano == [
        (Tarefa.BRC, Formato.PARQUET, "duckdb"),
        (Tarefa.BRC, Formato.PARQUET, "pandas"),
        (Tarefa.REALISTA, Formato.PARQUET, "duckdb"),
        (Tarefa.REALISTA, Formato.PARQUET, "pandas"),
    ]


def test_plano_completo_tem_dez_combinacoes() -> None:
    assert len(planejar(Tarefa, Formato, ["python", "pandas", "polars", "duckdb"])) == 10


def test_benchmark_mede_e_valida_cada_combinacao(resultado: ResultadoBenchmark) -> None:
    combinacoes = [(m.formato, m.engine) for m in resultado.medicoes]

    assert combinacoes == [("parquet", "duckdb"), ("txt", "polars"), ("parquet", "polars")]
    for medicao in resultado.medicoes:
        assert medicao.erro is None
        assert medicao.valido is True
        assert len(medicao.tempos_s) == 2
        assert medicao.pico_memoria_bytes > 10 * 2**20


def test_benchmark_registra_simulacao_e_maquina(resultado: ResultadoBenchmark) -> None:
    assert resultado.simulacao["leituras"] == 1440 * 54
    assert resultado.simulacao["linhas_txt"] > 0
    assert resultado.maquina["threads"] >= 1
    assert "duckdb" in resultado.versoes


def test_resultado_vai_e_volta_do_json(resultado: ResultadoBenchmark, tmp_path: Path) -> None:
    arquivo = tmp_path / "r.json"
    resultado.salvar(arquivo)

    assert ResultadoBenchmark.carregar(arquivo) == resultado


def test_medicao_que_demora_demais_e_interrompida(entrada: Entrada) -> None:
    comando = [sys.executable, "-c", "import time; time.sleep(30)"]

    with pytest.raises(TimeoutError, match=r"passou de 0\.5 s"):
        medir(comando, tempo_max_s=0.5)


def test_erro_no_executor_vira_mensagem() -> None:
    comando = [sys.executable, "-c", "raise SystemExit('deu ruim')"]

    with pytest.raises(RuntimeError, match="deu ruim"):
        medir(comando, tempo_max_s=30)


def test_relatorio_tem_uma_tabela_por_tarefa(resultado: ResultadoBenchmark) -> None:
    markdown = gerar_markdown([resultado])

    assert "### 1BRC clássico" in markdown
    assert "### Tarefa realista" not in markdown
    assert "| Polars | `txt` |" in markdown
    assert "✅ referência" in markdown
    assert descrever_maquina()["cpu"] in markdown


def test_cli_benchmark_e_relatorio(entrada: Entrada, tmp_path: Path) -> None:
    runner = CliRunner()
    json_saida = tmp_path / "bench.json"

    medido = runner.invoke(
        app,
        [
            "benchmark", str(entrada.diretorio), "--tarefa", "realista", "--engine", "duckdb",
            "--repeticoes", "1", "--no-aquecimento", "--resultado", str(json_saida),
        ],
    )  # fmt: skip
    relatorio = runner.invoke(
        app, ["relatorio-benchmark", str(json_saida), "--saida", str(tmp_path / "B.md")]
    )

    assert medido.exit_code == 0, medido.output
    assert "realista  parquet  duckdb" in medido.output
    assert relatorio.exit_code == 0, relatorio.output
    assert "### Tarefa realista" in (tmp_path / "B.md").read_text(encoding="utf-8")
