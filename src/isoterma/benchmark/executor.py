"""Uma medição, num processo próprio: ``python -m isoterma.benchmark.executor``.

Rodar cada medição num processo novo isola as engines: nenhuma herda cache, memória ou threads
da anterior. O tempo é medido aqui dentro, só em volta da tarefa, sem contar a inicialização do
Python nem os imports.
"""

import argparse
import json
import time
from pathlib import Path

import pyarrow.parquet as pq

from isoterma.benchmark.engines import ENGINES, IMPLEMENTACOES, Entrada
from isoterma.benchmark.tarefas import Formato, Tarefa


def main(argumentos: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tarefa", required=True, choices=[t.value for t in Tarefa])
    parser.add_argument("--formato", required=True, choices=[f.value for f in Formato])
    parser.add_argument("--engine", required=True, choices=ENGINES)
    parser.add_argument("--simulacao", required=True, type=Path)
    parser.add_argument("--txt", required=True, type=Path)
    parser.add_argument("--resultado", type=Path, help="Onde gravar o resultado (Parquet)")
    args = parser.parse_args(argumentos)

    implementacao = IMPLEMENTACOES[(Tarefa(args.tarefa), Formato(args.formato), args.engine)]
    entrada = Entrada(args.simulacao, args.txt)

    inicio = time.perf_counter()
    tabela = implementacao(entrada)
    segundos = time.perf_counter() - inicio

    if args.resultado:
        pq.write_table(tabela, args.resultado)
    print(json.dumps({"segundos": segundos, "linhas": tabela.num_rows}))


if __name__ == "__main__":
    main()
