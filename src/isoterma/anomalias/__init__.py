"""Detecção de anomalias explicável e a medição dela contra o gabarito."""

from isoterma.anomalias.avaliacao import Avaliacao, avaliar, ler_gabarito
from isoterma.anomalias.detectores import Deteccao, Limiares, Resultado, detectar

__all__ = [
    "Avaliacao",
    "Deteccao",
    "Limiares",
    "Resultado",
    "avaliar",
    "detectar",
    "ler_gabarito",
]
