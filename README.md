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
  - [ ] Simulador de data hall com incidentes injetados, gerando Parquet
  - [ ] Motor de agregação com DuckDB
  - [ ] Benchmark com validação cruzada entre engines (Python, pandas, Polars, DuckDB)
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
uv run isoterma --help
uv run isoterma info
```

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
src/isoterma/   pacote principal (núcleo, CLI e, em breve, simulador, motor e IA)
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
