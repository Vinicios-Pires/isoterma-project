# Detecção de anomalias: resultados

> Gerado por `isoterma relatorio-deteccao` a partir dos JSONs em `docs/deteccao/`. O método está em [ANOMALIAS.md](ANOMALIAS.md).

No conjunto de **teste**, os detectores acharam **346 de 346** incidentes (recall 100%), e **350 de 362** alertas correspondiam a um incidente real (precisão 96,7%).

Uma detecção conta como certa quando tem o mesmo tipo e o mesmo alvo de um incidente do gabarito, e o período dela encosta no dele (folga de 30 min). O atraso é o tempo entre o início do incidente e o primeiro alerta. Incidentes **invisíveis** são os que não afetaram nenhuma leitura (um defeito de picos que, no sorteio, não gerou pico) e ficam fora do recall.

## Calibração: usadas para escolher os limiares

| Tipo | Incidentes | Detectados | Alertas corretos | Precisão | Recall | F1 | Atraso mediano |
|---|--:|--:|--:|--:|--:|--:|--:|
| Falha de CRAC | 32 | 32 | 32 de 32 | 100% | 100% | 100% | 0 min |
| Super-refrigeração | 8 | 8 | 8 de 8 | 100% | 100% | 100% | 4 min |
| Rack sobrecarregado | 59 | 59 | 59 de 59 | 100% | 100% | 100% | 0 min |
| Recirculação | 24 | 24 | 24 de 24 | 100% | 100% | 100% | 0 min |
| Sensor congelado | 24 | 24 | 24 de 24 | 100% | 100% | 100% | 0 min |
| Sensor com deriva | 15 | 15 | 15 de 15 | 100% | 100% | 100% | 3,5 h |
| Sensor com picos | 35 (+2 invisíveis) | 35 | 41 de 41 | 100% | 100% | 100% | 36 min |
| Sensor sem leitura | 27 | 27 | 27 de 27 | 100% | 100% | 100% | 0 min |
| **Total** | 224 (+2 invisíveis) | 224 | 230 de 230 | 100% | 100% | 100% | 0 min |

| Simulação | Seed | Leituras | Período | Incidentes | Precisão | Recall | Tempo |
|---|--:|--:|--:|--:|--:|--:|--:|
| `calib-1` | 1 | 44 mi | 30 d a cada 60 s | 27 | 100% | 100% | 19 s |
| `calib-2` | 2 | 44 mi | 30 d a cada 60 s | 30 | 100% | 100% | 24 s |
| `calib-3` | 3 | 44 mi | 30 d a cada 60 s | 32 | 100% | 100% | 27 s |
| `calib-estresse-11` | 11 | 20 mi | 14 d a cada 60 s | 72 | 100% | 100% | 14 s |
| `calib-estresse-12` | 12 | 20 mi | 14 d a cada 60 s | 63 | 100% | 100% | 15 s |

**Erros:**

- **Invisível** em `calib-estresse-11`: Sensor com picos em `J-15/saida`. O defeito não chegou a afetar nenhuma leitura.
- **Invisível** em `calib-estresse-12`: Sensor com picos em `F-16/saida`. O defeito não chegou a afetar nenhuma leitura.

## Validação: usadas para achar defeitos dos detectores, depois corrigidos

| Tipo | Incidentes | Detectados | Alertas corretos | Precisão | Recall | F1 | Atraso mediano |
|---|--:|--:|--:|--:|--:|--:|--:|
| Falha de CRAC | 48 | 48 | 48 de 48 | 100% | 100% | 100% | 0 min |
| Super-refrigeração | 16 | 16 | 16 de 16 | 100% | 100% | 100% | 5 min |
| Rack sobrecarregado | 121 | 121 | 120 de 120 | 100% | 100% | 100% | 0 min |
| Recirculação | 37 | 37 | 41 de 41 | 100% | 100% | 100% | 0 min |
| Sensor congelado | 44 | 44 | 44 de 44 | 100% | 100% | 100% | 0 min |
| Sensor com deriva | 24 | 24 | 26 de 26 | 100% | 100% | 100% | 3,6 h |
| Sensor com picos | 37 (+1 invisível) | 37 | 50 de 50 | 100% | 100% | 100% | 33 min |
| Sensor sem leitura | 41 | 41 | 41 de 41 | 100% | 100% | 100% | 0 min |
| **Total** | 368 (+1 invisível) | 368 | 386 de 386 | 100% | 100% | 100% | 0 min |

| Simulação | Seed | Leituras | Período | Incidentes | Precisão | Recall | Tempo |
|---|--:|--:|--:|--:|--:|--:|--:|
| `demo` | 42 | 44 mi | 30 d a cada 60 s | 26 | 100% | 100% | 20 s |
| `aval-demo-101` | 101 | 44 mi | 30 d a cada 60 s | 37 | 100% | 100% | 24 s |
| `aval-demo-102` | 102 | 44 mi | 30 d a cada 60 s | 33 | 100% | 100% | 27 s |
| `aval-demo-103` | 103 | 44 mi | 30 d a cada 60 s | 26 | 100% | 100% | 31 s |
| `aval-demo-104` | 104 | 44 mi | 30 d a cada 60 s | 24 | 100% | 100% | 32 s |
| `aval-estresse-201` | 201 | 20 mi | 14 d a cada 60 s | 76 | 100% | 100% | 17 s |
| `aval-estresse-202` | 202 | 20 mi | 14 d a cada 60 s | 65 | 100% | 100% | 17 s |
| `aval-estresse-203` | 203 | 20 mi | 14 d a cada 60 s | 68 | 100% | 100% | 16 s |
| `bilhao` | 42 | 1,0 bi | 2,3 d a cada 1 s | 13 | 100% | 100% | 24 s |

**Erros:**

- **Invisível** em `aval-demo-104`: Sensor com picos em `J-06/saida`. O defeito não chegou a afetar nenhuma leitura.

## Teste: rodadas uma única vez, com tudo congelado

| Tipo | Incidentes | Detectados | Alertas corretos | Precisão | Recall | F1 | Atraso mediano |
|---|--:|--:|--:|--:|--:|--:|--:|
| Falha de CRAC | 40 | 40 | 40 de 40 | 100% | 100% | 100% | 0 min |
| Super-refrigeração | 20 | 20 | 21 de 21 | 100% | 100% | 100% | 4 min |
| Rack sobrecarregado | 109 | 109 | 109 de 109 | 100% | 100% | 100% | 0 min |
| Recirculação | 36 | 36 | 36 de 36 | 100% | 100% | 100% | 0 min |
| Sensor congelado | 38 | 38 | 38 de 38 | 100% | 100% | 100% | 0 min |
| Sensor com deriva | 34 | 34 | 35 de 47 | 74,5% | 100% | 85,4% | 3,9 h |
| Sensor com picos | 35 (+1 invisível) | 35 | 37 de 37 | 100% | 100% | 100% | 18 min |
| Sensor sem leitura | 34 | 34 | 34 de 34 | 100% | 100% | 100% | 0 min |
| **Total** | 346 (+1 invisível) | 346 | 350 de 362 | 96,7% | 100% | 98,3% | 0 min |

| Simulação | Seed | Leituras | Período | Incidentes | Precisão | Recall | Tempo |
|---|--:|--:|--:|--:|--:|--:|--:|
| `teste-demo-301` | 301 | 44 mi | 30 d a cada 60 s | 30 | 100% | 100% | 18 s |
| `teste-demo-302` | 302 | 44 mi | 30 d a cada 60 s | 32 | 100% | 100% | 23 s |
| `teste-demo-303` | 303 | 44 mi | 30 d a cada 60 s | 19 | 100% | 100% | 26 s |
| `teste-estresse-401` | 401 | 20 mi | 14 d a cada 60 s | 64 | 84,4% | 100% | 14 s |
| `teste-estresse-402` | 402 | 20 mi | 14 d a cada 60 s | 77 | 100% | 100% | 14 s |
| `teste-estresse-403` | 403 | 20 mi | 14 d a cada 60 s | 61 | 100% | 100% | 14 s |
| `teste-hall-alternativo-501` | 501 | 11 mi | 10 d a cada 30 s | 34 | 100% | 100% | 5 s |
| `teste-hall-alternativo-502` | 502 | 11 mi | 10 d a cada 30 s | 29 | 100% | 100% | 5 s |

**Erros:**

- **12 alertas falsos** em `teste-estresse-401`: Sensor com deriva em `D-14/saida`, a partir de 2026-11-01T12:19 UTC (Discorda até 2,3 °C do que os sensores vizinhos indicam)
- **Invisível** em `teste-estresse-402`: Sensor com picos em `I-17/entrada-meio`. O defeito não chegou a afetar nenhuma leitura.

Medido com o Isoterma 0.1.0 em 2026-11-22, Windows (AMD64 Family 25 Model 33 Stepping 2, AuthenticAMD). O tempo inclui ler os dados, rodar todos os detectores e ajustar o modelo do retorno.
