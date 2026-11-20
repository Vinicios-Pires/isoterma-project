"""Motor de consultas: camadas de dados, consultas de domínio e SQL seguro."""

from isoterma.motor.camadas import agregar
from isoterma.motor.hall import Hall
from isoterma.motor.sql_seguro import (
    ConsultaExpirou,
    ConsultaInvalida,
    ConsultaRecusada,
    ResultadoConsulta,
)

__all__ = [
    "ConsultaExpirou",
    "ConsultaInvalida",
    "ConsultaRecusada",
    "Hall",
    "ResultadoConsulta",
    "agregar",
]
