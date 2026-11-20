# Benchmark

<!-- Gerado por `isoterma relatorio-benchmark`. Não edite à mão: rode o benchmark de novo. -->

Comparação de **Python puro, pandas, Polars e DuckDB** sobre os dados do simulador, em duas tarefas. A primeira é o **1BRC clássico** (mínimo, média e máximo de cada sensor), herança direta do desafio. A segunda é uma **tarefa realista** do produto: junção com o cadastro de sensores, janela de uma hora e filtro pela faixa ASHRAE.

Todas as engines processam os dados em fluxo, sem carregar tudo na memória, e **todo resultado é conferido** contra a referência (DuckDB sobre Parquet). Uma engine rápida que erra a conta aparece com ❌.

## Simulação `demo`: 43.718.400 leituras

- **Dados:** 1.012 sensores em 200 racks. Parquet: 53,6 MB. `.txt` do 1BRC: 35.078.160 linhas, 712,0 MB.
- **Máquina:** AMD Ryzen 5 5600 6-Core Processor (6 núcleos, 12 threads), 16 GB de RAM, Windows-11-10.0.26200-SP0, Python 3.14.10.
- **Versões:** isoterma 0.1.0, duckdb 2.0.0, polars 2.1.0, pandas 3.1.1, pyarrow 26.0.1, numpy 2.5.5.
- **Método:** 3 medições por combinação, depois de uma rodada de aquecimento. Executado em 20/11/2026.

### 1BRC clássico

*mínimo, média e máximo de cada sensor de temperatura*

| Engine | Formato | Mediana | Melhor | vs. mais rápido | Memória (pico) | Resultado |
|---|---|--:|--:|--:|--:|---|
| DuckDB | `parquet` | 0,28 s | 0,27 s | 1,0× | 161,6 MB | ✅ referência |
| Polars | `parquet` | 0,46 s | 0,46 s | 1,6× | 444,7 MB | ✅ confere |
| Polars | `txt` | 0,68 s | 0,68 s | 2,4× | 1,1 GB | ✅ confere |
| DuckDB | `txt` | 0,86 s | 0,85 s | 3,1× | 562,7 MB | ✅ confere |
| pandas | `parquet` | 1,52 s | 1,51 s | 5,5× | 216,2 MB | ✅ confere |
| Python puro | `txt` | 3,68 s | 3,68 s | 13,3× | 3,5 GB | ✅ confere |
| pandas | `txt` | 3,89 s | 3,87 s | 14,0× | 243,2 MB | ✅ confere |

### Tarefa realista

*por rack e por hora: média da entrada, máximo da saída e leituras fora de 18–27 °C*

| Engine | Formato | Mediana | Melhor | vs. mais rápido | Memória (pico) | Resultado |
|---|---|--:|--:|--:|--:|---|
| DuckDB | `parquet` | 0,74 s | 0,74 s | 1,0× | 165,8 MB | ✅ referência |
| Polars | `parquet` | 0,87 s | 0,86 s | 1,2× | 1,0 GB | ✅ confere |
| pandas | `parquet` | 6,28 s | 6,27 s | 8,5× | 433,1 MB | ✅ confere |

## Simulação `bilhao`: 1.000.002.080 leituras

- **Dados:** 5.024 sensores em 1.000 racks. Parquet: 1,5 GB. `.txt` do 1BRC: 800.950.887 linhas, 15,9 GB.
- **Máquina:** AMD Ryzen 5 5600 6-Core Processor (6 núcleos, 12 threads), 16 GB de RAM, Windows-11-10.0.26200-SP0, Python 3.14.10.
- **Versões:** isoterma 0.1.0, duckdb 2.0.0, polars 2.1.0, pandas 3.1.1, pyarrow 26.0.1, numpy 2.5.5.
- **Método:** 3 medições por combinação, depois de uma rodada de aquecimento. Executado em 20/11/2026.

### 1BRC clássico

*mínimo, média e máximo de cada sensor de temperatura*

| Engine | Formato | Mediana | Melhor | vs. mais rápido | Memória (pico) | Resultado |
|---|---|--:|--:|--:|--:|---|
| DuckDB | `parquet` | 3,65 s | 3,54 s | 1,0× | 225,8 MB | ✅ referência |
| Polars | `parquet` | 6,94 s | 6,93 s | 1,9× | 1,5 GB | ✅ confere |
| Polars | `txt` | 14,3 s | 14,2 s | 3,9× | 1,9 GB | ✅ confere |
| DuckDB | `txt` | 16,8 s | 16,5 s | 4,6× | 936,0 MB | ✅ confere |
| pandas | `parquet` | 26,3 s | 26,1 s | 7,2× | 492,7 MB | ✅ confere |
| Python puro | `txt` | 68,7 s | 68,2 s | 18,8× | 3,8 GB | ✅ confere |
| pandas | `txt` | 95,3 s | 89,4 s | 26,1× | 288,7 MB | ✅ confere |

### Tarefa realista

*por rack e por hora: média da entrada, máximo da saída e leituras fora de 18–27 °C*

| Engine | Formato | Mediana | Melhor | vs. mais rápido | Memória (pico) | Resultado |
|---|---|--:|--:|--:|--:|---|
| DuckDB | `parquet` | 13,9 s | 13,8 s | 1,0× | 285,6 MB | ✅ referência |
| Polars | `parquet` | 14,6 s | 14,1 s | 1,1× | 2,9 GB | ✅ confere |
| pandas | `parquet` | 2 min 04 s | 2 min 03 s | 9,0× | 1,6 GB | ✅ confere |

## Como as medições são feitas

- Cada medição roda num **processo novo** (`python -m isoterma.benchmark.executor`), para que nenhuma engine herde cache, memória ou threads de outra.
- O **tempo** é medido dentro desse processo, só em volta da tarefa: não inclui a inicialização do Python nem os imports. Inclui ler os arquivos, que ficam no cache do sistema operacional depois do aquecimento quando cabem na RAM.
- A **memória** é o pico da soma do RSS do processo e dos seus filhos, amostrada a cada 20 ms. O Python puro usa um processo por núcleo e lê o arquivo por `mmap`, então páginas compartilhadas são contadas em cada processo e o valor dele fica superestimado.
- A **validação** compara chaves, mínimos, máximos e contagens exatamente. As médias aceitam diferença de uma unidade na última casa, porque somar em outra ordem pode mudar o arredondamento.
- O formato `.txt` é a exportação `codigo;valor` do 1BRC, só com temperaturas. A tarefa realista precisa de horário e do cadastro de sensores, então só roda sobre Parquet.

## Como reproduzir

```bash
uv run isoterma simular --preset bilhao
uv run isoterma benchmark data/bilhao --resultado docs/benchmark/bilhao.json
uv run isoterma relatorio-benchmark docs/benchmark/*.json --saida docs/BENCHMARK.md
```

## O projeto original

Para referência histórica, os tempos do README do projeto da aula (Apple M1 com 8 GB, CSV de 1 bilhão de linhas, sem validação dos resultados). O hardware, os dados e as versões são outros, então a comparação direta não vale:

| Implementação | Tempo |
|---|--:|
| Bash + awk | 25 min |
| Python | 20 min |
| pandas | 263 s |
| Dask | 155,6 s |
| Polars | 33,9 s |
| DuckDB | 15,0 s |
