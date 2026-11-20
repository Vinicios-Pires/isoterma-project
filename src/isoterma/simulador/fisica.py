"""Física lenta do hall ("drivers"), calculada em resolução de 1 minuto.

O modelo é propositalmente simples, para ser rápido e explicável (não é CFD):

- carga de TI = nominal × ciclo diário e semanal × ruído correlacionado no tempo;
- insuflamento de cada CRAC = setpoint, com inércia térmica de primeira ordem. Quando o CRAC
  falha, o insuflamento caminha em direção à temperatura do ar de retorno;
- entrada do rack = média do insuflamento ponderada pela distância a cada CRAC + recirculação de
  ar quente (maior no topo e nas pontas das fileiras);
- saída do rack = entrada + ΔT proporcional à carga;
- retorno do CRAC = média das saídas dos racks que ele atende.

As leituras finais saem daqui por interpolação, com ruído de sensor somado no gerador.
"""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from isoterma.simulador.config import SEGUNDOS_POR_DIA, ConfigSimulacao, TipoIncidente
from isoterma.simulador.incidentes import Incidente
from isoterma.simulador.layout import TIPOS_TEMPERATURA, Layout

PASSO_DRIVER_S = 60
CORRELACAO_CARGA = 0.98  # ruído de carga AR(1), minuto a minuto
RUIDO_CARGA = 0.01
FATOR_RECIRCULACAO_ALTURA = np.array([0.15, 0.5, 1.0])  # base, meio, topo
DESVIO_CALIBRACAO_C = 0.15  # erro fixo de cada sensor de temperatura


def fator_carga(inicio: datetime, fuso: str, tempos_s: np.ndarray) -> np.ndarray:
    """Ciclo diário (pico às 15h no horário local) com queda nos fins de semana."""
    deslocamento = inicio.astimezone(ZoneInfo(fuso)).utcoffset()
    local_s = inicio.timestamp() + (deslocamento.total_seconds() if deslocamento else 0) + tempos_s
    hora = (local_s % SEGUNDOS_POR_DIA) / 3600
    # 01/01/1970 foi uma quinta-feira: com segunda = 0, ela é o dia 3.
    dia_semana = ((local_s // SEGUNDOS_POR_DIA).astype(np.int64) + 3) % 7
    return 0.75 + 0.15 * np.cos(2 * np.pi * (hora - 15) / 24) - 0.08 * (dia_semana >= 5)


def calcular_drivers(
    config: ConfigSimulacao,
    layout: Layout,
    incidentes: list[Incidente],
    rng: np.random.Generator,
) -> np.ndarray:
    """Valor sem ruído de cada sensor a cada minuto: matriz (minutos + 1, sensores) float32."""
    termica = config.termica
    minutos = math.ceil(config.periodo.duracao_s / PASSO_DRIVER_S) + 1
    n_racks, n_cracs = layout.total_racks, layout.total_cracs
    tempos = np.arange(minutos, dtype=np.float64) * PASSO_DRIVER_S
    carga_dia = fator_carga(config.periodo.inicio, config.periodo.fuso, tempos)

    falha = np.zeros((minutos, n_cracs))
    delta_setpoint = np.zeros((minutos, n_cracs))
    multiplicador_carga = np.ones((minutos, n_racks))
    recirculacao_extra = np.zeros((minutos, n_racks))
    for inc in incidentes:
        janela = slice(inc.inicio_s // PASSO_DRIVER_S, math.ceil(inc.fim_s / PASSO_DRIVER_S))
        match inc.tipo:
            case TipoIncidente.FALHA_CRAC:
                z = layout.crac_ids.index(inc.alvo)
                falha[janela, z] = np.maximum(falha[janela, z], inc.intensidade)
            case TipoIncidente.SUPER_REFRIGERACAO:
                delta_setpoint[janela, layout.crac_ids.index(inc.alvo)] -= inc.intensidade
            case TipoIncidente.RACK_SOBRECARREGADO:
                multiplicador_carga[janela, layout.rack_ids.index(inc.alvo)] *= 1 + inc.intensidade
            case TipoIncidente.RECIRCULACAO:
                recirculacao_extra[janela, layout.rack_ids.index(inc.alvo)] += inc.intensidade
            case _:
                pass  # defeitos de sensor não mudam a física; entram direto nas leituras

    entrada = np.empty((minutos, n_racks, 3))
    saida = np.empty((minutos, n_racks))
    potencia = np.empty((minutos, n_racks))
    insuflamento_hist = np.empty((minutos, n_cracs))
    retorno_hist = np.empty((minutos, n_cracs))

    alfa = 1 - math.exp(-PASSO_DRIVER_S / 60 / termica.constante_tempo_min)
    ruido = rng.standard_normal((minutos, n_racks)) * RUIDO_CARGA
    nominal = layout.potencia_nominal_kw
    pesos = layout.pesos
    insuflamento = np.full(n_cracs, termica.setpoint_c)
    retorno = insuflamento + termica.delta_t_nominal_c
    desvio_carga = np.zeros(n_racks)

    for m in range(minutos):
        desvio_carga = CORRELACAO_CARGA * desvio_carga + ruido[m]
        potencia_m = nominal * carga_dia[m] * (1 + desvio_carga) * multiplicador_carga[m]

        setpoint = termica.setpoint_c + delta_setpoint[m]
        alvo = setpoint + falha[m] * (retorno - setpoint)
        insuflamento = insuflamento + alfa * (alvo - insuflamento)

        if falha[m].any():
            # Os CRACs vizinhos cobrem parte da área de quem falhou.
            pesos_m = pesos * (1 - termica.compensacao_vizinhos * (falha[m] > 0))
            pesos_m /= pesos_m.sum(axis=1, keepdims=True)
        else:
            pesos_m = pesos

        entrada_m = (
            (pesos_m @ insuflamento)[:, None]
            + layout.recirculacao_base_c
            + recirculacao_extra[m][:, None] * FATOR_RECIRCULACAO_ALTURA
        )
        saida_m = entrada_m.mean(axis=1) + termica.delta_t_nominal_c * potencia_m / nominal
        retorno = layout.pesos_retorno @ saida_m

        entrada[m] = entrada_m
        saida[m] = saida_m
        potencia[m] = potencia_m
        insuflamento_hist[m] = insuflamento
        retorno_hist[m] = retorno

    # A ordem das colunas segue a ordem dos sensores em layout.SENSORES_RACK e SENSORES_CRAC.
    por_rack = np.concatenate([entrada, saida[..., None], potencia[..., None]], axis=2)
    por_crac = np.stack([insuflamento_hist, retorno_hist], axis=2)
    valores = np.concatenate([por_rack.reshape(minutos, -1), por_crac.reshape(minutos, -1)], axis=1)

    temperatura = np.array([t in TIPOS_TEMPERATURA for t in layout.sensor_tipos])
    valores += rng.normal(0, DESVIO_CALIBRACAO_C, layout.total_sensores) * temperatura
    return valores.astype(np.float32)
