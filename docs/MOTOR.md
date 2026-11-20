# Motor de consultas

O motor é a camada entre os dados e tudo o que vem depois: a CLI, a API, a IA e a demo web. Ele
faz três coisas:

1. mantém as **camadas de dados** (as leituras brutas e os agregados);
2. oferece **consultas de domínio** prontas (mapa térmico, faixa ASHRAE, séries, resumo),
   escolhendo sozinho a camada mais barata para cada pergunta;
3. executa **SQL livre com segurança**, a base para as perguntas em linguagem natural da fase 2.

```python
from pathlib import Path
from isoterma.motor import Hall, agregar

agregar(Path("data/demo"))  # gera a camada ouro (uma vez)

with Hall(Path("data/demo")) as hall:
    hall.resumo()
    hall.mapa_termico()  # pyarrow.Table com um valor por rack
    hall.fora_da_faixa()
    hall.serie("C-07")
    hall.consultar("SELECT count(*) FROM incidentes")
```

## Camadas de dados

| Camada | Tabela | O que guarda | `demo` (30 dias) | `bilhao` |
|---|---|---|---|---|
| bronze | `leituras` | cada leitura de cada sensor | 43,7 mi linhas · 53,6 MB | 1 bi linhas · 1,5 GB |
| ouro | `agregados_minuto` | min, máx, média, leituras e nulos por sensor e minuto | (as leituras já são por minuto) | 16,7 mi linhas · 106 MB |
| ouro | `agregados_hora` | o mesmo, por hora | 729 mil linhas | 281 mil linhas · 2,3 MB |

`isoterma agregar` só gera as granularidades que reduzem os dados. Cada agregado sai do anterior
(a hora vem dos minutos), e não das leituras brutas. A média é recalculada ponderando pelo número
de leituras, porque a média das médias estaria errada.

### Escolha automática de camada

Cada consulta pede uma granularidade (por exemplo, pontos de 1 hora numa série de 30 dias), e o
motor usa a camada mais grossa que atende. Um agregado por hora só serve se a janela começar e
terminar em hora cheia. Senão, os intervalos das bordas trariam leituras de fora da janela, e o
motor desce para a camada de minuto ou para as leituras brutas. As bordas que coincidem com o
começo ou o fim da simulação não precisam de alinhamento.

## Consultas de domínio

| Método | Responde | Fonte típica |
|---|---|---|
| `resumo(inicio, fim)` | volume de dados, temperaturas por tipo de sensor, potência total e racks fora da faixa | agregados por hora |
| `mapa_termico(instante, tipo, altura)` | valor de cada rack (média dos últimos 5 min) com `x_m`, `y_m` e a faixa ASHRAE | leituras brutas |
| `fora_da_faixa(inicio, fim)` | racks que saíram de 18–27 °C, quantos minutos, pico e quando | agregados por minuto |
| `serie(alvo, inicio, fim, max_pontos)` | série de um sensor, de um rack (5 sensores) ou de um CRAC, com min, média e máx por ponto | a camada que couber |
| `esquema()` | dicionário de dados das tabelas disponíveis | manifesto |

Datas sem fuso são interpretadas no horário local do hall (`America/Sao_Paulo` nos presets).
Os resultados saem em UTC.

### Tempos sobre 1 bilhão de leituras

AMD Ryzen 5 5600 (6 núcleos), 16 GB de RAM, Windows 11, Python 3.14 e DuckDB 2.0:

| Operação | Tempo |
|---|---|
| `isoterma agregar` (minuto + hora) | 21,8 s, uma vez |
| `resumo()` do período inteiro | 0,8 s |
| `fora_da_faixa()` do período inteiro | 0,7 s |
| `serie()` de um rack no período inteiro | 0,1 s |
| `serie()` de um sensor em 1 hora (3.600 leituras brutas) | 0,06 s |
| `mapa_termico()` | 0,05 s |
| `consultar()` com o 1BRC (min, média e máx por sensor) sobre as leituras brutas | 3,4 s |

## SQL seguro

`Hall.consultar(sql)` aceita SQL escrito por uma pessoa ou, na fase 2, por uma IA. As proteções
estão em camadas:

1. **Só um SELECT.** O parser do próprio DuckDB classifica o comando, e qualquer outra coisa
   (`DROP`, `INSERT`, `COPY`, `ATTACH`, `SET`, `PRAGMA`, vários comandos juntos) é recusada com
   `ConsultaRecusada`.
2. **Conexão travada.** O `Hall` abre o DuckDB com `allowed_directories` apontando só para a
   pasta da simulação, `enable_external_access = false` e `lock_configuration = true`. Mesmo um
   SELECT não consegue ler outros arquivos do disco nem acessar a rede, e a configuração não
   pode ser reaberta.
3. **Limites.** Teto de linhas (o resultado informa se foi truncado) e de tempo. Uma consulta
   que passa do tempo é cancelada com `interrupt()` e levanta `ConsultaExpirou`.

Erros de SQL viram `ConsultaInvalida` com a mensagem do DuckDB, que a IA vai usar para corrigir
a própria consulta. As leituras são float32, e 20,8 viraria `20.799999…` em Python, então as
colunas float32 saem arredondadas para duas casas.

O gabarito (`incidentes`) continua consultável por SQL, mas nenhuma consulta de domínio o usa:
o motor enxerga o hall como enxergaria um data center real.

## Na linha de comando

```bash
uv run isoterma agregar data/demo
uv run isoterma resumo data/demo
uv run isoterma mapa data/demo --instante 2026-11-07T04:15
uv run isoterma consultar data/demo "SELECT * FROM incidentes ORDER BY inicio"
```

O mapa do roteiro da demo, 2h15 depois de o CRAC-02 falhar (no terminal, os blocos são coloridos
de azul a vermelho):

```
temp_entrada em 2026-11-07 04:15 (-03)

    1       5         10        15        20
  A ▓▓▒▒▒▒▒▒▓▓▓▓▓▓████████████▓▓▓▓▓▓▒▒▒▒▒▒▓▓
  B ▓▓▓▓▓▓▓▓▓▓▓▓▓▓████████████▓▓▓▓▓▓▓▓▓▓▒▒▓▓
  C ▓▓▓▓▓▓▓▓▓▓▓▓▓▓████████████▓▓▓▓▓▓▓▓▓▓▓▓▓▓
  D ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓██▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
  E ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
  F ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
  ...

    16 °C ░░░░░░▒▒▒▒▓▓▓▓██████ 30 °C   ·· sem leitura

10 racks acima de 27 °C, 1 abaixo de 18 °C
Mais quentes: A-11 (30,2 °C), A-10 (30,1 °C), A-12 (29,8 °C), A-09 (29,2 °C), A-08 (27,9 °C)
```

E um exemplo de por que distinguir defeito de sensor de evento real importa. Na mesma janela, a
zona do CRAC-04 tem o maior pico, mas é um sensor com picos espúrios, não calor de verdade:

```
$ uv run isoterma consultar data/demo "SELECT r.zona_crac, count(DISTINCT r.rack_id) AS racks,
    round(max(l.valor), 1) AS pico FROM leituras l JOIN sensores s USING (sensor_id)
    JOIN racks r USING (rack_id) WHERE s.tipo = 'temp_entrada'
    AND l.ts BETWEEN '2026-11-07 05:00Z' AND '2026-11-07 07:30Z' GROUP BY 1 ORDER BY pico DESC"

zona_crac  racks  pico
─────────  ─────  ────
CRAC-04       35  45,6
CRAC-02       30  30,5
CRAC-01       35  26,6
...
```
