# Detecção de anomalias

O Isoterma procura 8 tipos de anomalia com **regras explicáveis**, escritas em SQL e rodadas no
DuckDB. Cada alerta diz o que viu ("insuflamento até 13,8 °C acima do normal, com a entrada dos
racks da zona subindo junto"), e a qualidade dos detectores é medida contra o gabarito dos
incidentes injetados pelo simulador.

Os números estão em [DETECCAO.md](DETECCAO.md). Em resumo, no conjunto de teste, que tem 8
simulações e 346 incidentes, e foi rodado uma única vez com tudo congelado:

- **recall de 100%:** todos os incidentes foram detectados;
- **precisão de 96,7%:** 350 de 362 alertas correspondiam a um incidente real;
- **tempo:** de 5 a 26 s por simulação de até 44 milhões de leituras. A de 1 bilhão de leituras
  leva 18 s, porque parte dos agregados por minuto.

```bash
uv run isoterma detectar data/demo
```

## A ideia: evento físico ou defeito de sensor?

A pergunta que importa num data center não é só "algo está estranho?", mas "**o rack está quente
ou o sensor está com defeito?**". As duas coisas pedem respostas diferentes: uma chama a
operação, a outra a manutenção dos sensores.

A diferença aparece na coerência entre sensores:

- **Um evento físico mexe em vários sensores de forma coerente.** Quando um CRAC falha, o
  insuflamento esquenta *e* a entrada dos racks da zona sobe junto. Na recirculação, o ar
  quente volta por cima do rack e aquece as três alturas na proporção que a física impõe: pouco
  na base, muito no topo.
- **Um defeito de sensor mexe só nele.** O valor passa a discordar dos vizinhos, que continuam
  coerentes entre si.

Por isso, cada detector compara o sensor com uma **referência física**, e não só com o próprio
histórico:

| Sensor | Referência |
|---|---|
| Entrada (base, meio, topo) | as outras duas alturas do mesmo rack: o ar do CRAC é o mesmo para as três |
| Saída | a entrada do rack mais um aquecimento proporcional à carga (reta ajustada por rack) |
| Retorno do CRAC | a média das saídas dos racks, pesada pela distância até o CRAC |
| Insuflamento | o setpoint do CRAC no cadastro, confirmado pela entrada dos racks da zona |
| Potência | a carga do hall no mesmo minuto (todos seguem o mesmo ciclo diário) |

## Os detectores

Tudo roda na resolução de **minuto**: as leituras brutas quando já são por minuto, os agregados
por minuto quando existem, ou as leituras agrupadas na hora. Antes de comparar sensores, uma
média móvel de 15 minutos tira o ruído, e os minutos já explicados por um defeito (picos,
sensor congelado) ficam de fora.

| Tipo | Regra | Duração mínima |
|---|---|---|
| Falha de CRAC | insuflamento ≥ 2 °C acima do setpoint **e** entrada da zona ≥ 0,8 °C acima do resto do hall | 10 min |
| Super-refrigeração | insuflamento ≥ 2 °C abaixo do setpoint **e** zona mais fria que o resto do hall | 60 min |
| Rack sobrecarregado | carga (potência ÷ nominal) ≥ 1,3 vez a carga mediana do hall no mesmo minuto | 15 min |
| Recirculação | topo − base sobe ≥ 1,5 °C, com o meio subindo de 20% a 65% disso (a assinatura do ar quente voltando por cima) | 30 min |
| Sensor congelado | o mesmo valor exato por 30 minutos (com ruído de 0,12 °C e uma casa decimal, isso não acontece por acaso) | 30 min |
| Sensor com picos | leitura a ≥ 5 °C dos dois minutos vizinhos ao mesmo tempo (uma subida real, até ~2 °C/min, não faz isso) | — |
| Sensor sem leitura | ≥ 30% de leituras nulas numa janela de 15 min | 10 min |
| Sensor com deriva | discorda ≥ 1 °C da referência em ≥ 60% do evento, sem a assinatura de um evento físico | 60 min |

Duas regras resolvem as sobreposições:

- **A causa física tem preferência.** Se o próprio CRAC tem uma falha ou super-refrigeração
  detectada, um desvio no insuflamento ou no retorno dele não vira "defeito de sensor".
- **Sensor acusado não serve de referência.** Uma saída de rack com defeito detectado sai da
  média que serve de referência para o retorno do CRAC.

O único parâmetro ajustado pelos próprios dados, sem olhar o gabarito, é o **alcance do ar de
retorno**: quanto o peso de cada rack cai com a distância até o CRAC. O detector testa alguns
valores e fica com o que melhor explica o retorno nos primeiros 3 dias. Em todas as simulações,
ele escolheu 1,5 m.

## Como a medição foi feita

O risco de medir detectores com o próprio gabarito é ajustá-los até acertarem *aquelas*
simulações. Para evitar isso, as simulações foram divididas em três conjuntos, como num projeto
de aprendizado de máquina:

| Conjunto | Simulações | Para quê |
|---|---|---|
| Calibração | demo com seeds 1–3, estresse com 11–12 | desenhar os detectores e escolher os limiares |
| Validação | demo (seed 42) e 101–104, estresse 201–203, a de 1 bilhão | achar defeitos dos detectores |
| Teste | demo 301–303, estresse 401–403, hall alternativo 501–502 | o placar final, rodado **uma vez** |

- O cenário de **estresse** ([cenarios/estresse.toml](../cenarios/estresse.toml)) tem cerca de
  5 vezes mais incidentes que a demo, e eles se sobrepõem com frequência.
- O **hall alternativo** ([cenarios/hall-alternativo.toml](../cenarios/hall-alternativo.toml))
  tem outra geometria, outro setpoint e leituras a cada 30 s. Nenhuma simulação dele foi vista
  antes do teste.

Para reproduzir (a geração leva cerca de 1 minuto e a avaliação, uns 2):

```bash
for s in 301 302 303; do uv run isoterma simular -p demo --seed $s -o data/teste-demo-$s; done
for s in 401 402 403; do uv run isoterma simular -c cenarios/estresse.toml --seed $s -o data/teste-estresse-$s; done
for s in 501 502; do uv run isoterma simular -c cenarios/hall-alternativo.toml --seed $s -o data/teste-hall-alternativo-$s; done
uv run isoterma avaliar-deteccao data/teste-* --grupo teste
uv run isoterma relatorio-deteccao docs/deteccao/*.json
```

### O que a validação encontrou

A validação achou quatro defeitos, todos corrigidos antes do teste:

1. **Uma deriva longa entortava a reta da saída.** A relação "saída = entrada + k × carga" era
   ajustada com todos os minutos, inclusive os de um sensor com deriva por dias. A reta torta
   acusava desvios diários fora do incidente. Correção: um ajuste que descarta os pontos muito
   fora da reta e ajusta de novo.
2. **Um sensor de saída com defeito contaminava a referência do retorno.** Correção: saídas já
   acusadas ficam fora da referência.
3. **Incidentes que ocupam a maior parte do período viravam o "normal".** Na simulação de
   1 bilhão de leituras, com só 55 horas, uma super-refrigeração durava o período inteiro, e a
   referência era a mediana do próprio período. Correção: comparar com o setpoint do cadastro e
   com o resto do hall no mesmo minuto, e não com o histórico do próprio sensor.
4. **Dois eventos ao mesmo tempo confundiam a zona.** Um CRAC super-refrigerando enquanto o
   vizinho falhava fazia o insuflamento frio parecer defeito de sensor. Correção: a regra da
   causa física.

## Limitações

- **O hall é simulado.** A física do simulador é idealizada: as três alturas de um rack recebem
  exatamente o mesmo ar, e a saída é exatamente a entrada mais um termo linear da carga. Num
  data center real, as referências físicas valem, mas os limiares precisariam de nova calibração
  e a precisão seria menor. O número que mais importa aqui é o método, não os 100%.
- **A deriva lenta demora a aparecer.** Uma deriva de 0,1 °C/h leva 10 horas para chegar a 1 °C.
  O atraso mediano da deriva é de cerca de 4 horas, contra minutos nos outros tipos.
- **O erro que sobrou no teste:** os 12 alertas falsos vêm todos de uma saída de rack cuja
  deriva real durou 4 dias, a 0,5 °C/h, num período de 14. É o defeito 1 da validação numa
  forma mais forte: com 29% dos minutos contaminados, as duas rodadas de descarte não
  endireitam a reta. Partir de uma estimativa inicial robusta (Theil–Sen ou mediana das
  inclinações) deve resolver. Como o teste já foi usado, a correção vai precisar de um conjunto
  de teste novo.
- **Detectores ajustam os limiares, não aprendem.** Tipos de anomalia que não estão no catálogo
  (por exemplo, um vazamento de ar entre corredores) não são vistos.
