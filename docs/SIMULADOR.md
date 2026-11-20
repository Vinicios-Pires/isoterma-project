# Simulador de data hall

O simulador gera a telemetria térmica de um data hall fictício, com **incidentes injetados de
propósito** e um **gabarito** que diz o que aconteceu, onde e quando. É a matéria-prima do
Isoterma: o mapa térmico, a detecção de anomalias e as perguntas em linguagem natural partem
desses dados.

```bash
uv run isoterma simular --preset demo          # 30 dias, 200 racks, ~44 milhões de leituras
uv run isoterma simular --preset bilhao        # 1 bilhão de leituras
uv run isoterma simular --config meu_hall.toml # um hall próprio
```

## Desempenho

Medido num AMD Ryzen 5 5600 (6 núcleos, 12 threads), 16 GB de RAM e Windows 11, com Python 3.14:

| Preset | Racks | Sensores | Frequência | Período | Leituras | Em disco | Geração |
|---|---|---|---|---|---|---|---|
| `teste` | 10 | 54 | 1/min | 1 dia | 77.760 | ~100 KB | < 2 s |
| `demo` | 200 | 1.012 | 1/min | 30 dias | 43.718.400 | 53,6 MB | 6,7 s |
| `bilhao` | 1.000 | 5.024 | 1/s | ~2,3 dias | 1.000.002.080 | 1,5 GB | **20,1 s** |

Sobre o bilhão de leituras, o cálculo do desafio original (mínimo, média e máximo por sensor)
leva cerca de **3,3 s no DuckDB**.

Para comparação, o gerador do projeto original levava cerca de 10 minutos para escrever um
`.txt` de ~14 GB e, por um bug, gerava só 1 milhão de linhas (ver [EVOLUCAO.md](EVOLUCAO.md)).

## A planta

```
          CRAC-01              CRAC-02              CRAC-03
   ┌─────────────────────────────────────────────────────────┐
   │ A  ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮                                  │
   │    ░░░░░░░░░░ corredor frio (ar insuflado) ░░░░░░░░░░░    │
   │ B  ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮                                  │
   │    ▓▓▓▓▓▓▓▓▓▓ corredor quente (retorno ao CRAC) ▓▓▓▓▓▓    │
   │ C  ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮                                  │
   └─────────────────────────────────────────────────────────┘
          CRAC-04              CRAC-05              CRAC-06
```

- Fileiras com letras (A, B, C…) e racks numerados (`C-07` é o 7º rack da fileira C).
- Metade dos CRACs fica na parede de cima e metade na de baixo.
- A influência de cada CRAC sobre cada rack decai com a distância (`exp(-d / alcance)`). O CRAC
  de maior influência é a `zona_crac` do rack.
- Cerca de 10% dos racks são "densos" (12–16 kW, como os de GPU). Os demais consomem 4–8 kW.

## Sensores

| Tipo | Quantidade | Onde | Valor típico |
|---|---|---|---|
| `temp_entrada` | 3 por rack | frente, nas alturas base, meio e topo | 20–23 °C |
| `temp_saida` | 1 por rack | traseira | ~32 °C |
| `potencia_kw` | 1 por rack | PDU | 2–16 kW |
| `temp_insuflamento` | 1 por CRAC | saída de ar frio | ~19,5 °C |
| `temp_retorno` | 1 por CRAC | entrada de ar quente | ~32 °C |

As temperaturas são gravadas com uma casa decimal, como em sensores reais, e a potência com duas.

## O modelo físico

É um modelo simplificado e explicável, não uma simulação de fluidos (CFD). Ele roda em **dois
níveis**:

**1. Física lenta, em resolução de 1 minuto** (`fisica.py`):

- **Carga de TI:** potência nominal × ciclo diário (pico às 15h no horário local) × queda de 8%
  nos fins de semana × ruído correlacionado no tempo (AR(1)).
- **Insuflamento:** o setpoint do CRAC, com inércia térmica de primeira ordem (constante de
  tempo de 6 min). Quando o CRAC falha, o insuflamento caminha em direção ao ar de retorno, e
  os CRACs vizinhos compensam parte da área dele.
- **Entrada do rack:** média do insuflamento ponderada pela influência de cada CRAC, mais a
  **recirculação** de ar quente, que é maior no topo do rack e nas pontas das fileiras.
- **Saída do rack:** entrada + ΔT proporcional à carga (15 °C a 100% da potência nominal).
- **Retorno do CRAC:** média das saídas dos racks que ele atende. Isso fecha o laço: um CRAC
  que falha passa a soprar ar mais quente, que aquece os racks, que aquecem o retorno.

**2. Leituras, na frequência final** (`gerador.py`): os valores do nível 1 são interpolados, e
cada sensor ganha ruído de medição e um pequeno erro de calibração fixo. Os defeitos de sensor
entram aqui.

O período é dividido em **blocos independentes**, que nunca atravessam a meia-noite UTC. Cada
bloco sorteia números de um fluxo aleatório próprio, derivado da seed. Por isso:

- os blocos rodam **em paralelo de verdade** (um processo por núcleo), cada um gravando seu
  próprio arquivo Parquet;
- a mesma seed gera **exatamente os mesmos dados**, com qualquer número de processos.

## Catálogo de incidentes

| Tipo | Alvo | Efeito | Intensidade |
|---|---|---|---|
| `falha_crac` | CRAC | a zona aquece gradualmente e pode passar de 27 °C | fração da refrigeração perdida (0,7–1,0) |
| `super_refrigeracao` | CRAC | a zona fica fria demais (desperdício de energia) | °C abaixo do setpoint (3–5) |
| `rack_sobrecarregado` | rack | a potência sobe e a saída esquenta | carga extra (0,5–1,0 = +50% a +100%) |
| `recirculacao` | rack | o topo fica mais quente de forma persistente | °C a mais no topo (3–6) |
| `sensor_congelado` | sensor | repete sempre o mesmo valor | — |
| `sensor_deriva` | sensor | o valor sobe aos poucos, sem causa física | °C por hora (0,1–0,5) |
| `sensor_picos` | sensor | valores absurdos esporádicos (±8 a 25 °C) | fração das leituras (1–5%) |
| `sensor_sem_leitura` | sensor | leituras nulas | fração das leituras (50–100%) |

Os quatro primeiros mudam a física do hall. Os defeitos de sensor mudam **só o dado**. Distinguir
um do outro ("o rack está quente ou o sensor está com defeito?") é um dos desafios que o
Isoterma vai resolver.

Os incidentes são sorteados por **taxas diárias**, proporcionais ao tamanho do hall, ou
**programados**. Os presets `demo` e `bilhao` têm um roteiro fixo: um CRAC falha às 2h da
madrugada (horário de Brasília).

## Esquema dos dados

```
data/<nome>/
  manifesto.json        config, seed, versão, contagens, tempo de geração e dicionário de dados
  sensores.parquet      cadastro dos sensores
  racks.parquet         cadastro dos racks
  cracs.parquet         cadastro dos CRACs
  incidentes.parquet    o gabarito
  leituras/data=2026-11-01/parte-00000.parquet ...   particionado por dia (UTC)
```

| Tabela | Colunas |
|---|---|
| `leituras` | `ts` (UTC) · `sensor_id` · `valor` (float32, nulo quando não houve leitura) |
| `sensores` | `sensor_id` · `codigo` · `tipo` · `unidade` · `altura` · `rack_id` · `crac_id` · `x_m` · `y_m` |
| `racks` | `rack_id` · `fileira` · `posicao` · `x_m` · `y_m` · `potencia_nominal_kw` · `perfil` · `zona_crac` |
| `cracs` | `crac_id` · `x_m` · `y_m` · `setpoint_c` |
| `incidentes` | `incidente_id` · `tipo` · `alvo_tipo` · `alvo` · `inicio` · `fim` · `intensidade` · `descricao` |

O dicionário completo, com a descrição de cada coluna, está em `isoterma.simulador.esquema` e é
copiado para o `manifesto.json`. Ele será o contexto que a IA recebe para gerar SQL na fase 2.

Para consultar no DuckDB:

```python
from pathlib import Path
from isoterma.dados import conectar

db = conectar(Path("data/demo"))
db.sql("""
    SELECT r.rack_id, max(l.valor) AS pico
    FROM leituras l JOIN sensores s USING (sensor_id) JOIN racks r USING (rack_id)
    WHERE s.tipo = 'temp_entrada'
    GROUP BY r.rack_id
    HAVING pico > 27
    ORDER BY pico DESC
""").show()
```

Também dá para exportar as temperaturas no formato do desafio original (`codigo;valor`):

```bash
uv run isoterma exportar-1brc data/demo --destino medicoes.txt
```

## Configuração própria

Um arquivo TOML define um hall sob medida. Os campos omitidos usam os valores padrão de
`isoterma.simulador.config`.

```toml
seed = 7

[hall]
fileiras = 6
racks_por_fileira = 12
cracs = 4

[periodo]
inicio = 2026-12-01T00:00:00Z
dias = 7
intervalo_s = 30

[termica]
setpoint_c = 20.0

[incidentes.taxas_por_dia]
falha_crac = 0.2
sensor_congelado = 0.5

[[incidentes.programados]]
tipo = "recirculacao"
inicio_h = 30
duracao_min = 600
alvo = "D-04"
intensidade = 5.0
```

## Limitações conhecidas

- Não há umidade nem clima externo. Os dois entram na fase 3.
- Os CRACs ficam só nas paredes. Em halls muito largos, as fileiras do meio recebem influência
  quase igual de todos os CRACs.
- O ciclo diário usa o fuso do início do período, sem horário de verão. O Brasil não tem horário
  de verão desde 2019.
- A recirculação é um termo fixo por rack e altura, e não depende do fluxo de ar real.
