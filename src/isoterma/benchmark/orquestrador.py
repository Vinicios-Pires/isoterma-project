"""Planeja e executa as medições, valida os resultados e registra tudo num JSON."""

import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
import pyarrow.parquet as pq

from isoterma import __version__
from isoterma.benchmark.engines import ENGINES, IMPLEMENTACOES, REFERENCIA
from isoterma.benchmark.tarefas import Formato, Tarefa, comparar, normalizar
from isoterma.dados import exportar_1brc, ler_manifesto

AMOSTRAGEM_MEMORIA_S = 0.02


@dataclass
class Medicao:
    tarefa: str
    formato: str
    engine: str
    tempos_s: list[float] = field(default_factory=list)
    pico_memoria_bytes: int = 0
    valido: bool | None = None  # None: não deu para validar
    motivo: str = ""
    erro: str | None = None

    @property
    def mediana_s(self) -> float | None:
        return statistics.median(self.tempos_s) if self.tempos_s else None

    @property
    def melhor_s(self) -> float | None:
        return min(self.tempos_s) if self.tempos_s else None


@dataclass
class ResultadoBenchmark:
    simulacao: dict[str, Any]
    maquina: dict[str, Any]
    versoes: dict[str, str]
    parametros: dict[str, Any]
    gerado_em: str
    medicoes: list[Medicao]

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def carregar(cls, caminho: Path) -> ResultadoBenchmark:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["medicoes"] = [Medicao(**m) for m in dados["medicoes"]]
        return cls(**dados)


def _nome_cpu() -> str:
    try:
        if sys.platform == "win32":
            import winreg

            chave = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            )
            return str(winreg.QueryValueEx(chave, "ProcessorNameString")[0]).strip()
        if sys.platform == "linux":
            for linha in Path("/proc/cpuinfo").read_text().splitlines():
                if linha.startswith("model name"):
                    return linha.split(":", 1)[1].strip()
        if sys.platform == "darwin":
            saida = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
            )
            return saida.stdout.strip()
    except OSError:
        pass
    return platform.processor() or "desconhecida"


def descrever_maquina() -> dict[str, Any]:
    return {
        "cpu": _nome_cpu(),
        "nucleos": psutil.cpu_count(logical=False),
        "threads": psutil.cpu_count(),
        "memoria_gb": round(psutil.virtual_memory().total / 2**30),
        "sistema": platform.platform(),
        "python": platform.python_version(),
    }


def versoes() -> dict[str, str]:
    import duckdb
    import numpy
    import pandas
    import polars
    import pyarrow

    return {
        "isoterma": __version__,
        "duckdb": duckdb.__version__,
        "polars": polars.__version__,
        "pandas": pandas.__version__,
        "pyarrow": pyarrow.__version__,
        "numpy": numpy.__version__,
    }


def _encerrar(processo: psutil.Popen) -> None:
    for filho in processo.children(recursive=True):
        filho.kill()
    processo.kill()


def medir(comando: list[str], tempo_max_s: float) -> tuple[float, int]:
    """Roda o executor e devolve (segundos medidos lá dentro, pico de memória da árvore).

    A memória é a soma do RSS do processo e dos filhos (o Python puro usa vários processos),
    amostrada a cada 20 ms.
    """
    with tempfile.TemporaryFile("w+") as saida, tempfile.TemporaryFile("w+") as erros:
        processo = psutil.Popen(comando, stdout=saida, stderr=erros, text=True)
        pico = 0
        inicio = time.monotonic()
        while processo.poll() is None:
            try:
                arvore = [processo, *processo.children(recursive=True)]
                pico = max(pico, sum(p.memory_info().rss for p in arvore))
            except psutil.Error:
                pass
            if time.monotonic() - inicio > tempo_max_s:
                _encerrar(processo)
                processo.wait()
                raise TimeoutError(f"passou de {tempo_max_s:g} s")
            time.sleep(AMOSTRAGEM_MEMORIA_S)
        saida.seek(0)
        erros.seek(0)
        if processo.returncode != 0:
            ultima = (erros.read().strip().splitlines() or ["sem mensagem"])[-1]
            raise RuntimeError(ultima)
        dados = json.loads(saida.read().strip().splitlines()[-1])
    return float(dados["segundos"]), pico


def planejar(
    tarefas: Iterable[Tarefa], formatos: Iterable[Formato], engines: Iterable[str]
) -> list[tuple[Tarefa, Formato, str]]:
    """As combinações implementadas, com a referência de cada tarefa sempre primeiro."""
    tarefas, formatos, engines = list(tarefas), set(formatos), set(engines)
    plano: list[tuple[Tarefa, Formato, str]] = []
    for tarefa in tarefas:
        referencia = (tarefa, *REFERENCIA[tarefa])
        combinacoes = [
            chave
            for chave in IMPLEMENTACOES
            if chave[0] == tarefa and chave[1] in formatos and chave[2] in engines
        ]
        combinacoes.sort(
            key=lambda c: (c != referencia, list(Formato).index(c[1]), ENGINES.index(c[2]))
        )
        if referencia not in combinacoes:
            combinacoes.insert(0, referencia)  # sem referência não há como validar
        plano.extend(combinacoes)
    return plano


def executar_benchmark(
    diretorio: Path,
    *,
    tarefas: Iterable[Tarefa] = tuple(Tarefa),
    formatos: Iterable[Formato] = tuple(Formato),
    engines: Iterable[str] = ENGINES,
    repeticoes: int = 3,
    aquecimento: bool = True,
    tempo_max_s: float = 1800.0,
    aviso: Callable[[str], None] | None = None,
) -> ResultadoBenchmark:
    diretorio = diretorio.resolve()
    manifesto = ler_manifesto(diretorio)
    plano = planejar(tarefas, formatos, engines)
    avisar = aviso or (lambda _: None)

    txt = diretorio / "benchmark" / "medicoes.txt"
    linhas_txt: int | None = None
    if any(formato is Formato.TXT for _, formato, _ in plano):
        if not txt.exists():
            avisar(f"Exportando as temperaturas no formato do 1BRC para {txt}...")
            txt.parent.mkdir(parents=True, exist_ok=True)
            linhas_txt = exportar_1brc(diretorio, txt)
        else:
            with txt.open("rb") as arquivo:
                linhas_txt = sum(
                    bloco.count(b"\n") for bloco in iter(lambda: arquivo.read(1 << 24), b"")
                )

    medicoes: list[Medicao] = []
    referencias: dict[Tarefa, Any] = {}
    with tempfile.TemporaryDirectory(prefix="isoterma-bench-") as temporaria:
        for tarefa, formato, engine in plano:
            medicao = Medicao(tarefa.value, formato.value, engine)
            medicoes.append(medicao)
            resultado = Path(temporaria) / f"{tarefa}-{formato}-{engine}.parquet"
            comando = [
                sys.executable, "-m", "isoterma.benchmark.executor",
                "--tarefa", tarefa.value, "--formato", formato.value, "--engine", engine,
                "--simulacao", str(diretorio), "--txt", str(txt), "--resultado", str(resultado),
            ]  # fmt: skip
            rodadas = ["aquecimento"] * aquecimento + [
                f"{i + 1}/{repeticoes}" for i in range(repeticoes)
            ]
            for rodada in rodadas:
                try:
                    segundos, pico = medir(comando, tempo_max_s)
                except (TimeoutError, RuntimeError) as erro:
                    medicao.erro = str(erro)
                    avisar(f"{tarefa:<9} {formato:<8} {engine:<7} {rodada:<12} falhou: {erro}")
                    break
                medicao.pico_memoria_bytes = max(medicao.pico_memoria_bytes, pico)
                if rodada != "aquecimento":
                    medicao.tempos_s.append(segundos)
                avisar(f"{tarefa:<9} {formato:<8} {engine:<7} {rodada:<12} {segundos:8.2f} s")

            if medicao.erro is None:
                normalizado = normalizar(tarefa, pq.read_table(resultado))
                if (formato, engine) == REFERENCIA[tarefa]:
                    referencias[tarefa] = normalizado
                    medicao.valido, medicao.motivo = True, "referência"
                elif tarefa in referencias:
                    validacao = comparar(tarefa, normalizado, referencias[tarefa])
                    medicao.valido, medicao.motivo = validacao.valido, validacao.motivo

    contagens = manifesto["contagens"]
    tamanho_parquet = sum(f.stat().st_size for f in (diretorio / "leituras").rglob("*.parquet"))
    return ResultadoBenchmark(
        simulacao={
            "nome": manifesto["config"]["nome"],
            "leituras": contagens["linhas"],
            "sensores": contagens["sensores"],
            "racks": contagens["racks"],
            "linhas_txt": linhas_txt,
            "bytes_parquet": tamanho_parquet,
            "bytes_txt": txt.stat().st_size if linhas_txt is not None else None,
        },
        maquina=descrever_maquina(),
        versoes=versoes(),
        parametros={
            "repeticoes": repeticoes,
            "aquecimento": aquecimento,
            "tempo_max_s": tempo_max_s,
        },
        gerado_em=datetime.now(UTC).isoformat(timespec="seconds"),
        medicoes=medicoes,
    )
