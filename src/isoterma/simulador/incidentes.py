"""Catálogo de incidentes, sorteio e o gabarito usado para medir a detecção."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pyarrow as pa

from isoterma.simulador.config import SEGUNDOS_POR_DIA, ConfigSimulacao, TipoIncidente
from isoterma.simulador.layout import TIPOS_TEMPERATURA, Layout

T = TipoIncidente

ALVO_POR_TIPO: dict[TipoIncidente, str] = {
    T.FALHA_CRAC: "crac",
    T.SUPER_REFRIGERACAO: "crac",
    T.RACK_SOBRECARREGADO: "rack",
    T.RECIRCULACAO: "rack",
    T.SENSOR_CONGELADO: "sensor",
    T.SENSOR_DERIVA: "sensor",
    T.SENSOR_PICOS: "sensor",
    T.SENSOR_SEM_LEITURA: "sensor",
}

# Faixas sorteadas quando o incidente não define duração ou intensidade.
DURACAO_MIN: dict[TipoIncidente, tuple[float, float]] = {
    T.FALHA_CRAC: (30, 180),
    T.RACK_SOBRECARREGADO: (60, 360),
    T.RECIRCULACAO: (6 * 60, 72 * 60),
    T.SUPER_REFRIGERACAO: (12 * 60, 72 * 60),
    T.SENSOR_CONGELADO: (2 * 60, 48 * 60),
    T.SENSOR_DERIVA: (12 * 60, 96 * 60),
    T.SENSOR_PICOS: (60, 12 * 60),
    T.SENSOR_SEM_LEITURA: (10, 6 * 60),
}

# Significado da intensidade em cada tipo:
#   falha_crac: fração da refrigeração perdida · rack_sobrecarregado: carga extra (0,5 = +50%)
#   recirculacao: °C a mais no topo · super_refrigeracao: °C abaixo do setpoint
#   sensor_deriva: °C por hora · sensor_picos e sensor_sem_leitura: fração das leituras afetadas
INTENSIDADE: dict[TipoIncidente, tuple[float, float]] = {
    T.FALHA_CRAC: (0.7, 1.0),
    T.RACK_SOBRECARREGADO: (0.5, 1.0),
    T.RECIRCULACAO: (3.0, 6.0),
    T.SUPER_REFRIGERACAO: (3.0, 5.0),
    T.SENSOR_CONGELADO: (1.0, 1.0),
    T.SENSOR_DERIVA: (0.1, 0.5),
    T.SENSOR_PICOS: (0.01, 0.05),
    T.SENSOR_SEM_LEITURA: (0.5, 1.0),
}


@dataclass(frozen=True)
class Incidente:
    tipo: TipoIncidente
    alvo: str
    inicio_s: int  # segundos desde o início do período
    fim_s: int
    intensidade: float

    @property
    def alvo_tipo(self) -> str:
        return ALVO_POR_TIPO[self.tipo]

    def descricao(self) -> str:
        i = self.intensidade
        graus = f"{i:.1f}".replace(".", ",")
        match self.tipo:
            case T.FALHA_CRAC:
                return f"{self.alvo} perdeu {i:.0%} da refrigeração; a zona aquece"
            case T.SUPER_REFRIGERACAO:
                return f"Setpoint de {self.alvo} {graus} °C abaixo do normal; zona fria demais"
            case T.RACK_SOBRECARREGADO:
                return f"Carga do rack {self.alvo} subiu {i:.0%}; a saída esquenta"
            case T.RECIRCULACAO:
                return f"Ar quente recirculando no rack {self.alvo}: topo até {graus} °C acima"
            case T.SENSOR_CONGELADO:
                return f"Sensor {self.alvo} travou e repete o mesmo valor"
            case T.SENSOR_DERIVA:
                taxa = f"{i:.2f}".replace(".", ",")
                return f"Sensor {self.alvo} perdeu a calibração: deriva de {taxa} °C por hora"
            case T.SENSOR_PICOS:
                return f"Sensor {self.alvo} com picos espúrios em {i:.0%} das leituras"
            case T.SENSOR_SEM_LEITURA:
                return f"Sensor {self.alvo} sem leitura em {i:.0%} do período"


def _alvos(tipo: TipoIncidente, layout: Layout) -> list[str]:
    match ALVO_POR_TIPO[tipo]:
        case "crac":
            return layout.crac_ids
        case "rack":
            return layout.rack_ids
        case _:
            return [
                codigo
                for codigo, tipo_sensor in zip(
                    layout.sensor_codigos, layout.sensor_tipos, strict=True
                )
                if tipo_sensor in TIPOS_TEMPERATURA
            ]


def sortear_incidentes(
    config: ConfigSimulacao, layout: Layout, rng: np.random.Generator
) -> list[Incidente]:
    """Combina os incidentes programados com os sorteados pelas taxas diárias."""
    duracao_total = config.periodo.duracao_s
    incidentes: list[Incidente] = []

    def criar(
        tipo: TipoIncidente,
        inicio_s: float,
        duracao_s: float,
        alvo: str | None,
        intensidade: float | None,
    ) -> None:
        alvos = _alvos(tipo, layout)
        if alvo is None:
            alvo = alvos[rng.integers(len(alvos))]
        elif alvo not in alvos:
            raise ValueError(f"Alvo {alvo!r} não existe ou não serve para {tipo.value}")
        if intensidade is None:
            intensidade = float(rng.uniform(*INTENSIDADE[tipo]))
        inicio = int(min(inicio_s, duracao_total - 1))
        fim = int(min(inicio + max(duracao_s, 1), duracao_total))
        incidentes.append(Incidente(tipo, alvo, inicio, fim, intensidade))

    for programado in config.incidentes.programados:
        criar(
            programado.tipo,
            programado.inicio_h * 3600,
            programado.duracao_min * 60,
            programado.alvo,
            programado.intensidade,
        )

    dias = duracao_total / SEGUNDOS_POR_DIA
    for tipo, taxa in config.incidentes.taxas_por_dia.items():
        for _ in range(rng.poisson(taxa * dias)):
            duracao = rng.uniform(*DURACAO_MIN[tipo]) * 60
            inicio = rng.uniform(0, max(duracao_total - duracao, 1))
            criar(tipo, inicio, duracao, None, None)

    return sorted(incidentes, key=lambda inc: (inc.inicio_s, inc.tipo.value, inc.alvo))


def tabela_incidentes(incidentes: list[Incidente], inicio: datetime) -> pa.Table:
    """O gabarito: o que foi injetado, onde e quando."""
    tipo_ts = pa.timestamp("ms", tz="UTC")
    return pa.table(
        {
            "incidente_id": pa.array(range(1, len(incidentes) + 1), pa.int32()),
            "tipo": [inc.tipo.value for inc in incidentes],
            "alvo_tipo": [inc.alvo_tipo for inc in incidentes],
            "alvo": [inc.alvo for inc in incidentes],
            "inicio": pa.array(
                [inicio + timedelta(seconds=inc.inicio_s) for inc in incidentes], tipo_ts
            ),
            "fim": pa.array([inicio + timedelta(seconds=inc.fim_s) for inc in incidentes], tipo_ts),
            "intensidade": [round(inc.intensidade, 3) for inc in incidentes],
            "descricao": [inc.descricao() for inc in incidentes],
        }
    )
