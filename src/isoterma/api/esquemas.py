"""Modelos das respostas da API. Viram o esquema OpenAPI e, dele, os tipos do front."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TipoSensorRack = Literal["temp_entrada", "temp_saida", "potencia_kw"]
Altura = Literal["base", "meio", "topo"]


class Simulacao(BaseModel):
    nome: str
    racks: int
    cracs: int
    sensores: int
    leituras: int
    inicio: datetime
    fim: datetime
    intervalo_s: int
    fuso: str
    camadas: list[str] = Field(description="Tabelas de dados disponíveis: leituras e agregados")


class RackPlanta(BaseModel):
    rack_id: str
    fileira: str
    posicao: int
    x_m: float
    y_m: float
    potencia_nominal_kw: float
    perfil: str
    zona_crac: str


class CracPlanta(BaseModel):
    crac_id: str
    x_m: float
    y_m: float
    setpoint_c: float


class Planta(BaseModel):
    racks: list[RackPlanta]
    cracs: list[CracPlanta]
    largura_m: float = Field(description="Extensão do hall no eixo x, incluindo os CRACs")
    profundidade_m: float = Field(description="Extensão do hall no eixo y, incluindo os CRACs")


class Estatistica(BaseModel):
    minimo: float | None
    media: float | None
    maximo: float | None


class Resumo(BaseModel):
    inicio: datetime
    fim: datetime
    fonte: str
    racks: int
    cracs: int
    sensores: int
    leituras: int
    leituras_nulas: int
    potencia_media_total_kw: float | None
    racks_acima_da_faixa: int
    racks_abaixo_da_faixa: int
    por_tipo: dict[str, Estatistica]


class ValorRack(BaseModel):
    rack_id: str
    fileira: str
    posicao: int
    x_m: float
    y_m: float
    zona_crac: str
    valor: float | None
    faixa: Literal["acima", "abaixo", "ok"] | None


class MapaTermico(BaseModel):
    instante: datetime
    tipo: TipoSensorRack
    altura: Altura | None
    racks: list[ValorRack]


class RackForaDaFaixa(BaseModel):
    rack_id: str
    fileira: str
    zona_crac: str
    minutos_acima: float
    minutos_abaixo: float
    pico_c: float | None
    minimo_c: float | None
    primeira_vez: datetime | None
    ultima_vez: datetime | None


class PontoSerie(BaseModel):
    inicio: datetime
    sensor: str
    tipo: str
    unidade: str
    minimo: float | None
    media: float | None
    maximo: float | None
    leituras: int


class Serie(BaseModel):
    alvo: str
    pontos: list[PontoSerie]


class Incidente(BaseModel):
    incidente_id: int
    tipo: str
    alvo_tipo: str
    alvo: str
    inicio: datetime
    fim: datetime
    intensidade: float
    descricao: str


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=1, max_length=2_000)


class EventoPasso(BaseModel):
    """Uma ferramenta que o agente chamou (evento ``passo`` do streaming)."""

    ferramenta: str
    argumentos: dict[str, object]
    segundos: float
    linhas: int | None
    sql: str | None
    erro: bool
    mensagem_erro: str | None = None


class EventoResposta(BaseModel):
    """A resposta final do agente (evento ``resposta``)."""

    texto: str
    parada: str
    detalhe: str
    provedor: str
    modelo: str
    turnos: int
    segundos: float
    tokens_entrada: int
    tokens_saida: int
    tokens_cache: int
    custo_usd: float | None


class EventoErro(BaseModel):
    """Falha que impediu a resposta (evento ``erro``)."""

    mensagem: str


class Saude(BaseModel):
    status: Literal["ok"]
    versao: str
    simulacoes: int
    llm: str | None
