# Avaliação da IA

<!-- Gerado por `isoterma relatorio-ia`. Não edite à mão: rode a avaliação de novo. -->

As perguntas e as respostas esperadas são geradas a partir dos dados e do gabarito de incidentes, que o agente não enxerga. Cada resposta é corrigida automaticamente pela última linha `RESPOSTA:` que a avaliação pede ao agente. Detalhes em [IA.md](IA.md).

## Versão 2: 19 perguntas

Pergunta sempre pelo rack (*houve algo anormal no rack X?*): o modelo precisa descobrir sozinho se a causa é um sensor com defeito, o CRAC da zona ou o próprio rack. Tem três controles sem incidente e uma pergunta de descoberta sem pista nenhuma (*quais incidentes houve no dia X?*), corrigida pelo F1 entre os incidentes apontados e os do gabarito (mínimo de 0,7).

Simulação `demo`, executada em 21/11/2026.

| Provedor | Modelo | Acerto | Fatos | Investigação | Diagnóstico | Descoberta | Tempo médio | Ferramentas por pergunta | Custo total |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| claude | `claude-haiku-5-5` | **18/19** | 6/6 | 2/2 | 10/10 | 0/1 | 11,7 s | 4,3 | US$ 0,0604 |

<details><summary>Pergunta a pergunta</summary>

**racks** (fatos): Quantos racks há no hall?

Esperado: `200`

- ✅ claude `claude-haiku-5-5`: `200` (3,0 s, 1 ferramentas)

**zona** (fatos): Qual CRAC refrigera principalmente o rack F-01?

Esperado: `CRAC-04`

- ✅ claude `claude-haiku-5-5`: `CRAC-04` (5,2 s, 2 ferramentas)

**potencia_nominal** (fatos): Qual rack tem a maior potência nominal?

Esperado: `A-16`

- ✅ claude `claude-haiku-5-5`: `A-16` (2,3 s, 1 ferramentas)

**media_entrada** (fatos): Qual foi a temperatura média de entrada dos racks no período inteiro, em °C?

Esperado: `20.21`

- ✅ claude `claude-haiku-5-5`: `20.2` (6,9 s, 2 ferramentas)

**potencia_total** (fatos): Qual foi a potência média total do hall no período, em kW?

Esperado: `1020.0`

- ✅ claude `claude-haiku-5-5`: `1020.0` (4,8 s, 1 ferramentas)

**sensores_sem_leitura** (fatos): Quantos sensores ficaram sem leitura em algum momento do período?

Esperado: `4`

- ✅ claude `claude-haiku-5-5`: `4` (5,3 s, 3 ferramentas)

**racks_quentes** (investigação): Quais racks tiveram a entrada acima de 27 °C entre 07/11 01:00 e 07/11 06:00 (horário local) por um evento térmico real? Desconsidere defeitos de sensor.

Esperado: `['A-08', 'A-09', 'A-10', 'A-11', 'A-12', 'A-13', 'B-09', 'B-10', 'B-11', 'B-12', 'B-13', 'C-09', 'C-10', 'C-11']`

- ✅ claude `claude-haiku-5-5`: `A-08, A-09, A-10, A-11, A-12, A-13, B-09, B-10, B-11, B-12, B-13, C-09, C-10, C-11` (10,1 s, 4 ferramentas)

**primeira_vez** (investigação): Entre 07/11 01:00 e 07/11 06:00 (horário local), a que horas a entrada de algum rack passou de 27 °C pela primeira vez?

Esperado: `02:11`

- ✅ claude `claude-haiku-5-5`: `02:11` (9,3 s, 3 ferramentas)

**diagnostico_rack_sobrecarregado** (diagnóstico): Houve algo anormal no rack F-15 entre 03/11 às 13:59 e 03/11 às 19:38 (horário local)? Se houve, qual foi a causa?

Esperado: `sobrecarga`

- ✅ claude `claude-haiku-5-5`: `sobrecarga` (16,7 s, 6 ferramentas)

**diagnostico_falha_crac** (diagnóstico): Houve algo anormal no rack J-10 entre 04/11 às 02:01 e 04/11 às 04:00 (horário local)? Se houve, qual foi a causa?

Esperado: `falha_crac`

- ✅ claude `claude-haiku-5-5`: `falha_crac` (11,6 s, 4 ferramentas)

**diagnostico_sensor_picos** (diagnóstico): Houve algo anormal no rack G-07 entre 07/11 às 02:50 e 07/11 às 08:29 (horário local)? Se houve, qual foi a causa?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (20,0 s, 4 ferramentas)

**diagnostico_super_refrigeracao** (diagnóstico): Houve algo anormal no rack J-10 entre 09/11 às 18:42 e 11/11 às 19:24 (horário local)? Se houve, qual foi a causa?

Esperado: `super_refrigeracao`

- ✅ claude `claude-haiku-5-5`: `super_refrigeracao` (12,7 s, 4 ferramentas)

**diagnostico_sensor_congelado** (diagnóstico): Houve algo anormal no rack F-13 entre 12/11 às 17:31 e 14/11 às 08:23 (horário local)? Se houve, qual foi a causa?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (16,2 s, 5 ferramentas)

**diagnostico_sensor_sem_leitura** (diagnóstico): Houve algo anormal no rack J-14 entre 18/11 às 19:42 e 18/11 às 21:26 (horário local)? Se houve, qual foi a causa?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (20,8 s, 10 ferramentas)

**diagnostico_sensor_deriva** (diagnóstico): Houve algo anormal no rack E-15 entre 27/11 às 13:22 e 30/11 às 11:14 (horário local)? Se houve, qual foi a causa?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (13,3 s, 5 ferramentas)

**controle_A-01** (diagnóstico): Houve algo anormal no rack A-01 entre 02/11 às 00:00 e 02/11 às 03:00 (horário local)? Se houve, qual foi a causa?

Esperado: `normal`

- ✅ claude `claude-haiku-5-5`: `normal` (9,0 s, 5 ferramentas)

**controle_A-08** (diagnóstico): Houve algo anormal no rack A-08 entre 04/11 às 08:00 e 04/11 às 11:00 (horário local)? Se houve, qual foi a causa?

Esperado: `normal`

- ✅ claude `claude-haiku-5-5`: `normal` (10,9 s, 5 ferramentas)

**controle_A-15** (diagnóstico): Houve algo anormal no rack A-15 entre 06/11 às 15:00 e 06/11 às 18:00 (horário local)? Se houve, qual foi a causa?

Esperado: `normal`

- ✅ claude `claude-haiku-5-5`: `normal` (5,4 s, 2 ferramentas)

**descoberta** (descoberta): Quais incidentes aconteceram no hall no dia 12/11 (horário local)? Considere falhas e super-refrigeração de CRAC, sobrecargas de rack, recirculação de ar quente e defeitos de sensor.

Esperado: `[{'categoria': 'super_refrigeracao', 'alvos': ['CRAC-04']}, {'categoria': 'defeito_sensor', 'alvos': ['F-13/saida', 'F-13']}]`

- ❌ claude `claude-haiku-5-5`: `super_refrigeracao:CRAC-04 (F1 0.67)` (38,3 s, 15 ferramentas)

</details>

Tokens no total: 166 de entrada, 475.033 lidos do cache e 40.948 de saída.

## Versão 1: 17 perguntas

Primeira versão, mantida como registro. Perguntava pelo alvo do incidente (*o que aconteceu com o sensor X?*), o que já entregava metade do diagnóstico, e o modelo mais barato acertou tudo. Por isso foi substituída pela v2.

Simulação `demo`, executada em 21/11/2026.

| Provedor | Modelo | Acerto | Fatos | Investigação | Diagnóstico | Tempo médio | Ferramentas por pergunta | Custo total |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| claude | `claude-haiku-5-5` | **17/17** | 6/6 | 2/2 | 9/9 | 9,6 s | 3,4 | US$ 0,0448 |

<details><summary>Pergunta a pergunta</summary>

**racks** (fatos): Quantos racks há no hall?

Esperado: `200`

- ✅ claude `claude-haiku-5-5`: `200` (2,3 s, 1 ferramentas)

**zona** (fatos): Qual CRAC refrigera principalmente o rack F-01?

Esperado: `CRAC-04`

- ✅ claude `claude-haiku-5-5`: `CRAC-04` (13,5 s, 6 ferramentas)

**potencia_nominal** (fatos): Qual rack tem a maior potência nominal?

Esperado: `A-16`

- ✅ claude `claude-haiku-5-5`: `A-16` (2,9 s, 2 ferramentas)

**media_entrada** (fatos): Qual foi a temperatura média de entrada dos racks no período inteiro, em °C?

Esperado: `20.21`

- ✅ claude `claude-haiku-5-5`: `20.2` (8,4 s, 3 ferramentas)

**potencia_total** (fatos): Qual foi a potência média total do hall no período, em kW?

Esperado: `1020.0`

- ✅ claude `claude-haiku-5-5`: `1020` (4,1 s, 1 ferramentas)

**sensores_sem_leitura** (fatos): Quantos sensores ficaram sem leitura em algum momento do período?

Esperado: `4`

- ✅ claude `claude-haiku-5-5`: `4` (5,2 s, 2 ferramentas)

**racks_quentes** (investigação): Quais racks tiveram a entrada acima de 27 °C entre 07/11 01:00 e 07/11 06:00 (horário local) por um evento térmico real? Desconsidere defeitos de sensor.

Esperado: `['A-08', 'A-09', 'A-10', 'A-11', 'A-12', 'A-13', 'B-09', 'B-10', 'B-11', 'B-12', 'B-13', 'C-09', 'C-10', 'C-11']`

- ✅ claude `claude-haiku-5-5`: `A-08, A-09, A-10, A-11, A-12, A-13, B-09, B-10, B-11, B-12, B-13, C-09, C-10, C-11` (11,8 s, 4 ferramentas)

**primeira_vez** (investigação): Entre 07/11 01:00 e 07/11 06:00 (horário local), a que horas a entrada de algum rack passou de 27 °C pela primeira vez?

Esperado: `02:11`

- ✅ claude `claude-haiku-5-5`: `02:11` (8,7 s, 3 ferramentas)

**diagnostico_rack_sobrecarregado** (diagnóstico): O que aconteceu com o rack F-15 entre 03/11 às 13:59 e 03/11 às 19:38 (horário local)?

Esperado: `sobrecarga`

- ✅ claude `claude-haiku-5-5`: `sobrecarga` (15,6 s, 6 ferramentas)

**diagnostico_falha_crac** (diagnóstico): O que aconteceu com o CRAC-05 entre 04/11 às 02:01 e 04/11 às 04:00 (horário local)?

Esperado: `falha_crac`

- ✅ claude `claude-haiku-5-5`: `falha_crac` (9,5 s, 3 ferramentas)

**diagnostico_sensor_picos** (diagnóstico): O que aconteceu com o sensor G-07/entrada-topo entre 07/11 às 02:50 e 07/11 às 08:29 (horário local)?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (10,6 s, 2 ferramentas)

**diagnostico_super_refrigeracao** (diagnóstico): O que aconteceu com o CRAC-05 entre 09/11 às 18:42 e 11/11 às 19:24 (horário local)?

Esperado: `super_refrigeracao`

- ✅ claude `claude-haiku-5-5`: `super_refrigeracao` (13,8 s, 5 ferramentas)

**diagnostico_sensor_congelado** (diagnóstico): O que aconteceu com o sensor F-13/saida entre 12/11 às 17:31 e 14/11 às 08:23 (horário local)?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (13,3 s, 4 ferramentas)

**diagnostico_sensor_sem_leitura** (diagnóstico): O que aconteceu com o sensor J-14/entrada-topo entre 18/11 às 19:42 e 18/11 às 21:26 (horário local)?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (13,7 s, 6 ferramentas)

**diagnostico_sensor_deriva** (diagnóstico): O que aconteceu com o sensor E-15/entrada-base entre 27/11 às 13:22 e 30/11 às 11:14 (horário local)?

Esperado: `defeito_sensor`

- ✅ claude `claude-haiku-5-5`: `defeito_sensor` (14,7 s, 5 ferramentas)

**controle_A-01** (diagnóstico): O que aconteceu com o rack A-01 entre 02/11 às 13:00 e 02/11 às 16:00 (horário local)?

Esperado: `normal`

- ✅ claude `claude-haiku-5-5`: `normal` (6,0 s, 3 ferramentas)

**controle_A-08** (diagnóstico): O que aconteceu com o rack A-08 entre 05/11 às 21:00 e 06/11 às 00:00 (horário local)?

Esperado: `normal`

- ✅ claude `claude-haiku-5-5`: `normal` (9,0 s, 2 ferramentas)

</details>

Tokens no total: 140 de entrada, 292.881 lidos do cache e 30.475 de saída.
