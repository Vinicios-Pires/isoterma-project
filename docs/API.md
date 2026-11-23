# API

A API HTTP expõe o motor e o agente para a web. Cada rota é uma camada fina sobre o `Hall`: as
consultas, o SQL seguro e a IA são os mesmos da CLI.

```bash
uv sync --extra api --extra claude
uv run isoterma servir data --llm claude
```

A documentação interativa (Swagger) fica em `http://127.0.0.1:8000/docs`, e o esquema OpenAPI
em `/openapi.json`. O front gera os tipos TypeScript a partir dele.

## Rotas

Todas ficam sob `/api`. `{simulacao}` é o nome de uma pasta de simulação dentro da pasta de
dados (por exemplo, `demo`).

| Método | Rota | Devolve |
|---|---|---|
| GET | `/saude` | status, versão, quantas simulações e qual LLM está configurado |
| GET | `/simulacoes` | as simulações disponíveis: tamanho, período, fuso e camadas de dados |
| GET | `/{simulacao}/planta` | racks e CRACs com coordenadas, para desenhar o hall |
| GET | `/{simulacao}/resumo?inicio&fim` | visão geral da janela |
| GET | `/{simulacao}/mapa?instante&tipo&altura` | valor de cada rack num instante, com a faixa ASHRAE |
| GET | `/{simulacao}/fora-da-faixa?inicio&fim` | racks que saíram de 18–27 °C |
| GET | `/{simulacao}/serie?alvo&inicio&fim&pontos` | série de um sensor, rack ou CRAC |
| GET | `/{simulacao}/gabarito` | os incidentes injetados (só existe porque os dados são simulados) |
| GET | `/{simulacao}/anomalias` | os alertas dos detectores, com a evidência de cada um e a avaliação contra o gabarito |
| POST | `/{simulacao}/perguntar` | a IA, em streaming (SSE) |

- **Datas** vão em ISO 8601. Sem fuso (`2026-11-07T04:15`), valem no horário local do hall; com
  fuso (`2026-11-07T07:15Z`), valem como estão. As respostas vêm sempre em UTC.
- **Erros** seguem o padrão do FastAPI, `{"detail": "..."}`: `404` para simulação inexistente,
  `400` para erros de domínio (janela fora da simulação, alvo que não existe), `422` para
  parâmetros inválidos, `429` para limite de uso da IA e `503` para IA desligada ou mal
  configurada.

## Anomalias

A rota `/anomalias` roda os [detectores](ANOMALIAS.md) sobre a simulação inteira. Como isso leva
de 5 a 25 s, o resultado fica em memória: só o primeiro pedido de cada simulação espera, e
pedidos simultâneos aguardam o mesmo cálculo. O `servir` já calcula a `demo` ao subir (opção
`--preparar`), para a primeira visita à página não esperar.

- **Cada alerta** traz tipo, alvo (`B-05/entrada-topo`), o equipamento (`B-05`), o período, a
  frase com o que foi visto e o valor que mais se afastou do normal.
- **Os detectores não leem o gabarito.** A comparação é feita depois, à parte: cada alerta traz
  os `incidentes` do gabarito que acertou (vazio é alerta falso), e `avaliacao` traz o placar
  total e por tipo, os incidentes perdidos e os que não afetaram nenhuma leitura.
- **Numa simulação sem gabarito** (sem o `incidentes.parquet`), `avaliacao` e `incidentes` vêm
  nulos e os alertas continuam lá: é o caso de um data center real.

## `perguntar` em streaming

O corpo é `{"pergunta": "..."}`. A resposta é `text/event-stream`, com três tipos de evento (os valores abaixo são ilustrativos):

```
event: passo
data: {"ferramenta":"fora_da_faixa","argumentos":{"inicio":"2026-11-07T00:00","fim":"2026-11-07T06:00"},
       "segundos":0.08,"linhas":14,"sql":null,"erro":false,"mensagem_erro":null}

event: passo
data: {"ferramenta":"consultar_sql","argumentos":{"sql":"SELECT ..."},"segundos":0.12,...}

event: resposta
data: {"texto":"O CRAC-02 falhou...","parada":"fim","detalhe":"","provedor":"claude",
       "modelo":"claude-haiku-5-5","turnos":3,"segundos":9.4,"tokens_entrada":13000,
       "tokens_saida":600,"tokens_cache":8400,"custo_usd":0.0031}
```

- **`passo`** chega ao vivo, a cada ferramenta que o agente chama, com o SQL quando é uma
  consulta livre.
- **`resposta`** é o último evento quando tudo dá certo.
- **`erro`** (`{"mensagem": "..."}`) substitui a resposta quando o provedor falha no meio, por
  exemplo com uma chave recusada.

Os problemas que dá para checar antes, como IA desligada, provedor mal configurado, limite
atingido ou simulação inexistente, voltam como resposta HTTP comum, sem abrir o streaming.

Como é um `POST`, no navegador o streaming é lido com `fetch` e um leitor do corpo, e não com
`EventSource`, que só faz `GET`.

Os modelos dos três eventos (`EventoPasso`, `EventoResposta`, `EventoErro`) entram no OpenAPI
em `components.schemas`, mesmo sem a rota devolver JSON, para o front gerar os tipos deles.

Para testar no terminal, use um arquivo com o corpo em UTF-8. No Windows, o curl repassa o texto
digitado no comando com outro encoding, e uma pergunta com acento chega corrompida (`There was
an error parsing the body`):

```bash
curl -N -X POST http://127.0.0.1:8000/api/demo/perguntar      -H "Content-Type: application/json" --data-binary @pergunta.json
```

## Configuração e proteções

| Opção do `servir` | Para quê | Padrão |
|---|---|---|
| `--llm` | provedor da IA; sem ele (e sem `ISOTERMA_LLM`), a IA fica desligada | desligada |
| `--perguntas-por-hora` | limite de perguntas por IP | 20 |
| `--teto-diario` | teto de gasto estimado da IA por dia (UTC), somando todas as perguntas | US$ 1,00 |
| `--origem` | origens liberadas no CORS | o Vite local (`localhost:5173`) |
| `--atras-de-proxy` | identifica o cliente pelo `X-Forwarded-For` (Cloud Run, por exemplo) | não |

- **A IA vem desligada por padrão**, para um deploy público não gastar sem querer.
- **O nome da simulação só é aceito se for uma das pastas listadas**, então não dá para pedir
  caminhos arbitrários.
- **Todas as consultas passam pelo modo seguro do motor**, e a IA nunca vê o gabarito. A rota
  `/gabarito` usa uma conexão separada.
- **Os limites de uso ficam em memória.** Valem por instância do servidor e recomeçam quando
  ele reinicia, o que basta para proteger uma demo.

## Testes

`tests/api/` testa cada rota com o `TestClient` do FastAPI sobre uma simulação pequena: as
respostas, os erros HTTP, o CORS, o streaming (com o provedor falso e com uma falha do provedor
no meio), o limite por IP, o IP vindo do proxy, o teto diário e o comando `servir`.
