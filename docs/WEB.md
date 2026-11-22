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
| Mapa térmico | `/:simulacao/mapa` | a planta do hall com as isotermas, o controle de tempo e o detalhe do rack |

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
| Visualização | D3 (`d3-contour`, `d3-geo`, `d3-scale`) para as isotermas; Recharts para as séries (próximo PR) |
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
- **Componentes:** a planta (um bloco por rack, a isoterma de 27 °C quando uma zona passa do
  limite, o contorno dos racks fora da faixa, seleção e dica) e as páginas com uma API falsa
  (indicadores, tabela, links para o mapa, erros da API e simulação inexistente).

O pacote do mapa (com o D3) é carregado só quando a página é aberta.
