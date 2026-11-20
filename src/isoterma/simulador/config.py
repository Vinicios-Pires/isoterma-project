"""Configuração do simulador: modelos validados e presets de escala."""

import math
import re
import tomllib
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SENSORES_POR_RACK = 5
SENSORES_POR_CRAC = 2
SEGUNDOS_POR_DIA = 86_400


class TipoIncidente(StrEnum):
    FALHA_CRAC = "falha_crac"
    RACK_SOBRECARREGADO = "rack_sobrecarregado"
    RECIRCULACAO = "recirculacao"
    SUPER_REFRIGERACAO = "super_refrigeracao"
    SENSOR_CONGELADO = "sensor_congelado"
    SENSOR_DERIVA = "sensor_deriva"
    SENSOR_PICOS = "sensor_picos"
    SENSOR_SEM_LEITURA = "sensor_sem_leitura"


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Hall(_Modelo):
    """Planta do data hall: fileiras de racks entre corredores frios e quentes."""

    fileiras: int = Field(default=4, ge=1, le=26)
    racks_por_fileira: int = Field(default=10, ge=1, le=99)
    cracs: int = Field(default=4, ge=1, le=99)
    passo_rack_m: float = Field(default=0.6, gt=0)
    passo_fileira_m: float = Field(default=2.4, gt=0)

    @property
    def total_racks(self) -> int:
        return self.fileiras * self.racks_por_fileira


class Periodo(_Modelo):
    """Janela simulada. Os timestamps são sempre gravados em UTC."""

    inicio: datetime = datetime(2026, 11, 1, tzinfo=UTC)
    dias: float = Field(default=1.0, gt=0)
    intervalo_s: int = Field(default=60, ge=1, le=3600)
    fuso: str = "America/Sao_Paulo"

    @field_validator("inicio")
    @classmethod
    def _inicio_em_utc(cls, valor: datetime) -> datetime:
        if valor.tzinfo is None:
            return valor.replace(tzinfo=UTC)
        return valor.astimezone(UTC)

    @model_validator(mode="after")
    def _intervalo_divide_o_dia(self) -> Self:
        if SEGUNDOS_POR_DIA % self.intervalo_s:
            raise ValueError("intervalo_s precisa dividir 86400 (ex.: 1, 10, 30, 60, 300)")
        return self

    @property
    def passos(self) -> int:
        return max(1, round(self.dias * SEGUNDOS_POR_DIA / self.intervalo_s))

    @property
    def duracao_s(self) -> int:
        return self.passos * self.intervalo_s


class Termica(_Modelo):
    """Parâmetros do modelo térmico simplificado (não é CFD)."""

    setpoint_c: float = Field(default=19.5, description="Insuflamento dos CRACs")
    potencia_padrao_kw: tuple[float, float] = (4.0, 8.0)
    potencia_densa_kw: tuple[float, float] = (12.0, 16.0)
    fracao_racks_densos: float = Field(default=0.1, ge=0, le=1)
    delta_t_nominal_c: float = Field(default=15.0, gt=0, description="Saída − entrada a 100%")
    constante_tempo_min: float = Field(default=6.0, gt=0, description="Inércia do insuflamento")
    alcance_crac_m: float = Field(default=1.5, gt=0, description="Decaimento da influência")
    compensacao_vizinhos: float = Field(
        default=0.15, ge=0, le=1, description="Quanto os outros CRACs cobrem um que falhou"
    )
    ruido_temperatura_c: float = Field(default=0.12, ge=0)
    ruido_potencia: float = Field(default=0.005, ge=0, description="Fração da nominal")


class IncidenteProgramado(_Modelo):
    """Incidente com hora marcada, útil para roteiros de demonstração."""

    tipo: TipoIncidente
    inicio_h: float = Field(ge=0, description="Horas após o início do período")
    duracao_min: float = Field(gt=0)
    alvo: str | None = Field(default=None, description="CRAC, rack ou código do sensor")
    intensidade: float | None = None


class ConfigIncidentes(_Modelo):
    taxas_por_dia: dict[TipoIncidente, float] = Field(default_factory=dict)
    programados: list[IncidenteProgramado] = Field(default_factory=list)

    @field_validator("taxas_por_dia")
    @classmethod
    def _taxas_nao_negativas(cls, taxas: dict[TipoIncidente, float]) -> dict[TipoIncidente, float]:
        if any(taxa < 0 for taxa in taxas.values()):
            raise ValueError("taxas_por_dia não podem ser negativas")
        return taxas


class ConfigSimulacao(_Modelo):
    nome: str = Field(default="hall", pattern=r"^[a-z0-9][a-z0-9_-]*$")
    seed: int = Field(default=42, ge=0)
    hall: Hall = Field(default_factory=Hall)
    periodo: Periodo = Field(default_factory=Periodo)
    termica: Termica = Field(default_factory=Termica)
    incidentes: ConfigIncidentes = Field(default_factory=ConfigIncidentes)
    linhas_por_bloco: int = Field(default=8_000_000, ge=1_000)

    @property
    def total_sensores(self) -> int:
        return self.hall.total_racks * SENSORES_POR_RACK + self.hall.cracs * SENSORES_POR_CRAC

    @property
    def total_linhas(self) -> int:
        return self.periodo.passos * self.total_sensores


# Incidentes por dia num hall de 200 racks (o preset demo). Halls maiores usam taxas_para().
TAXAS_PADRAO: dict[TipoIncidente, float] = {
    TipoIncidente.FALHA_CRAC: 0.1,
    TipoIncidente.RACK_SOBRECARREGADO: 0.3,
    TipoIncidente.RECIRCULACAO: 0.1,
    TipoIncidente.SUPER_REFRIGERACAO: 0.05,
    TipoIncidente.SENSOR_CONGELADO: 0.1,
    TipoIncidente.SENSOR_DERIVA: 0.05,
    TipoIncidente.SENSOR_PICOS: 0.1,
    TipoIncidente.SENSOR_SEM_LEITURA: 0.1,
}


def taxas_para(hall: Hall) -> dict[TipoIncidente, float]:
    """Taxas padrão proporcionais ao tamanho do hall: mais equipamento, mais incidentes."""
    fator = hall.total_racks / 200
    return {tipo: taxa * fator for tipo, taxa in TAXAS_PADRAO.items()}


def _falha_crac_da_madrugada(dia: int, crac: str) -> IncidenteProgramado:
    """O roteiro da demo: um CRAC falha às 2h, horário de Brasília (5h UTC)."""
    return IncidenteProgramado(
        tipo=TipoIncidente.FALHA_CRAC,
        inicio_h=(dia - 1) * 24 + 5,
        duracao_min=150,
        alvo=crac,
        intensidade=0.9,
    )


class Preset(StrEnum):
    TESTE = "teste"
    DEMO = "demo"
    BILHAO = "bilhao"


def preset(nome: Preset | str) -> ConfigSimulacao:
    """Configurações prontas: ``teste`` (segundos), ``demo`` (30 dias) e ``bilhao``."""
    match Preset(nome):
        case Preset.TESTE:
            return ConfigSimulacao(
                nome="teste",
                hall=Hall(fileiras=2, racks_por_fileira=5, cracs=2),
                periodo=Periodo(dias=1, intervalo_s=60),
            )
        case Preset.DEMO:
            hall = Hall(fileiras=10, racks_por_fileira=20, cracs=6)
            return ConfigSimulacao(
                nome="demo",
                hall=hall,
                periodo=Periodo(dias=30, intervalo_s=60),
                incidentes=ConfigIncidentes(
                    taxas_por_dia=taxas_para(hall),
                    programados=[_falha_crac_da_madrugada(dia=7, crac="CRAC-02")],
                ),
            )
        case Preset.BILHAO:
            hall = Hall(fileiras=25, racks_por_fileira=40, cracs=12)
            sensores = hall.total_racks * SENSORES_POR_RACK + hall.cracs * SENSORES_POR_CRAC
            passos = math.ceil(1_000_000_000 / sensores)
            return ConfigSimulacao(
                nome="bilhao",
                hall=hall,
                periodo=Periodo(dias=passos / SEGUNDOS_POR_DIA, intervalo_s=1),
                incidentes=ConfigIncidentes(
                    taxas_por_dia=taxas_para(hall),
                    programados=[_falha_crac_da_madrugada(dia=2, crac="CRAC-05")],
                ),
            )


def carregar_config(caminho: Path) -> ConfigSimulacao:
    """Lê uma configuração em TOML. Campos ausentes usam os valores padrão."""
    with caminho.open("rb") as arquivo:
        dados = tomllib.load(arquivo)
    dados.setdefault("nome", re.sub(r"[^a-z0-9_-]", "-", caminho.stem.lower()).strip("-"))
    return ConfigSimulacao.model_validate(dados)
