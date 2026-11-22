# A web

O front do Isoterma: um console de operação para ver o hall, voltar no tempo e entender o que
aconteceu. Fica em `web/` e consome a [API](API.md).

```bash
# terminal 1: a API, com as simulações da pasta data/
uv sync --extra api
uv run isoterma servir data

# terminal 2: o front, em modo de desenvolvimento
cd web
npm install
npm run dev          # http://localhost:5173
```

Em desenvolvimento, o Vite encaminha `/api` para `http://127.0.0.1:8000`; para outra API, use
`ISOTERMA_API=http://... npm run dev`. No build, `VITE_API_URL` define o endereço da API (vazio:
o mesmo domínio do front).

## Telas

| Tela | Rota | O que mostra |
|---|---|---|
| Painel | `/:simulacao` | indicadores do período, racks fora da faixa ASHRAE (o horário abre o mapa naquele momento), mínimo, média e máximo por tipo de sensor, e a linha do tempo dos incidentes injetados |
| Mapa térmico | `/:simulacao/mapa` | a planta do hall com as isotermas, o controle de tempo e o detalhe do rack; clicar num CRAC abre as séries dele |
| Rack | `/:simulacao/rack/:id` | ficha do rack e séries de temperatura (entrada nas 3 alturas e saída) e de potência |
| CRAC | `/:simulacao/crac/:id` | setpoint, os racks da zona e as séries de insuflamento e retorno |
| Perguntar | `/:simulacao/perguntar` | o chat com a IA, com cada consulta mostrada ao vivo |

A raiz (`/`) abre a simulação `demo`, se existir, ou a primeira da lista.

**O estado do mapa fica na URL** (`?t=2026-11-07T07:15:00Z&tipo=temp_entrada&altura=topo&rack=A-11`):
dá para compartilhar um momento exato e voltar com o navegador.

## O mapa de isotermas

Os sensores ficam nos racks, então a temperatura entre eles é **estimada**:

1. os valores dos racks são interpolados numa grade fina (inverso da distância ao quadrado,
   só com os racks a até 2,6 m), com cerca de 20 mil células;
2. o `d3-contour` traça as curvas de nível dessa grade, a cada 1 °C na entrada;
3. as regiões acima de cada nível são pintadas em ordem crescente e formam as faixas de cor;
   o contorno de cada uma é a isoterma daquele valor;
4. as isotermas de 18 e 27 °C (os limites da faixa ASHRAE) aparecem tracejadas e mais grossas.

O SVG trabalha em metros, no mesmo sistema de coordenadas do simulador. **Um hall mais fundo que
largo é desenhado girado** (as fileiras viram colunas), para caber na tela sem rolagem. A
legenda avisa que, entre os racks, os valores são interpolados.

O controle de tempo anda em passos de 5 minutos (ou o intervalo das leituras, se for maior). O
play avança um passo por vez e só pede o próximo mapa quando o anterior chegou. Enquanto isso, o
mapa anterior continua na tela, sem piscar.

## Séries de rack e CRAC

- **Um gráfico por unidade, nunca dois eixos:** temperatura num, potência noutro, com a
  linha-guia sincronizada entre eles.
- **Cada ponto é a média do intervalo**, e o intervalo se ajusta à janela (a API escolhe a
  camada de dados). O tooltip lista todas as séries, com o valor primeiro e o mínimo e o
  máximo ao lado.
- **Arrastar no gráfico amplia o trecho.** "Afastar" e "Período inteiro" voltam. A janela fica
  na URL (`?inicio=...&fim=...`), e os links do mapa e do painel já abrem 6 horas em volta do
  momento de interesse.
- **Linhas de referência:** 18 e 27 °C no rack, o setpoint no CRAC.
- **"Incidentes da simulação"** sombreia no fundo os períodos do gabarito que tocam o
  equipamento, o CRAC da zona ou os sensores dele. Fica desligado por padrão: com ele ligado, é
  a "cola" para comparar o que aconteceu com o que os dados mostram.
- **Cores das séries:** a paleta categórica validada para daltonismo e contraste nos dois
  temas, sempre na mesma ordem (entrada base, meio, topo, saída). Como duas cores ficam abaixo
  de 3:1 no tema claro, toda série tem legenda e todo gráfico tem **"Ver como tabela"**.

## Perguntar

- **Streaming:** a resposta do `perguntar` é lida com `fetch` e um leitor do corpo, já que o
  `EventSource` do navegador só faz GET. O leitor (`lib/sse.ts`) remonta eventos e caracteres
  acentuados cortados entre pedaços da rede.
- **Cada consulta aparece ao vivo:** ferramenta, argumentos, tempo, linhas e o SQL, que fica
  recolhido. Quando a resposta chega, a lista de consultas se recolhe.
- **A resposta vem em Markdown** (listas, negrito, tabelas), com o rodapé do provedor, modelo,
  tempo, tokens (e quanto veio do cache) e o custo estimado.
- **Dá para interromper** uma pergunta em andamento.
- **Cada pergunta é independente:** o agente não lembra das anteriores, e a tela diz isso.
- **Sem IA no servidor**, a página explica como ligar, em vez de deixar a pessoa perguntar e
  receber um erro. Limite de uso e falhas do provedor aparecem como mensagens claras.

## Visual

- **Console de operação:** neutros levemente azulados, um acento azul-petróleo para a interface e
  as cores térmicas reservadas para os dados, do azul (frio) ao vermelho (quente), com o centro
  neutro em 21 °C, a temperatura de operação normal.
- **Tipografia:** IBM Plex Sans para o texto e IBM Plex Mono para números e códigos (`C-07`,
  `CRAC-02`), com algarismos tabulares.
- **Temas claro e escuro**, seguindo o sistema na primeira visita, com alternância no cabeçalho.
- **Formatação brasileira** em tudo (`43.718.400`, `20,2 °C`), e **horários no fuso do hall**,
  não no de quem abre a página.

## Stack

| | |
|---|---|
| Base | React 19, Vite 8, TypeScript 7 |
| Interface | Tailwind CSS 4 e shadcn/ui (sobre Base UI), ícones Lucide |
| Dados | TanStack Query (cache, carregamento, erros), React Router |
| Visualização | D3 (`d3-contour`, `d3-geo`, `d3-scale`) para as isotermas; Recharts para as séries |
| Texto | `react-markdown` + `remark-gfm` para as respostas da IA |
| Qualidade | Vitest e Testing Library, oxlint |

## Tipos gerados da API

Os tipos TypeScript das respostas vêm do OpenAPI da API, então front e back não divergem:

```bash
cd web
npm run tipos     # exporta web/src/api/openapi.json e gera web/src/api/esquema.ts
```

Um teste do lado Python (`tests/api/test_openapi.py`) falha se a API mudar e o `openapi.json`
commitado não acompanhar. O `openapi-typescript` roda isolado via `npx`, porque ainda exige o
TypeScript 5, e o projeto usa o 7.

## Scripts

| Comando (em `web/`) | O que faz |
|---|---|
| `npm run dev` | servidor de desenvolvimento com recarga automática |
| `npm run build` | checagem de tipos e build de produção em `web/dist/` |
| `npm run teste` | testes (Vitest) |
| `npm run lint` | lint (oxlint) |
| `npm run tipos` | regenera os tipos a partir da API |

O CI roda lint, testes e build do front num job próprio.

## Testes

- **Utilitários:** a interpolação (reproduz o valor exato sobre o rack, fica entre os vizinhos,
  deixa vazio longe de tudo), as isotermas (uma curva por limiar presente, em metros), a
  geometria da planta (giro, CRACs afastados da parede, rótulos), as escalas de cor e a
  formatação de números e datas no fuso do hall.
- **SSE e séries:** eventos e acentos cortados entre pedaços, o pivô das séries e a janela
  em volta de um instante.
- **Componentes:** a planta (um bloco por rack, a isoterma de 27 °C quando uma zona passa do
  limite, o contorno dos racks fora da faixa, seleção e dica) e as páginas com uma API falsa
  (indicadores, tabela, links para o mapa, erros da API e simulação inexistente).

- **Detalhe e Perguntar:** o pedido da série com a janela da URL, a ficha, a visão em tabela, o
  streaming simulado (consultas, Markdown, custo e lista recolhida), o erro no meio do fluxo, o
  limite de uso e a IA desligada.

Mapa, Detalhe e Perguntar são carregados só quando abertos (D3, Recharts e o Markdown ficam
fora do pacote inicial).
