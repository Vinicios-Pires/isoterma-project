"""Simulador de data hall: telemetria térmica realista, com incidentes injetados e gabarito."""

from isoterma.simulador.config import (
    ConfigSimulacao,
    Preset,
    TipoIncidente,
    carregar_config,
    preset,
)
from isoterma.simulador.gerador import ResultadoSimulacao, simular

__all__ = [
    "ConfigSimulacao",
    "Preset",
    "ResultadoSimulacao",
    "TipoIncidente",
    "carregar_config",
    "preset",
    "simular",
]
