# Isoterma

**Inteligência térmica para data centers: veja, entenda e pergunte.**

[![CI](https://github.com/Vinicios-Pires/isoterma-project/actions/workflows/ci.yml/badge.svg)](https://github.com/Vinicios-Pires/isoterma-project/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.14-blue)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

> 🚧 **Em construção (fase 1: fundação).** O que está descrito abaixo é o destino do projeto.
> O roteiro mostra o que já existe.

*Isoterma é a linha que liga pontos de mesma temperatura num mapa, exatamente o que este
projeto desenha sobre a planta de um data center.*

## O problema

Um data center tem milhares de sensores de temperatura e umidade. Com 1.000 racks e 3 sensores
por rack lendo a cada segundo, são cerca de **259 milhões de leituras por dia**, e o bilhão de
linhas chega em menos de 4 dias. Os painéis costumam mostrar só o "agora", e perguntas mais
profundas dependem de alguém escrevendo SQL. Na prática, as equipes refrigeram demais por
precaução ou descobrem um ponto quente só quando um servidor desliga.

## A proposta

- **Mapa térmico** da planta do data hall, com isotermas mostrando onde o calor se acumula.
- **Detecção de anomalias**: rack fora da faixa recomendada pela ASHRAE (18–27 °C na entrada),
  falha de refrigeração (CRAC), ΔT anormal entre corredor frio e quente.
- **Perguntas em português**: *"Quais racks da fileira C passaram de 27 °C ontem à noite?"*.
  A IA gera o SQL, o DuckDB executa, e a resposta vem explicada, **com o SQL visível**.
- **Seus dados não saem de casa**: o modelo vê só o schema e os resultados agregados.
- **Sem dependência de fornecedor de IA**: Claude por padrão, com GPT, Gemini e Ollama plugáveis.
- **Precisão medida**: o simulador injeta falhas conhecidas e mede quantas são detectadas.

```
Pergunta em PT-BR → LLM gera SQL → DuckDB sobre Parquet → resultado + anomalias → LLM explica
```

## Roteiro

- **Fase 1: fundação**
  - [x] Estrutura do pacote, CLI, ferramentas de qualidade e CI
  - [x] [Simulador de data hall](docs/SIMULADOR.md) com incidentes injetados e gabarito, gerando Parquet
  - [x] [Motor de consultas](docs/MOTOR.md): camadas de agregados, consultas de domínio e SQL seguro
  - [x] [Benchmark](docs/BENCHMARK.md) com validação cruzada entre engines (Python, pandas, Polars, DuckDB)
- **Fase 2: inteligência**
  - [ ] Camada de IA com provedores plugáveis e benchmark de LLMs
  - [ ] Detecção de anomalias
  - [ ] API (FastAPI) e web (React + Vite + TypeScript) com o mapa térmico
  - [ ] Demo pública: DuckDB-WASM no navegador, Cloudflare Pages + R2, Cloud Run
- **Fase 3: mundo real**
  - [ ] Clima externo real (Open-Meteo/INMET) como entrada do simulador
  - [ ] Alertas e relatórios automáticos

## Começando

Requisito: [uv](https://docs.astral.sh/uv/). Ele instala o Python 3.14 sozinho.

```bash
git clone https://github.com/Vinicios-Pires/isoterma-project.git
cd isoterma-project
uv sync
uv run isoterma info
uv run isoterma simular --preset demo   # 30 dias de um hall com 200 racks, em segundos
uv run isoterma agregar data/demo       # camada de agregados por hora
uv run isoterma resumo data/demo
uv run isoterma mapa data/demo --instante 2026-11-07T04:15   # o CRAC-02 falhou às 2h
uv run isoterma consultar data/demo "SELECT * FROM incidentes ORDER BY inicio"
```

O simulador gera **1 bilhão de leituras em cerca de 20 s** num desktop de 6 núcleos
(`--preset bilhao`). Os detalhes do modelo, dos incidentes e do esquema estão em
[docs/SIMULADOR.md](docs/SIMULADOR.md).

## Desempenho

Sobre **1 bilhão de leituras**, num desktop com AMD Ryzen 5 5600 (6 núcleos) e 16 GB de RAM:

| | Tempo |
|---|--:|
| Gerar a simulação (1,5 GB em Parquet) | 20 s |
| 1BRC clássico: DuckDB sobre Parquet | 3,7 s |
| 1BRC clássico: Polars sobre Parquet | 6,9 s |
| 1BRC clássico: Python puro sobre `.txt` (mmap + multiprocessing) | 69 s |
| Consultas do motor (resumo, faixa ASHRAE, séries, mapa térmico) | < 1 s |

Todas as engines são conferidas contra a referência a cada execução. A comparação completa,
com memória, a tarefa realista e o método, está em [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Desenvolvimento

```bash
uv run pre-commit install   # roda lint, formatação e tipos antes de cada commit
uv run pytest --cov         # testes com cobertura
uv run ruff check           # lint
uv run ruff format          # formatação
uv run pyright              # checagem de tipos
```

## Estrutura

```
src/isoterma/   pacote principal: CLI, simulador, motor e, em breve, IA
tests/          testes automatizados
docs/           documentação, incluindo a evolução do projeto
legacy/         o projeto original da aula, preservado intocado
```

## Origem

O Isoterma nasceu de um projeto didático do
[One Billion Row Challenge](https://github.com/gunnarmorling/1brc) em Python, que comparava
Python puro, pandas, Dask, Polars, DuckDB e awk no processamento de 1 bilhão de linhas. Esse
projeto está preservado em [`legacy/`](legacy/), e o caminho do antes ao depois está em
[docs/EVOLUCAO.md](docs/EVOLUCAO.md).

**Créditos:** projeto original de Luciano Galvão ([lvgalvao](https://github.com/lvgalvao)), com
implementações de Koen Vossen (Polars) e Arthur Julião (Python e Bash), inspirado no 1BRC de
Gunnar Morling, e contribuições dos colegas do curso.

## Licença

[MIT](LICENSE). O conteúdo de `legacy/` pertence aos autores do projeto original, que não
declarou licença, e está aqui apenas como registro histórico com os devidos créditos.
