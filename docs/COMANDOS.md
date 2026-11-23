# Comandos do Isoterma

Guia de todos os comandos da linha de comando, na ordem em que costumam ser usados.

## Antes de tudo

- **Rode os comandos com `uv run`**, a partir da pasta do projeto: `uv run isoterma <comando>`.
  O uv usa o ambiente do projeto, sem precisar ativar nada.
- **A própria CLI tem ajuda:**
  ```bash
  uv run isoterma --help              # lista os comandos
  uv run isoterma <comando> --help    # opções de um comando, com os valores padrão
  ```
- **A maioria dos comandos recebe a pasta de uma simulação** (`data/demo`, `data/bilhao`...),
  criada pelo `simular`.
- **Datas são no horário local do hall** (`America/Sao_Paulo` nos presets), em um destes
  formatos: `2026-11-07T02:30`, `"2026-11-07 02:30"` ou `2026-11-07`.
- **Opções sim/não** têm a forma `--opcao` / `--no-opcao` (ex.: `--aquecimento` e
  `--no-aquecimento`).

## Resumo

| Comando | Para quê | Custa dinheiro? |
|---|---|---|
| [`info`](#info) | versões do Isoterma e das engines | não |
| [`simular`](#simular) | gera a telemetria de um data hall | não |
| [`exportar-1brc`](#exportar-1brc) | exporta as temperaturas no formato do desafio original | não |
| [`agregar`](#agregar) | gera os agregados por minuto e por hora | não |
| [`resumo`](#resumo) | visão geral do hall numa janela | não |
| [`mapa`](#mapa) | mapa térmico colorido no terminal | não |
| [`consultar`](#consultar) | executa um SELECT em modo seguro | não |
| [`benchmark`](#benchmark) | compara Python, pandas, Polars e DuckDB | não |
| [`relatorio-benchmark`](#relatorio-benchmark) | gera o `docs/BENCHMARK.md` | não |
| [`perguntar`](#perguntar) | pergunta em português, respondida pela IA | **sim**, com provedor real |
| [`avaliar-ia`](#avaliar-ia) | mede quanto cada modelo de IA acerta | **sim**, com provedor real |
| [`relatorio-ia`](#relatorio-ia) | gera o `docs/AVALIACAO_IA.md` | não |
| [`detectar`](#detectar) | procura anomalias, explicando cada alerta | não |
| [`avaliar-deteccao`](#avaliar-deteccao) | mede os detectores contra o gabarito | não |
| [`relatorio-deteccao`](#relatorio-deteccao) | gera o `docs/DETECCAO.md` | não |
| [`servir`](#servir) | sobe a API HTTP para a web | só se a IA estiver ligada |

Um roteiro completo, do zero até a primeira pergunta:

```bash
uv run isoterma simular --preset demo
uv run isoterma agregar data/demo
uv run isoterma mapa data/demo --instante 2026-11-07T04:15
uv run isoterma perguntar data/demo "o que aconteceu na fileira A no dia 7 de madrugada?"
```

---

## Geral

### `info`

Mostra as versões instaladas do Isoterma, do DuckDB, do Polars e do pandas. É útil para
conferir a instalação ou registrar o ambiente num relatório.

```bash
uv run isoterma info
uv run isoterma --version     # só a versão do Isoterma
```

---

## Simulação

### `simular`

Gera a telemetria de um data hall fictício: leituras de temperatura e potência de cada rack e
de cada CRAC, com incidentes injetados de propósito (falhas de CRAC, sobrecargas, defeitos de
sensor...). Grava tudo em Parquet numa pasta, junto com o gabarito dos incidentes e um
`manifesto.json`. Detalhes do modelo em [SIMULADOR.md](SIMULADOR.md).

```bash
uv run isoterma simular                          # preset teste: 1 dia, 10 racks, em segundos
uv run isoterma simular --preset demo            # 30 dias, 200 racks, ~44 milhões de leituras
uv run isoterma simular --preset bilhao          # 1 bilhão de leituras (~20 s, 1,5 GB)
uv run isoterma simular --config meu_hall.toml   # um hall próprio
uv run isoterma simular -p demo --seed 7 --saida data/outro-demo
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--preset`, `-p` | escala pronta: `teste`, `demo` ou `bilhao` | `teste` |
| `--config`, `-c` | arquivo TOML com um hall próprio; substitui o preset | — |
| `--seed` | semente aleatória; a mesma seed gera exatamente os mesmos dados | a do preset (42) |
| `--saida`, `-o` | pasta de destino | `data/<nome do preset>` |
| `--processos` | quantos processos geram em paralelo | todos os núcleos |
| `--sobrescrever` | apaga uma simulação anterior na mesma pasta | não apaga |

Por segurança, o `--sobrescrever` só apaga pastas que têm um `manifesto.json`, ou seja,
simulações do próprio Isoterma.

### `exportar-1brc`

Exporta as temperaturas de uma simulação no formato do One Billion Row Challenge original: uma
linha `codigo;valor` por leitura (ex.: `B-10/entrada-base;19.7`). Serve para comparar com o
desafio e é usado pelo benchmark.

```bash
uv run isoterma exportar-1brc data/demo --destino data/demo/medicoes.txt
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--destino`, `-d` | arquivo de saída | `medicoes.txt` |

O arquivo fica grande: o do `bilhao` tem cerca de 17 GB.

---

## Consulta

### `agregar`

Gera a "camada ouro": mínimo, máximo, média e contagem de cada sensor por minuto e por hora.
Com ela, consultas de janelas longas ficam centenas de vezes mais rápidas. Rode uma vez depois
de simular; o `resumo`, o `mapa`, a IA e as outras consultas passam a usá-la sozinhos. Detalhes
em [MOTOR.md](MOTOR.md).

```bash
uv run isoterma agregar data/demo
uv run isoterma agregar data/bilhao --granularidade hora
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--granularidade` | `minuto` e/ou `hora` (repita a opção para as duas) | todas as que reduzem os dados |

Em leituras de minuto em minuto, como na demo, só o agregado por hora é gerado.

### `resumo`

Visão geral do hall numa janela de tempo: quantas leituras, temperaturas mínima, média e
máxima por tipo de sensor, potência média total e quantos racks saíram da faixa ASHRAE
(18–27 °C na entrada).

```bash
uv run isoterma resumo data/demo
uv run isoterma resumo data/demo --inicio 2026-11-07 --fim 2026-11-08
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--inicio` | começo da janela (horário local) | começo da simulação |
| `--fim` | fim da janela (horário local) | fim da simulação |

### `mapa`

Desenha a planta do hall no terminal: uma linha por fileira, um bloco colorido por rack, do
azul (frio) ao vermelho (quente). Cada valor é a média dos 5 minutos anteriores ao instante.
Para a temperatura de entrada, lista também os racks fora da faixa ASHRAE.

```bash
uv run isoterma mapa data/demo                               # no fim da simulação
uv run isoterma mapa data/demo --instante 2026-11-07T04:15   # 2h15 depois da falha do CRAC-02
uv run isoterma mapa data/demo --tipo potencia_kw
uv run isoterma mapa data/demo --altura topo
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--instante` | o momento a desenhar (horário local) | fim da simulação |
| `--tipo` | `temp_entrada`, `temp_saida` ou `potencia_kw` | `temp_entrada` |
| `--altura` | `base`, `meio` ou `topo`; só para `temp_entrada` | a altura mais quente de cada rack |

### `consultar`

Executa um SELECT livre nos dados, em modo seguro: só leitura, sem acesso a outros arquivos nem
à rede, com teto de linhas e de tempo. Comandos que alteram algo (`DROP`, `INSERT`, `COPY`...)
são recusados.

```bash
uv run isoterma consultar data/demo "SELECT * FROM incidentes ORDER BY inicio"
uv run isoterma consultar data/demo "SELECT fileira, count(*) AS racks FROM racks GROUP BY 1" --limite 100
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--limite` | máximo de linhas no resultado | 50 |

Tabelas disponíveis: `leituras`, `sensores`, `racks`, `cracs`, `incidentes` (o gabarito) e,
depois do `agregar`, `agregados_minuto` e `agregados_hora`. **No SQL, os horários estão em UTC**
(o horário de Brasília é UTC−3). O dicionário completo está em
[SIMULADOR.md](SIMULADOR.md#esquema-dos-dados).

---

## Benchmark

### `benchmark`

Compara Python puro, pandas, Polars e DuckDB em duas tarefas: o 1BRC clássico (mínimo, média e
máximo por sensor) e uma tarefa realista (por rack e hora, com junção e janela de tempo). Cada
medição roda num processo isolado, mede o tempo e o pico de memória, e **todo resultado é
conferido** contra a referência. Detalhes em [BENCHMARK.md](BENCHMARK.md).

```bash
uv run isoterma benchmark data/demo
uv run isoterma benchmark data/demo --tarefa 1brc --engine polars --repeticoes 1 --no-aquecimento
uv run isoterma benchmark data/bilhao --resultado docs/benchmark/bilhao.json
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--tarefa` | `1brc` e/ou `realista` | as duas |
| `--formato` | `txt` e/ou `parquet` | os dois |
| `--engine` | `python`, `pandas`, `polars` e/ou `duckdb`; o DuckDB sobre Parquet sempre roda, porque é a referência | todas |
| `--repeticoes` | medições por combinação | 3 |
| `--aquecimento` / `--no-aquecimento` | roda uma vez antes de medir, para aquecer o cache | com aquecimento |
| `--tempo-max` | segundos por medição antes de desistir | 1800 |
| `--resultado` | onde gravar o JSON | `<simulação>/benchmark/resultado.json` |

Se o formato `txt` for usado e o arquivo ainda não existir, o comando o exporta primeiro. Se
alguma engine errar a conta, o comando termina com código de saída 2. Sobre o `bilhao`, a
rodada completa leva uns 30 minutos.

### `relatorio-benchmark`

Gera o relatório em Markdown a partir de um ou mais JSONs do `benchmark`, com uma tabela por
tarefa, a máquina, as versões e o método.

```bash
uv run isoterma relatorio-benchmark docs/benchmark/demo.json docs/benchmark/bilhao.json
uv run isoterma relatorio-benchmark data/demo/benchmark/resultado.json --saida data/demo/BENCHMARK.md
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--saida` | arquivo Markdown de saída | `docs/BENCHMARK.md` |

---

## IA

Os comandos de IA usam um provedor de LLM, escolhido com `--llm` ou pela variável de ambiente
`ISOTERMA_LLM`:

| Valor | Provedor | Credencial |
|---|---|---|
| `claude` | Claude Haiku 5.5 (o padrão) | `ANTHROPIC_API_KEY` |
| `claude:<modelo>` | outro modelo do Claude, ex.: `claude:claude-sonnet-5-5` | `ANTHROPIC_API_KEY` |
| `openai:<modelo>` | um modelo da OpenAI (o modelo é obrigatório) | `OPENAI_API_KEY` |
| `gemini:<modelo>` | um modelo do Gemini (o modelo é obrigatório) | `GEMINI_API_KEY` |
| `falso` | demonstração sem rede e sem custo | nenhuma |

Para configurar no PowerShell (vale só para o terminal aberto):

```powershell
uv sync --extra claude                # ou --extra openai / --extra gemini / --all-extras
$env:ANTHROPIC_API_KEY = "sua-chave"
$env:ISOTERMA_LLM = "claude"          # opcional: muda o provedor padrão
```

**As APIs são cobradas por token**, à parte de qualquer assinatura (claude.ai, ChatGPT...). Com o
Haiku 5.5, uma pergunta custa por volta de US$ 0,003; o custo estimado aparece no fim de cada
resposta. Detalhes em [IA.md](IA.md).

### `perguntar`

Faz uma pergunta em português sobre o hall. A IA consulta os dados pelas ferramentas do motor,
mostra cada consulta enquanto trabalha e responde com os fatos que encontrou. Ela não enxerga o
gabarito de incidentes.

```bash
uv run isoterma perguntar data/demo "como está o hall?"
uv run isoterma perguntar data/demo "o rack G-07 está quente ou o sensor está com defeito?"
uv run isoterma perguntar data/demo "quais CRACs falharam no mês?" --llm claude:claude-sonnet-5-5
uv run isoterma perguntar data/demo "como está o hall?" --llm falso    # sem chave
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--llm` | provedor e modelo (tabela acima) | `ISOTERMA_LLM` ou `claude` |
| `--mostrar-sql` / `--no-mostrar-sql` | mostra o SQL de cada consulta livre | mostra |

No fim, a resposta traz o provedor, o modelo, o tempo, quantas consultas foram feitas, os tokens
e o custo estimado.

### `avaliar-ia`

Mede quanto cada modelo acerta. Gera perguntas com resposta conhecida a partir da simulação
(19 na demo, na v2: fatos, investigação, diagnóstico de incidentes e uma pergunta de descoberta),
faz cada uma ao agente e corrige automaticamente. Registra acerto, tempo, tokens e custo de cada
tentativa num JSON.

```bash
uv run isoterma avaliar-ia data/demo --llm claude --amostra 3     # 3 perguntas, para estimar o custo
uv run isoterma avaliar-ia data/demo --llm claude
uv run isoterma avaliar-ia data/demo --llm claude --llm gemini:<modelo> --resultado docs/avaliacao/demo.json
uv run isoterma avaliar-ia data/demo --llm claude --versao v1     # o conjunto original
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--llm` | provedor a avaliar; repita para comparar vários | **obrigatória**, para não gastar sem querer |
| `--amostra` | roda só as N primeiras perguntas | todas |
| `--versao` | `v2` (atual, mais difícil) ou `v1` (o conjunto original, mantido como registro) | `v2` |
| `--resultado` | onde gravar o JSON | `<simulação>/avaliacao-ia.json` |

### `relatorio-ia`

Gera o relatório em Markdown de uma ou mais avaliações: acerto por provedor e por categoria,
tempo médio, custo e o resultado de cada pergunta. Com vários JSONs, cada versão vira uma seção,
a mais nova primeiro.

```bash
uv run isoterma relatorio-ia data/demo/avaliacao-ia.json
uv run isoterma relatorio-ia docs/avaliacao/demo-v2.json docs/avaliacao/demo-v1.json
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--saida` | arquivo Markdown de saída | `docs/AVALIACAO_IA.md` |

---

## Anomalias

Os detectores são regras explicáveis, sem IA e sem custo. O método está em
[ANOMALIAS.md](ANOMALIAS.md) e os resultados em [DETECCAO.md](DETECCAO.md).

### `detectar`

Procura os 8 tipos de anomalia (falhas e super-refrigeração de CRAC, rack sobrecarregado,
recirculação e quatro defeitos de sensor) e mostra cada alerta com o período, no fuso da
simulação, e a evidência. Não lê o gabarito: funciona igual numa pasta sem `incidentes.parquet`.

```bash
uv run isoterma detectar data/demo
uv run isoterma detectar data/demo --tipo falha_crac --tipo recirculacao
uv run isoterma detectar data/demo --json alertas.json
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--tipo` | mostra só esses tipos; repita para vários | todos |
| `--json` | grava também as detecções, os limiares e o tempo de cada etapa em JSON | não grava |

### `avaliar-deteccao`

Roda os detectores em várias simulações e compara com o gabarito de cada uma: precisão, recall,
F1 e atraso por tipo, mais a lista de incidentes perdidos e de alertas falsos.

```bash
uv run isoterma avaliar-deteccao data/teste-demo-* data/teste-estresse-* --grupo teste
uv run isoterma avaliar-deteccao data/calib-* --grupo calibracao --resultado calib.json
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--grupo` | nome do conjunto: `calibracao`, `validacao` ou `teste` | `teste` |
| `--resultado` | onde gravar o JSON | `docs/deteccao/<grupo>.json` |

### `relatorio-deteccao`

Gera o relatório em Markdown a partir dos JSONs do `avaliar-deteccao`, com uma seção por
conjunto.

```bash
uv run isoterma relatorio-deteccao docs/deteccao/*.json
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--saida` | arquivo Markdown de saída | `docs/DETECCAO.md` |

---

## API

### `servir`

Sobe a API HTTP que a web usa: as consultas do motor e o agente de IA, com documentação
interativa em `http://127.0.0.1:8000/docs`. Recebe a pasta que contém as simulações (`data`, por
padrão) e serve todas elas. Detalhes das rotas em [API.md](API.md).

```bash
uv sync --extra api --extra claude
uv run isoterma servir                                   # sem IA
uv run isoterma servir data --llm claude                 # com a IA
uv run isoterma servir --porta 9000 --origem https://meu-front.dev
```

| Opção | O que faz | Padrão |
|---|---|---|
| `--host` | endereço de escuta; use `0.0.0.0` para aceitar conexões de fora da máquina | `127.0.0.1` |
| `--porta` | porta HTTP | 8000 |
| `--llm` | provedor da IA, como no `perguntar` | `ISOTERMA_LLM`; sem nenhum dos dois, IA desligada |
| `--perguntas-por-hora` | limite de perguntas à IA por IP | 20 |
| `--teto-diario` | teto de gasto estimado da IA por dia, em dólares | 1,0 |
| `--origem` | origem liberada no CORS; repita para várias | o Vite local (`http://localhost:5173`) |
| `--atras-de-proxy` | identifica o IP do cliente pelo `X-Forwarded-For` | não |
| `--preparar` | simulação cujas anomalias são calculadas ao subir, em segundo plano, para a página de anomalias não esperar; repita para várias | `demo` |

Para parar o servidor, use Ctrl+C.

---

## Desenvolvimento

Estes não são comandos do Isoterma, mas são os que você usa para trabalhar no projeto:

```bash
uv sync --all-extras          # instala tudo, inclusive os SDKs de IA usados nos testes
uv run pytest --cov           # testes com cobertura (nenhum chama API paga)
uv run ruff check             # lint
uv run ruff format            # formatação
uv run pyright                # checagem de tipos
uv run pre-commit install     # roda lint, formatação e tipos antes de cada commit
```
