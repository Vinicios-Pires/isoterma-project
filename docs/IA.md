# A camada de IA

O Isoterma responde perguntas em português sobre o hall. Um **agente** recebe a pergunta,
consulta os dados pelas ferramentas do motor e responde com os fatos que encontrou, mostrando
cada consulta que fez.

```bash
uv sync --extra claude
export ANTHROPIC_API_KEY=...        # PowerShell: $env:ANTHROPIC_API_KEY = "..."
uv run isoterma perguntar data/demo "o que aconteceu na fileira A no dia 7 de madrugada?"
```

Um exemplo ilustrativo do formato da saída (o texto real depende do modelo):

```
  → fora_da_faixa(inicio='2026-11-07T00:00', fim='2026-11-07T06:00')  0,08 s, 14 linhas
  → serie(alvo='CRAC-02', inicio='2026-11-07T01:00', fim='2026-11-07T05:00', pontos=24)  0,05 s, 48 linhas

O CRAC-02 falhou por volta das 2h e a zona dele aqueceu: ...
```

Sem chave, `--llm falso` roda um provedor de demonstração, sem rede e sem custo.

## Como funciona

```
pergunta ──► modelo ──► chamadas de ferramenta ──► motor (Hall em modo seguro) ──► resultados
                ▲                                                                     │
                └──────────────────── até concluir (máx. 12 turnos) ◄─────────────────┘
```

| Ferramenta | O que faz | Vem de |
|---|---|---|
| `resumo` | visão geral de uma janela | `Hall.resumo` |
| `mapa_termico` | valor de cada rack num instante, com a faixa ASHRAE | `Hall.mapa_termico` |
| `fora_da_faixa` | racks fora de 18–27 °C, com duração e horários | `Hall.fora_da_faixa` |
| `serie` | série de um sensor, rack ou CRAC | `Hall.serie` |
| `consultar_sql` | SELECT livre, no máximo 50 linhas | `Hall.consultar` (SQL seguro) |

- **Ferramentas de domínio primeiro.** Elas fazem as contas certas e escolhem a camada de dados
  mais barata. O SQL livre fica para o que elas não cobrem.
- **Argumentos validados.** Cada ferramenta tem um modelo pydantic, e o JSON Schema enviado ao
  provedor é estrito (todos os campos obrigatórios, sem extras). Argumentos inválidos, SQL
  com erro ou consultas recusadas voltam ao modelo como resultado de erro, com a mensagem, e
  ele se corrige no turno seguinte.
- **Horários.** As ferramentas de domínio recebem e devolvem o horário local do hall. No SQL,
  as tabelas estão em UTC, e as instruções explicam a conversão.
- **O laço é do Isoterma**, e não do SDK de um provedor. Assim ele é idêntico com qualquer
  modelo. Cada adaptador só traduz mensagens e ferramentas para o formato nativo e guarda o
  histórico nesse formato, porque os modelos com raciocínio exigem que o que devolveram
  (blocos de thinking, assinaturas, raciocínio cifrado) volte intacto.

## O que a IA vê, e o que não vê

- **Não recebe os arquivos.** Vê as instruções, o dicionário de dados e os resultados das
  consultas que pede, limitados a 50 linhas no SQL e a 200 nas outras ferramentas.
- **Não vê o gabarito.** O agente usa um `Hall(ocultar_gabarito=True)`: a tabela `incidentes`
  não existe na conexão, e o arquivo fica fora da lista de caminhos liberados do DuckDB. Nem um
  `read_parquet` direto o alcança. Sem isso, a avaliação abaixo seria trapaça.
- **Não altera nada.** Todo SQL passa pelo SQL seguro do motor: só um SELECT, conexão travada,
  teto de linhas e de tempo.
- **Na OpenAI, nada fica guardado** (`store=False`): o histórico, inclusive o raciocínio cifrado,
  é mantido localmente e reenviado a cada turno.

## Provedores

| `--llm` / `ISOTERMA_LLM` | SDK | Credencial | Extra |
|---|---|---|---|
| `claude` (padrão: Claude Haiku 5.5) ou `claude:<modelo>` | `anthropic` | `ANTHROPIC_API_KEY` ou `ant auth login` | `uv sync --extra claude` |
| `openai:<modelo>` | `openai` (Responses API) | `OPENAI_API_KEY` | `uv sync --extra openai` |
| `gemini:<modelo>` | `google-genai` | `GEMINI_API_KEY` | `uv sync --extra gemini` |
| `falso` | nenhum | nenhuma | nenhum |

- OpenAI e Gemini não têm modelo padrão: os nomes mudam com frequência, então o modelo é
  escolhido explicitamente.
- No Claude, os pedidos usam esforço `medium`, cache automático do prefixo (instruções e
  ferramentas são iguais em toda pergunta) e ferramentas estritas. Nos modelos que têm
  *fallback* no servidor (Opus 5.5, Sonnet 5.5 e outros), uma resposta recusada pelo filtro de
  segurança é refeita automaticamente em outro modelo. O Haiku 5.5 não tem esse recurso.
- **A API é cobrada à parte das assinaturas** (claude.ai, ChatGPT etc.), por token, com créditos
  da conta de API de cada provedor. O custo estimado aparece no fim de cada resposta para os
  modelos com preço conhecido. Com o Haiku 5.5, uma pergunta custa por volta de US$ 0,003.

## Avaliação

`isoterma avaliar-ia` mede quanto cada modelo acerta. As perguntas são **geradas a partir da
simulação**: as respostas esperadas saem do motor e do gabarito de incidentes, então valem para
qualquer seed. A resposta é corrigida pela última linha `RESPOSTA: <valor>`, que a avaliação pede
ao agente. Os resultados estão em [AVALIACAO_IA.md](AVALIACAO_IA.md).

Na v2, o conjunto atual, a demo tem 19 perguntas em quatro categorias:

| Categoria | Exemplos | Correção |
|---|---|---|
| Fatos | quantos racks há; qual CRAC refrigera um rack; temperatura média; sensores com falta de leitura | número com tolerância ou texto exato |
| Investigação | quais racks passaram de 27 °C por um evento real em volta da falha de CRAC; a que horas começou | conjunto (Jaccard ≥ 0,85) e horário (± 3 min) |
| Diagnóstico | *houve algo anormal no rack X entre ... e ...? Se houve, qual a causa?*: `falha_crac`, `super_refrigeracao`, `sobrecarga`, `recirculacao`, `defeito_sensor` ou `normal` | opção exata |
| Descoberta | *quais incidentes aconteceram no dia X?*, sem pista nenhuma | F1 ≥ 0,7 entre os `categoria:alvo` apontados e o gabarito |

- **O diagnóstico pergunta sempre pelo rack.** Num defeito de sensor, o rack é o dono do sensor;
  num incidente de CRAC, é o rack da zona mais perto dele. O modelo precisa descobrir sozinho
  se a causa é um sensor, o CRAC ou o próprio rack. Incidentes que coincidem com outro no mesmo
  rack ficam de fora, porque a resposta seria ambígua.
- **Três controles** fazem a mesma pergunta para racks e janelas sem nenhum incidente, em que a
  resposta certa é `normal`. Um modelo que vê problema em tudo também erra.
- **A descoberta** escolhe o dia mais variado da simulação, com 2 a 8 incidentes. Um defeito de
  sensor conta se o modelo apontar o sensor ou o rack dele.

A **v1**, o primeiro conjunto, perguntava pelo alvo do incidente (*o que aconteceu com o sensor
X?*), o que já entregava metade do diagnóstico, e o Claude Haiku 5.5 acertou as 17 perguntas.
Ela continua disponível (`--versao v1`) e o resultado dela fica no relatório como registro.

```bash
uv run isoterma avaliar-ia data/demo --llm claude --amostra 3     # estima o custo antes
uv run isoterma avaliar-ia data/demo --llm claude --llm gemini:<modelo> --resultado docs/avaliacao/demo-v2.json
uv run isoterma relatorio-ia docs/avaliacao/demo-v2.json docs/avaliacao/demo-v1.json
```

`avaliar-ia` não tem provedor padrão, para não gastar sem querer. Registra acerto, tempo,
turnos, ferramentas chamadas, tokens e custo de cada tentativa.

## Testes

Nenhum teste chama uma API. O laço é testado com um provedor falso roteirizado. Os adaptadores
são testados com respostas construídas com os tipos dos próprios SDKs e um cliente que registra
o que seria enviado: ferramentas estritas, cache, histórico com o raciocínio intacto, resultados
de ferramenta, recusas e limites.
