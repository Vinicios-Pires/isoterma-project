"""Gera o docs/BENCHMARK.md a partir dos JSONs de resultado."""

from datetime import datetime

from isoterma.benchmark.orquestrador import Medicao, ResultadoBenchmark
from isoterma.benchmark.tarefas import DESCRICAO, Tarefa
from isoterma.terminal import numero, tamanho

NOMES_ENGINE = {
    "python": "Python puro",
    "pandas": "pandas",
    "polars": "Polars",
    "duckdb": "DuckDB",
}
NOMES_TAREFA = {Tarefa.BRC: "1BRC clássico", Tarefa.REALISTA: "Tarefa realista"}

# Tempos do README do projeto original: Apple M1 com 8 GB, CSV de 1 bilhão de linhas.
ORIGINAL = {
    "Bash + awk": "25 min",
    "Python": "20 min",
    "pandas": "263 s",
    "Dask": "155,6 s",
    "Polars": "33,9 s",
    "DuckDB": "15,0 s",
}


def _tempo(segundos: float | None) -> str:
    if segundos is None:
        return "—"
    if segundos >= 120:
        minutos, resto = divmod(segundos, 60)
        return f"{int(minutos)} min {int(resto):02d} s"
    return f"{numero(segundos, 2 if segundos < 10 else 1)} s"


def _status(m: Medicao) -> str:
    if m.erro:
        return f"⏱ {m.erro}" if m.erro.startswith("passou de") else f"💥 {m.erro}"
    if m.valido is None:
        return "não validado"
    if m.motivo == "referência":
        return "✅ referência"
    return "✅ confere" if m.valido else f"❌ {m.motivo}"


def _tabela(medicoes: list[Medicao]) -> list[str]:
    ordenadas = sorted(medicoes, key=lambda m: (m.mediana_s is None, m.mediana_s or 0))
    melhor = next((m.mediana_s for m in ordenadas if m.mediana_s), None)
    linhas = [
        "| Engine | Formato | Mediana | Melhor | vs. mais rápido | Memória (pico) | Resultado |",
        "|---|---|--:|--:|--:|--:|---|",
    ]
    for m in ordenadas:
        relativo = f"{numero(m.mediana_s / melhor, 1)}×" if m.mediana_s and melhor else "—"
        memoria = tamanho(m.pico_memoria_bytes) if m.pico_memoria_bytes else "—"
        linhas.append(
            f"| {NOMES_ENGINE[m.engine]} | `{m.formato}` | {_tempo(m.mediana_s)} "
            f"| {_tempo(m.melhor_s)} | {relativo} | {memoria} | {_status(m)} |"
        )
    return linhas


def _secao(resultado: ResultadoBenchmark) -> list[str]:
    s = resultado.simulacao
    p = resultado.parametros
    maq = resultado.maquina
    linhas = [
        f"## Simulação `{s['nome']}`: {numero(s['leituras'])} leituras",
        "",
        f"- **Dados:** {numero(s['sensores'])} sensores em {numero(s['racks'])} racks. "
        f"Parquet: {tamanho(s['bytes_parquet'])}."
        + (
            f" `.txt` do 1BRC: {numero(s['linhas_txt'])} linhas, {tamanho(s['bytes_txt'])}."
            if s.get("linhas_txt") is not None
            else ""
        ),
        f"- **Máquina:** {maq['cpu']} ({maq['nucleos']} núcleos, {maq['threads']} threads), "
        f"{maq['memoria_gb']} GB de RAM, {maq['sistema']}, Python {maq['python']}.",
        "- **Versões:** " + ", ".join(f"{k} {v}" for k, v in resultado.versoes.items()) + ".",
        f"- **Método:** {p['repeticoes']} medições por combinação"
        + (", depois de uma rodada de aquecimento" if p["aquecimento"] else "")
        + f". Executado em {datetime.fromisoformat(resultado.gerado_em):%d/%m/%Y}.",
        "",
    ]
    for tarefa in Tarefa:
        medicoes = [m for m in resultado.medicoes if m.tarefa == tarefa.value]
        if medicoes:
            linhas += [f"### {NOMES_TAREFA[tarefa]}", "", f"*{DESCRICAO[tarefa]}*", ""]
            linhas += [*_tabela(medicoes), ""]
    return linhas


def gerar_markdown(resultados: list[ResultadoBenchmark]) -> str:
    linhas = [
        "# Benchmark",
        "",
        "<!-- Gerado por `isoterma relatorio-benchmark`. "
        "Não edite à mão: rode o benchmark de novo. -->",
        "",
        "Comparação de **Python puro, pandas, Polars e DuckDB** sobre os dados do simulador, em "
        "duas tarefas. A primeira é o **1BRC clássico** (mínimo, média e máximo de cada sensor), "
        "herança direta do desafio. A segunda é uma **tarefa realista** do produto: junção com o "
        "cadastro de sensores, janela de uma hora e filtro pela faixa ASHRAE.",
        "",
        "Todas as engines processam os dados em fluxo, sem carregar tudo na memória, e "
        "**todo resultado é conferido** contra a referência (DuckDB sobre Parquet). Uma engine "
        "rápida que erra a conta aparece com ❌.",
        "",
    ]
    for resultado in resultados:
        linhas += _secao(resultado)
    linhas += [
        "## Como as medições são feitas",
        "",
        "- Cada medição roda num **processo novo** (`python -m isoterma.benchmark.executor`), "
        "para que nenhuma engine herde cache, memória ou threads de outra.",
        "- O **tempo** é medido dentro desse processo, só em volta da tarefa: não inclui a "
        "inicialização do Python nem os imports. Inclui ler os arquivos, que ficam no cache do "
        "sistema operacional depois do aquecimento quando cabem na RAM.",
        "- A **memória** é o pico da soma do RSS do processo e dos seus filhos, amostrada a cada "
        "20 ms. O Python puro usa um processo por núcleo e lê o arquivo por `mmap`, então páginas "
        "compartilhadas são contadas em cada processo e o valor dele fica superestimado.",
        "- A **validação** compara chaves, mínimos, máximos e contagens exatamente. As médias "
        "aceitam diferença de uma unidade na última casa, porque somar em outra ordem pode mudar "
        "o arredondamento.",
        "- O formato `.txt` é a exportação `codigo;valor` do 1BRC, só com temperaturas. A tarefa "
        "realista precisa de horário e do cadastro de sensores, então só roda sobre Parquet.",
        "",
        "## Como reproduzir",
        "",
        "```bash",
        "uv run isoterma simular --preset bilhao",
        "uv run isoterma benchmark data/bilhao --resultado docs/benchmark/bilhao.json",
        "uv run isoterma relatorio-benchmark docs/benchmark/*.json --saida docs/BENCHMARK.md",
        "```",
        "",
        "## O projeto original",
        "",
        "Para referência histórica, os tempos do README do projeto da aula (Apple M1 com 8 GB, "
        "CSV de 1 bilhão de linhas, sem validação dos resultados). O hardware, os dados e as "
        "versões são outros, então a comparação direta não vale:",
        "",
        "| Implementação | Tempo |",
        "|---|--:|",
        *[f"| {nome} | {tempo} |" for nome, tempo in ORIGINAL.items()],
        "",
    ]
    return "\n".join(linhas)
